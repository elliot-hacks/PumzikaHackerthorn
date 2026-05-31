from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from io import StringIO
import json

from home.models import Review, TopicCluster, PropertyInsight, SentimentSnapshot
from home.tasks import (
    bulk_process_home,
    update_topic_clusters,
    generate_property_insights,
    build_sentiment_snapshots,
)


@staff_member_required
def command_palette_api(request):
    """
    API endpoint for command palette operations.
    Handles NLP operations triggered from the Unfold command palette.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        command = data.get("command")
        params = data.get("params", {})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Command handlers
    handlers = {
        "analyze_sentiment": handle_analyze_sentiment,
        "extract_topics": handle_extract_topics,
        "generate_insights": handle_generate_insights,
        "update_clusters": handle_update_clusters,
        "build_snapshots": handle_build_snapshots,
        "get_status": handle_get_status,
    }

    handler = handlers.get(command)
    if not handler:
        return JsonResponse({"error": f"Unknown command: {command}"}, status=400)

    return handler(request, params)


def handle_analyze_sentiment(request, params):
    """Trigger sentiment analysis on unprocessed reviews."""
    batch_size = params.get("batch_size", 100)
    async_mode = params.get("async", True)

    if async_mode:
        task = bulk_process_home.delay(batch_size=batch_size)
        return JsonResponse({
            "success": True,
            "message": f"Queued sentiment analysis for {batch_size} reviews",
            "task_id": task.id,
        })
    else:
        out = StringIO()
        call_command("analyze_sentiment", "--batch-size", str(batch_size), stdout=out)
        return JsonResponse({
            "success": True,
            "message": out.getvalue(),
        })


def handle_extract_topics(request, params):
    """Trigger topic extraction on reviews."""
    update_clusters = params.get("update_clusters", True)
    async_mode = params.get("async", True)

    if async_mode:
        # Run extraction and optionally update clusters
        from home.tasks import extract_topics_task
        task = extract_topics_task.delay(update_clusters=update_clusters)
        return JsonResponse({
            "success": True,
            "message": "Queued topic extraction",
            "task_id": task.id,
        })
    else:
        args = []
        if update_clusters:
            args.append("--update-clusters")
        out = StringIO()
        call_command("extract_topics", *args, stdout=out)
        return JsonResponse({
            "success": True,
            "message": out.getvalue(),
        })


def handle_generate_insights(request, params):
    """Generate LLM-powered property insights."""
    property_id = params.get("property_id")
    generate_all = params.get("all", True)
    async_mode = params.get("async", True)

    if async_mode:
        if property_id:
            task = generate_property_insights.delay(property_id=property_id)
        else:
            task = generate_property_insights.delay()
        return JsonResponse({
            "success": True,
            "message": "Queued insight generation",
            "task_id": task.id,
        })
    else:
        args = []
        if property_id:
            args.extend(["--property", property_id])
        elif generate_all:
            args.append("--all")
        out = StringIO()
        call_command("generate_insights", *args, stdout=out)
        return JsonResponse({
            "success": True,
            "message": out.getvalue(),
        })


def handle_update_clusters(request, params):
    """Update topic cluster aggregates."""
    task = update_topic_clusters.delay()
    return JsonResponse({
        "success": True,
        "message": "Queued topic cluster update",
        "task_id": task.id,
    })


def handle_build_snapshots(request, params):
    """Build sentiment snapshots."""
    task = build_sentiment_snapshots.delay()
    return JsonResponse({
        "success": True,
        "message": "Queued sentiment snapshot generation",
        "task_id": task.id,
    })


def handle_get_status(request, params):
    """Get current NLP system status."""
    from django.db.models import Count, Avg
    from django.utils import timezone
    from datetime import timedelta

    total_reviews = Review.objects.count()
    processed_reviews = Review.objects.filter(is_processed=True).count()
    unprocessed_reviews = total_reviews - processed_reviews

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

    # Topic clusters
    topic_count = TopicCluster.objects.count()

    # Property insights
    insight_count = PropertyInsight.objects.count()
    total_properties = Review.objects.values("property_id").distinct().count()

    # Recent activity
    yesterday = timezone.now() - timedelta(hours=24)
    recent_processed = Review.objects.filter(
        is_processed=True,
        updated_at__gte=yesterday
    ).count()

    return JsonResponse({
        "success": True,
        "data": {
            "reviews": {
                "total": total_reviews,
                "processed": processed_reviews,
                "unprocessed": unprocessed_reviews,
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
            },
            "topics": {
                "clusters": topic_count,
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
    })


@staff_member_required
def chat_api(request):
    """
    LLM-powered chat API for natural language queries about hotel reviews.
    Uses the LLM service to analyze questions and query the database.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        query = data.get("query", "")
        history = data.get("history", [])
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not query:
        return JsonResponse({"error": "No query provided"}, status=400)

    try:
        # Use the LLM service to process the query
        from home.llm_service import LLMService
        from home.nlp import NLPQueryEngine
        
        llm = LLMService()
        engine = NLPQueryEngine()
        
        # Process the query with the LLM
        result = engine.process_query(query, history)
        
        return JsonResponse({
            "success": True,
            "response": result["response"],
            "data": result.get("data", {}),
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        })


@staff_member_required
def dashboard_with_commands(request):
    """
    Enhanced dashboard view with command palette integration.
    Extends the admin dashboard with command palette UI.
    """
    from django.db.models import Count, Avg, Q
    from django.db.models.functions import TruncDate
    from datetime import date, timedelta

    # Overall sentiment distribution
    sent_counts = dict(
        Review.objects.filter(is_processed=True)
        .values("sentiment")
        .annotate(n=Count("id"))
        .values_list("sentiment", "n")
    )

    # Sentiment over time (last 90 days, daily)
    cutoff = date.today() - timedelta(days=90)
    timeline = list(
        Review.objects
        .filter(is_processed=True, review_date__gte=cutoff)
        .annotate(day=TruncDate("review_date"))
        .values("day")
        .annotate(
            pos=Count("id", filter=Q(sentiment="positive")),
            neg=Count("id", filter=Q(sentiment="negative")),
        )
        .order_by("day")
        .values("day", "pos", "neg")
    )

    # Top 10 topics by review count
    top_topics = list(
        TopicCluster.objects.order_by("-review_count")[:10]
        .values("label", "review_count", "avg_sentiment_score")
    )

    # Top 10 properties by negative review count
    problem_props = list(
        Review.objects
        .filter(is_processed=True, sentiment="negative")
        .values("property_name")
        .annotate(neg_count=Count("id"))
        .order_by("-neg_count")[:10]
        .values("property_name", "neg_count")
    )

    # Language breakdown
    lang_counts = dict(
        Review.objects.filter(is_processed=True)
        .values("language")
        .annotate(n=Count("id"))
        .values_list("language", "n")
    )

    # Aspect averages across all reviews
    import statistics
    aspect_all = {}
    for asp in Review.objects.filter(is_processed=True).values_list("aspect_scores", flat=True).iterator():
        if asp:
            for k, v in asp.items():
                aspect_all.setdefault(k, []).append(v)
    aspect_avgs = {
        k: round(statistics.mean(v) * 100)
        for k, v in aspect_all.items() if v
    }

    # Processing stats for command palette
    total_reviews = Review.objects.count()
    processed = Review.objects.filter(is_processed=True).count()
    unprocessed = total_reviews - processed

    context = {
        **admin.site.each_context(request),
        "title": "Review Sentiment Dashboard",
        "sent_counts": sent_counts,
        "timeline": timeline,
        "top_topics": top_topics,
        "problem_props": problem_props,
        "lang_counts": lang_counts,
        "aspect_avgs": aspect_avgs,
        "total_reviews": total_reviews,
        "processed": processed,
        "unprocessed": unprocessed,
        # Command palette quick stats
        "command_stats": {
            "pending_reviews": unprocessed,
            "topic_clusters": TopicCluster.objects.count(),
            "property_insights": PropertyInsight.objects.count(),
            "total_properties": Review.objects.values("property_id").distinct().count(),
        }
    }
    return render(request, "admin/home/dashboard.html", context)

