"""
Django management command to show NLP processing status and statistics.
Used by the command palette for quick system status checks.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Avg, Q
from home.models import Review, TopicCluster, SentimentSnapshot, PropertyInsight
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = "Show NLP processing status and system statistics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output in JSON format for API consumption",
        )
        parser.add_argument(
            "--brief",
            action="store_true",
            help="Show only key metrics (one-line summary)",
        )

    def handle(self, *args, **options):
        json_output = options["json"]
        brief = options["brief"]

        # Gather statistics
        total_reviews = Review.objects.count()
        processed_reviews = Review.objects.filter(is_processed=True).count()
        unprocessed_reviews = total_reviews - processed_reviews
        flagged_reviews = Review.objects.filter(is_flagged=True).count()

        # Language distribution
        lang_stats = dict(
            Review.objects.filter(is_processed=True)
            .values("language")
            .annotate(count=Count("id"))
            .values_list("language", "count")
        )

        # Sentiment distribution
        sentiment_stats = dict(
            Review.objects.filter(is_processed=True)
            .values("sentiment")
            .annotate(count=Count("id"))
            .values_list("sentiment", "count")
        )

        # Processing models used
        model_stats = dict(
            Review.objects.filter(is_processed=True)
            .values("sentiment_model")
            .annotate(count=Count("id"))
            .values_list("sentiment_model", "count")
        )

        # Topic clusters
        topic_count = TopicCluster.objects.count()
        top_topics = list(
            TopicCluster.objects.order_by("-review_count")[:5]
            .values("label", "review_count", "avg_sentiment_score")
        )

        # Property insights
        insight_count = PropertyInsight.objects.count()
        total_properties = Review.objects.values("property_id").distinct().count()

        # Recent activity (last 24 hours)
        yesterday = timezone.now() - timedelta(hours=24)
        recent_processed = Review.objects.filter(
            is_processed=True,
            updated_at__gte=yesterday
        ).count()

        # Average processing stats
        avg_sentiment_score = Review.objects.filter(
            is_processed=True
        ).aggregate(avg=Avg("sentiment_score"))["avg"] or 0

        if brief:
            # One-line summary
            pct = (processed_reviews / total_reviews * 100) if total_reviews > 0 else 0
            self.stdout.write(
                f"📊 NLP Status: {processed_reviews}/{total_reviews} reviews processed ({pct:.1f}%) | "
                f"{topic_count} topics | {insight_count} insights | "
                f"{lang_stats.get('sw', 0)} Swahili reviews"
            )
        elif json_output:
            # JSON output for API
            import json
            data = {
                "reviews": {
                    "total": total_reviews,
                    "processed": processed_reviews,
                    "unprocessed": unprocessed_reviews,
                    "flagged": flagged_reviews,
                    "processing_rate": round(processed_reviews / total_reviews * 100, 2) if total_reviews > 0 else 0,
                },
                "languages": {
                    "english": lang_stats.get("en", 0),
                    "swahili": lang_stats.get("sw", 0),
                    "other": lang_stats.get("other", 0),
                },
                "sentiment": {
                    "positive": sentiment_stats.get("positive", 0),
                    "negative": sentiment_stats.get("negative", 0),
                    "neutral": sentiment_stats.get("neutral", 0),
                    "average_score": round(avg_sentiment_score, 3),
                },
                "models": dict(model_stats),
                "topics": {
                    "clusters": topic_count,
                    "top_topics": [
                        {
                            "label": t["label"],
                            "count": t["review_count"],
                            "sentiment": round(t["avg_sentiment_score"], 3),
                        }
                        for t in top_topics
                    ],
                },
                "insights": {
                    "generated": insight_count,
                    "total_properties": total_properties,
                    "coverage": round(insight_count / total_properties * 100, 2) if total_properties > 0 else 0,
                },
                "activity": {
                    "processed_last_24h": recent_processed,
                }
            }
            self.stdout.write(json.dumps(data, indent=2))
        else:
            # Detailed human-readable output
            self.stdout.write(self.style.SUCCESS("╔══════════════════════════════════════════╗"))
            self.stdout.write(self.style.SUCCESS("║   🏠 Pumzika NLP Review Analytics Hub   ║"))
            self.stdout.write(self.style.SUCCESS("╚══════════════════════════════════════════╝"))

            # Processing Status
            pct = (processed_reviews / total_reviews * 100) if total_reviews > 0 else 0
            self.stdout.write(f"\n📊 Processing Status:")
            self.stdout.write(f"  Total Reviews:      {total_reviews:,}")
            self.stdout.write(f"  Processed:          {processed_reviews:,} ({pct:.1f}%)")
            self.stdout.write(f"  Pending:            {unprocessed_reviews:,}")
            self.stdout.write(f"  Flagged:            {flagged_reviews}")

            # Language Distribution
            self.stdout.write(f"\n🌍 Language Distribution:")
            self.stdout.write(f"  English:            {lang_stats.get('en', 0):,}")
            self.stdout.write(f"  Swahili:            {lang_stats.get('sw', 0):,}")
            self.stdout.write(f"  Other:              {lang_stats.get('other', 0):,}")

            # Sentiment Analysis
            self.stdout.write(f"\n💭 Sentiment Analysis:")
            self.stdout.write(f"  Positive:           {sentiment_stats.get('positive', 0):,}")
            self.stdout.write(f"  Negative:           {sentiment_stats.get('negative', 0):,}")
            self.stdout.write(f"  Neutral:            {sentiment_stats.get('neutral', 0):,}")
            self.stdout.write(f"  Avg Score:          {avg_sentiment_score:.3f}")

            # Models Used
            if model_stats:
                self.stdout.write(f"\n🤖 Sentiment Models:")
                for model, count in sorted(model_stats.items(), key=lambda x: -x[1]):
                    self.stdout.write(f"  {model:20s}: {count:,} reviews")

            # Topic Clusters
            self.stdout.write(f"\n🏷️  Topic Clusters:")
            self.stdout.write(f"  Total Clusters:     {topic_count}")
            if top_topics:
                self.stdout.write(f"  Top 5 Topics:")
                for topic in top_topics:
                    sentiment_emoji = "🟢" if topic["avg_sentiment_score"] >= 0.65 else "🔴" if topic["avg_sentiment_score"] <= 0.4 else "🟡"
                    self.stdout.write(
                        f"    {sentiment_emoji} {topic['label']:30s}: {topic['review_count']:4d} reviews "
                        f"(sentiment: {topic['avg_sentiment_score']:.2f})"
                    )

            # Property Insights
            self.stdout.write(f"\n💡 Property Insights:")
            self.stdout.write(f"  Insights Generated: {insight_count}")
            self.stdout.write(f"  Total Properties:   {total_properties}")
            coverage = (insight_count / total_properties * 100) if total_properties > 0 else 0
            self.stdout.write(f"  Coverage:           {coverage:.1f}%")

            # Recent Activity
            self.stdout.write(f"\n⚡ Recent Activity:")
            self.stdout.write(f"  Processed (24h):    {recent_processed} reviews")

            # Recommendations
            if unprocessed_reviews > 0:
                self.stdout.write(
                    f"\n💡 {self.style.SUCCESS('Run: python manage.py analyze_sentiment --async')}"
                )
            if insight_count < total_properties * 0.5:
                self.stdout.write(
                    f"💡 {self.style.SUCCESS('Run: python manage.py generate_insights --all --async')}"
                )