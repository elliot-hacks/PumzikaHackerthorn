# reviews/tasks.py
"""
Celery tasks for the reviews app.

  process_review_task        — NLP pipeline for one review
  bulk_process_reviews       — batch NLP for unprocessed reviews
  build_sentiment_snapshots  — daily aggregate per property
  generate_property_insights — LLM narrative for each property
  update_topic_clusters      — rebuild TopicCluster counts + keywords
  ingest_kaggle_dataset      — trigger ingestion from stored file path
"""

from __future__ import annotations

import logging

from celery import shared_task, group

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="reviews.tasks.process_review_task",
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def process_review_task(self, review_pk: str) -> dict:
    """Run the full NLP pipeline on a single Review."""
    try:
        from home.models import Review
        from home.nlp import review_pipeline
        review = Review.objects.get(pk=review_pk)
        ok = review_pipeline.process(review)
        return {"status": "ok" if ok else "failed", "pk": review_pk}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=self.default_retry_delay * (2 ** self.request.retries))


@shared_task(name="reviews.tasks.bulk_process_reviews")
def bulk_process_reviews(batch_size: int = 200) -> dict:
    """
    Process all unprocessed reviews in batches.
    Safe to run as a periodic task — idempotent.
    """
    from home.models import Review
    from home.nlp import review_pipeline

    unprocessed = Review.objects.filter(is_processed=False).count()
    logger.info(f"bulk_process_reviews: {unprocessed} reviews to process")

    result = review_pipeline.process_batch(
        Review.objects.filter(is_processed=False),
        limit=batch_size,
    )
    logger.info(f"bulk_process_reviews done: {result}")
    return result


@shared_task(name="reviews.tasks.build_sentiment_snapshots")
def build_sentiment_snapshots() -> dict:
    """
    Build/refresh SentimentSnapshot rows for every property+date combination
    that has processed reviews but no snapshot yet.

    Run daily at midnight via Celery Beat.
    """
    from django.db.models import Avg, Count, Q
    from home.models import Review, SentimentSnapshot

    # Find all property+date pairs with processed reviews
    pairs = (
        Review.objects
        .filter(is_processed=True, review_date__isnull=False)
        .values("property_id", "property_name", "review_date")
        .annotate(n=Count("id"))
        .filter(n__gt=0)
    )

    created = updated = 0
    for pair in pairs:
        pid   = pair["property_id"]
        pname = pair["property_name"]
        date  = pair["review_date"]

        qs = Review.objects.filter(
            property_id=pid,
            review_date=date,
            is_processed=True,
        )
        stats = qs.aggregate(
            total   = Count("id"),
            pos     = Count("id", filter=Q(sentiment="positive")),
            neg     = Count("id", filter=Q(sentiment="negative")),
            neu     = Count("id", filter=Q(sentiment="neutral")),
            avg_rs  = Avg("reviewer_score"),
            avg_sent= Avg("sentiment_score"),
        )

        # Collect top topics for the day
        from collections import Counter
        topic_counter: Counter = Counter()
        for topics in qs.values_list("topic_labels", flat=True):
            if topics:
                topic_counter.update(topics)
        top_topics = [t for t, _ in topic_counter.most_common(5)]

        # Aspect averages
        import statistics
        aspect_buckets: dict[str, list] = {}
        for asp in qs.values_list("aspect_scores", flat=True):
            if asp:
                for k, v in asp.items():
                    aspect_buckets.setdefault(k, []).append(v)
        aspect_avgs = {
            k: round(statistics.mean(v), 3)
            for k, v in aspect_buckets.items()
            if v
        }

        snap, is_new = SentimentSnapshot.objects.update_or_create(
            property_id=pid,
            snapshot_date=date,
            defaults={
                "property_name":    pname,
                "total_reviews":    stats["total"] or 0,
                "positive_count":   stats["pos"]   or 0,
                "negative_count":   stats["neg"]   or 0,
                "neutral_count":    stats["neu"]   or 0,
                "avg_score":        round(float(stats["avg_rs"]   or 0), 2),
                "avg_sentiment":    round(float(stats["avg_sent"] or 0), 3),
                "top_topics":       top_topics,
                "aspect_averages":  aspect_avgs,
            },
        )
        if is_new:
            created += 1
        else:
            updated += 1

    result = {"created": created, "updated": updated}
    logger.info(f"build_sentiment_snapshots done: {result}")
    return result


@shared_task(name="reviews.tasks.update_topic_clusters")
def update_topic_clusters() -> dict:
    """
    Rebuild TopicCluster rows from review.topic_labels.
    Sets review_count, avg_sentiment_score, top_properties per cluster.
    """
    from django.db.models import Avg, Count, Q
    from home.models import Review, TopicCluster
    from collections import Counter

    # Gather all topics + their stats
    topic_data: dict[str, dict] = {}

    for review in Review.objects.filter(is_processed=True).iterator(chunk_size=500):
        if not review.topic_labels:
            continue
        for topic in review.topic_labels:
            if topic not in topic_data:
                topic_data[topic] = {
                    "count":      0,
                    "sentiments": [],
                    "properties": [],
                    "phrases":    [],
                }
            topic_data[topic]["count"] += 1
            if review.sentiment_score is not None:
                sentiment_val = (
                    review.sentiment_score
                    if review.sentiment == "positive"
                    else (1 - review.sentiment_score)
                    if review.sentiment == "negative"
                    else 0.5
                )
                topic_data[topic]["sentiments"].append(sentiment_val)
            topic_data[topic]["properties"].append(review.property_id)
            topic_data[topic]["phrases"].extend(review.key_phrases[:3])

    upserted = 0
    for label, data in topic_data.items():
        import statistics
        avg_sent = (
            round(statistics.mean(data["sentiments"]), 3)
            if data["sentiments"] else 0.5
        )
        prop_counts = Counter(data["properties"]).most_common(5)
        top_props   = [pid for pid, _ in prop_counts]

        phrase_counts = Counter(data["phrases"]).most_common(10)
        keywords      = [ph for ph, _ in phrase_counts]

        TopicCluster.objects.update_or_create(
            label=label,
            defaults={
                "review_count":         data["count"],
                "avg_sentiment_score":  avg_sent,
                "top_properties":       top_props,
                "keywords":             keywords,
            },
        )
        upserted += 1

    logger.info(f"update_topic_clusters: {upserted} clusters upserted")
    return {"upserted": upserted}


@shared_task(name="reviews.tasks.generate_property_insights")
def generate_property_insights(property_id: str = None) -> dict:
    """
    Generate LLM narrative insights for one or all properties.
    If property_id is None, regenerates all properties that have
    100+ processed reviews.
    """
    from home.models import Review, PropertyInsight
    from django.db.models import Avg, Count, Q
    import json

    if property_id:
        property_ids = [property_id]
    else:
        property_ids = list(
            Review.objects
            .filter(is_processed=True)
            .values("property_id")
            .annotate(n=Count("id"))
            .filter(n__gte=5)  # Lowered for demo — raise to 100 in production
            .values_list("property_id", flat=True)[:50]  # Cap at 50 per run
        )

    generated = 0
    for pid in property_ids:
        try:
            _generate_insight_for_property(pid)
            generated += 1
        except Exception as e:
            logger.warning(f"Insight generation failed for {pid}: {e}")

    return {"generated": generated}


def _generate_insight_for_property(property_id: str) -> None:
    """Generate and save a PropertyInsight for one property."""
    from home.models import Review, PropertyInsight
    from django.db.models import Avg, Count, Q
    from collections import Counter
    import json

    qs = Review.objects.filter(property_id=property_id, is_processed=True)
    if not qs.exists():
        return

    property_name = qs.first().property_name

    # Aggregate stats
    stats = qs.aggregate(
        total    = Count("id"),
        avg_rs   = Avg("reviewer_score"),
        pos_count= Count("id", filter=Q(sentiment="positive")),
        neg_count= Count("id", filter=Q(sentiment="negative")),
        neu_count= Count("id", filter=Q(sentiment="neutral")),
    )

    # Top topics
    topic_counter: Counter = Counter()
    for topics in qs.values_list("topic_labels", flat=True):
        if topics:
            topic_counter.update(topics)
    top_topics = [t for t, _ in topic_counter.most_common(8)]

    # Sample negative key phrases for the LLM
    neg_phrases = []
    for phrases in (
        qs.filter(sentiment="negative")
        .values_list("key_phrases", flat=True)[:30]
    ):
        neg_phrases.extend(phrases[:3])
    neg_phrases = list(set(neg_phrases))[:15]

    # Sample positive key phrases
    pos_phrases = []
    for phrases in (
        qs.filter(sentiment="positive")
        .values_list("key_phrases", flat=True)[:30]
    ):
        pos_phrases.extend(phrases[:3])
    pos_phrases = list(set(pos_phrases))[:15]

    # Swahili-specific
    sw_qs     = qs.filter(language="sw")
    sw_count  = sw_qs.count()
    sw_sent   = sw_qs.aggregate(avg=Avg("sentiment_score"))["avg"]

    # Aspect averages across all reviews
    import statistics
    aspect_buckets: dict[str, list] = {}
    for asp in qs.values_list("aspect_scores", flat=True):
        if asp:
            for k, v in asp.items():
                aspect_buckets.setdefault(k, []).append(v)
    aspect_avgs = {
        k: round(statistics.mean(v), 3)
        for k, v in aspect_buckets.items() if v
    }

    # LLM narrative generation
    narrative_data = _llm_generate_narrative(
        property_name=property_name,
        total_reviews=stats["total"],
        avg_score=stats["avg_rs"],
        pos_count=stats["pos_count"],
        neg_count=stats["neg_count"],
        top_topics=top_topics,
        pos_phrases=pos_phrases,
        neg_phrases=neg_phrases,
        aspect_avgs=aspect_avgs,
        sw_count=sw_count,
    )

    PropertyInsight.objects.update_or_create(
        property_id=property_id,
        defaults={
            "property_name":        property_name,
            "strength_summary":     narrative_data.get("strengths", ""),
            "weakness_summary":     narrative_data.get("weaknesses", ""),
            "actionable_advice":    narrative_data.get("advice", ""),
            "overall_narrative":    narrative_data.get("narrative", ""),
            "total_reviews":        stats["total"] or 0,
            "avg_reviewer_score":   round(float(stats["avg_rs"] or 0), 2),
            "sentiment_breakdown":  {
                "positive": stats["pos_count"] or 0,
                "negative": stats["neg_count"] or 0,
                "neutral":  stats["neu_count"] or 0,
            },
            "top_topics":           top_topics,
            "aspect_scores":        aspect_avgs,
            "swahili_feedback_count": sw_count,
            "swahili_sentiment_avg": round(float(sw_sent or 0), 3) if sw_sent else None,
        },
    )


def _llm_generate_narrative(
    property_name, total_reviews, avg_score, pos_count, neg_count,
    top_topics, pos_phrases, neg_phrases, aspect_avgs, sw_count,
) -> dict:
    """Call LLM to generate human-readable property narrative."""
    try:
        import json
        from ai.services import ai_service_provider
        from django.contrib.auth import get_user_model
        User = get_user_model()
        system_user = User.objects.filter(is_superuser=True).first()
        if not system_user:
            return {}

        pct_pos = round(pos_count / total_reviews * 100) if total_reviews else 0
        pct_neg = round(neg_count / total_reviews * 100) if total_reviews else 0

        aspect_str = ", ".join(
            f"{k}: {v:.0%}" for k, v in sorted(
                aspect_avgs.items(), key=lambda x: -x[1]
            )[:5]
        )

        prompt = f"""You are a hospitality analytics expert writing insights for an East African rental platform.

Property: {property_name}
Total reviews: {total_reviews} | Avg score: {avg_score:.1f}/10
Sentiment: {pct_pos}% positive, {pct_neg}% negative
Top topics: {', '.join(top_topics[:5])}
Aspect scores: {aspect_str}
What guests love: {', '.join(pos_phrases[:8])}
What guests dislike: {', '.join(neg_phrases[:8])}
Swahili reviews: {sw_count}

Return JSON only:
{{
  "strengths": "2-3 sentences on what this property does well",
  "weaknesses": "2-3 sentences on the main complaints",
  "advice": "3 specific actionable improvements",
  "narrative": "One compelling paragraph summary for property management"
}}"""

        response = ai_service_provider.chat_completion_sync(
            user=system_user,
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"},
            timeout=15,
        )
        if response and response.get("content"):
            return json.loads(response["content"])
    except Exception as e:
        logger.debug(f"LLM narrative generation failed: {e}")
    return {}


@shared_task(name="reviews.tasks.ingest_kaggle_dataset")
def ingest_kaggle_dataset(
    csv_path: str,
    batch_size: int = 500,
    limit: int = None,
) -> dict:
    """Trigger Kaggle CSV ingestion as a Celery task."""
    from home.ingestion import KaggleIngester
    return KaggleIngester().ingest(
        csv_path=csv_path,
        batch_size=batch_size,
        limit=limit,
        queue_nlp=True,
    )


@shared_task(name="reviews.tasks.ingest_afrisenti_dataset")
def ingest_afrisenti_dataset(file_path: str) -> dict:
    """Trigger AfriSenti ingestion as a Celery task."""
    from home.ingestion import AfriSentiIngester
    return AfriSentiIngester().ingest(file_path=file_path)


