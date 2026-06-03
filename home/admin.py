# home/admin.py
"""
Unfold admin for the Review Sentiment & NLP Analysis layer.

Surfaces:
  ReviewAdmin           — searchable list with sentiment badges + topic tags
  TopicClusterAdmin     — topic overview with sentiment bar
  SentimentSnapshotAdmin — daily aggregate view
  PropertyInsightAdmin  — LLM narrative per property
  ReviewDashboard       — custom admin view with Chart.js visualisations

Command palette integration:
  home and property insights are registered as searchable models
  so they appear in the Unfold command palette semantic search.
"""
from __future__ import annotations
import json
import logging
from django.contrib import admin
from django.urls import path
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count, Avg, Q
from django.views.decorators.http import require_GET
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from home.models import Review, TopicCluster, SentimentSnapshot, PropertyInsight


# ── Review Admin ───────────────────────────────────────────────────────────
@admin.register(Review)
class ReviewAdmin(UnfoldModelAdmin):
    change_list_template = "admin/home/change_list_with_panel.html"
    
    def changelist_view(self, request, extra_context=None):
        extra = extra_context or {}
        sent_counts = dict(
            Review.objects.values("sentiment")
            .annotate(n=Count("id"))
            .values_list("sentiment", "n")
        )
        extra["module_name"] = "Reviews"
        extra["stats"] = {
            "total":     Review.objects.count(),
            "processed": Review.objects.filter(is_processed=True).count(),
            "positive":  sent_counts.get("positive", 0),
            "negative":  sent_counts.get("negative", 0),
            "neutral":   sent_counts.get("neutral", 0),
            "swahili":   Review.objects.filter(language="sw").count(),
        }
        return super().changelist_view(request, extra_context=extra)

    list_display = [
        "property_name",
        "review_date",
        "reviewer_score_display",
        "sentiment_badge",
        "language_badge",
        "topics_display",
        "source",
        "is_processed",
    ]
    list_filter  = [
        "sentiment",
        "language",
        "source",
        "is_processed",
        "review_date",
    ]
    search_fields = [
        "property_name",
        "positive_text",
        "negative_text",
        "full_text",
        "key_phrases",
    ]
    date_hierarchy    = "review_date"
    list_per_page     = 50
    ordering          = ["-review_date"]
    readonly_fields   = [
        "sentiment", "sentiment_score", "sentiment_model",
        "topic_labels", "key_phrases", "aspect_scores",
        "language", "is_processed", "processing_error",
        "aspect_scores_display", "review_text_display",
        "created_at", "updated_at",
    ]
    fieldsets = (
        ("Review content", {
            "fields": (
                "property_name", "property_id",
                "review_date", "reviewer_score",
                "source", "external_id",
                "review_text_display",
            ),
        }),
        ("NLP results", {
            "fields": (
                "language",
                "sentiment", "sentiment_score", "sentiment_model",
                "topic_labels", "key_phrases",
                "aspect_scores_display",
            ),
        }),
        ("Status", {
            "classes": ("collapse",),
            "fields": ("is_processed", "is_flagged", "processing_error"),
        }),
        ("Audit", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )

    # ── Display helpers ────────────────────────────────────────────────────

    def reviewer_score_display(self, obj):
        if obj.reviewer_score is None:
            return "—"
        try:
            score = float(obj.reviewer_score)
        except (ValueError, TypeError):
            return "—"
        colour = (
            "#2e7d32" if score >= 8
            else "#e65100" if score >= 6
            else "#c62828"
        )
        # Pre-format the score as a string since format_html doesn't support :.1f
        score_str = f"{score:.1f}"
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colour, score_str,
        )
    reviewer_score_display.short_description = "Score"
    reviewer_score_display.admin_order_field = "reviewer_score"

    def sentiment_badge(self, obj):
        if not obj.sentiment:
            return "—"
        colours = {
            "positive": ("#2e7d32", "#fff"),
            "negative": ("#c62828", "#fff"),
            "neutral":  ("#757575", "#fff"),
        }
        bg, fg = colours.get(obj.sentiment, ("#555", "#fff"))
        pct = ""
        if obj.sentiment_score is not None:
            try:
                pct = f" {float(obj.sentiment_score):.0%}"
            except (ValueError, TypeError):
                pass
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:10px;font-size:11px;font-weight:600">{}{}</span>',
            bg, fg, obj.sentiment.title(), pct,
        )
    sentiment_badge.short_description = "Sentiment"
    sentiment_badge.admin_order_field = "sentiment"

    def language_badge(self, obj):
        colours = {"en": "#1565c0", "sw": "#4a148c", "other": "#555"}
        labels  = {"en": "EN", "sw": "SW", "other": "??"}
        c = colours.get(obj.language, "#555")
        l = labels.get(obj.language, obj.language.upper())
        return format_html(
            '<span style="background:{c};color:#fff;padding:1px 6px;'
            'border-radius:4px;font-size:10px;font-weight:600">{l}</span>',
            c=c, l=l,
        )
    language_badge.short_description = "Lang"

    def topics_display(self, obj):
        if not obj.topic_labels:
            return "—"
        badges = []
        for topic in obj.topic_labels[:3]:
            short = topic.split("&")[0].strip()[:12]
            badges.append(
                f'<span style="background:#e3f2fd;color:#1565c0;'
                f'padding:1px 5px;border-radius:4px;font-size:10px;'
                f'margin-right:3px">{short}</span>'
            )
        return mark_safe("".join(badges))
    topics_display.short_description = "Topics"

    def review_text_display(self, obj):
        rows = []
        if obj.positive_text and obj.positive_text not in ("No Positive", ""):
            rows.append(
                f'<div style="background:#f1f8e9;padding:8px;border-radius:6px;'
                f'border-left:3px solid #2e7d32;margin-bottom:6px;font-size:12px">'
                f'<strong style="color:#2e7d32">✓ Positive</strong><br>{obj.positive_text[:500]}</div>'
            )
        if obj.negative_text and obj.negative_text not in ("No Negative", ""):
            rows.append(
                f'<div style="background:#fce4ec;padding:8px;border-radius:6px;'
                f'border-left:3px solid #c62828;margin-bottom:6px;font-size:12px">'
                f'<strong style="color:#c62828">✗ Negative</strong><br>{obj.negative_text[:500]}</div>'
            )
        return mark_safe("".join(rows)) if rows else "—"
    review_text_display.short_description = "Review text"

    def aspect_scores_display(self, obj):
        if not obj.aspect_scores:
            return "—"
        rows = []
        for aspect, score in sorted(obj.aspect_scores.items(), key=lambda x: -x[1]):
            pct   = int(score * 100)
            colour = "#2e7d32" if pct >= 70 else "#e65100" if pct >= 40 else "#c62828"
            bar   = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            rows.append(
                f'<div style="font-size:11px;margin-bottom:3px">'
                f'<span style="display:inline-block;width:100px">{aspect.title()}</span>'
                f'<span style="color:{colour};font-family:monospace">{bar}</span>'
                f' {pct}%</div>'
            )
        return mark_safe("".join(rows))
    aspect_scores_display.short_description = "Aspect scores"

    # ── Actions ────────────────────────────────────────────────────────────

    @admin.action(description="Re-run NLP pipeline on selected home")
    def reprocess_home(self, request, queryset):
        queryset.update(is_processed=False, processing_error="")
        from home.tasks import process_review_task
        from celery import group
        pks = list(queryset.values_list("pk", flat=True))
        group(process_review_task.s(str(pk)) for pk in pks).apply_async()
        self.message_user(request, f"Queued NLP reprocessing for {len(pks)} home.")

    actions = ["reprocess_home"]


# ── TopicCluster Admin ─────────────────────────────────────────────────────
@admin.register(TopicCluster)
class TopicClusterAdmin(UnfoldModelAdmin):
    change_list_template = "admin/home/change_list_with_panel.html"
    
    def changelist_view(self, request, extra_context=None):
        extra = extra_context or {}
        total_reviews = Review.objects.filter(is_processed=True).count()
        extra["module_name"] = "Topic Clusters"
        extra["stats"] = {
            "total":     TopicCluster.objects.count(),
            "processed": TopicCluster.objects.filter(review_count__gt=0).count(),
            "positive":  TopicCluster.objects.filter(avg_sentiment_score__gte=0.65).count(),
            "negative":  TopicCluster.objects.filter(avg_sentiment_score__lt=0.40).count(),
            "neutral":   TopicCluster.objects.filter(avg_sentiment_score__gte=0.40, avg_sentiment_score__lt=0.65).count(),
        }
        return super().changelist_view(request, extra_context=extra)

    list_display  = [
        "label", "review_count", "sentiment_bar", "keywords_display",
    ]
    search_fields = ["label", "description"]
    readonly_fields = [
        "review_count", "avg_sentiment_score", "top_properties",
        "keywords", "sentiment_bar",
    ]
    ordering = ["-review_count"]

    def sentiment_bar(self, obj):
        pct    = int(obj.avg_sentiment_score * 100)
        colour = "#2e7d32" if pct >= 65 else "#e65100" if pct >= 40 else "#c62828"
        bar    = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        return format_html(
            '<span style="font-family:monospace;color:{c}">{b}</span> {p}%',
            c=colour, b=bar, p=pct,
        )
    sentiment_bar.short_description = "Avg sentiment"

    def keywords_display(self, obj):
        if not obj.keywords:
            return "—"
        return mark_safe(
            " ".join(
                f'<span style="background:#ede7f6;color:#4a148c;'
                f'padding:1px 6px;border-radius:4px;font-size:11px;margin:1px">'
                f'{kw}</span>'
                for kw in obj.keywords[:8]
            )
        )
    keywords_display.short_description = "Top keywords"


# ── PropertyInsight Admin ──────────────────────────────────────────────────
@admin.register(PropertyInsight)
class PropertyInsightAdmin(UnfoldModelAdmin):
    change_list_template = "admin/home/change_list_with_panel.html"
    
    def changelist_view(self, request, extra_context=None):
        extra = extra_context or {}
        total_insights = PropertyInsight.objects.count()
        # Count insights by sentiment (based on majority of reviews)
        pos_count = PropertyInsight.objects.filter(
            sentiment_breakdown__positive__gt=0
        ).count()
        neg_count = PropertyInsight.objects.filter(
            sentiment_breakdown__negative__gt=0
        ).count()
        extra["module_name"] = "Property Insights"
        extra["stats"] = {
            "total":     total_insights,
            "processed": PropertyInsight.objects.filter(generated_at__isnull=False).count(),
            "positive":  pos_count,
            "negative":  neg_count,
            "neutral":   total_insights - pos_count - neg_count,
        }
        return super().changelist_view(request, extra_context=extra)

    list_display  = [
        "property_name", "total_home", "avg_reviewer_score",
        "sentiment_breakdown_display", "swahili_feedback_count",
        "generated_at",
    ]
    search_fields = ["property_name", "property_id", "overall_narrative"]
    readonly_fields = [
        "total_home", "avg_reviewer_score",
        "sentiment_breakdown", "top_topics", "aspect_scores",
        "swahili_feedback_count", "swahili_sentiment_avg",
        "generated_at", "narrative_display",
    ]
    ordering = ["-total_home"]
    fieldsets = (
        ("Property", {"fields": ("property_id", "property_name")}),
        ("Narrative insights", {"fields": ("narrative_display",)}),
        ("Statistics", {
            "fields": (
                "total_home", "avg_reviewer_score",
                "sentiment_breakdown", "top_topics",
                "aspect_scores", "swahili_feedback_count", "swahili_sentiment_avg",
            ),
        }),
        ("Audit", {"classes": ("collapse",), "fields": ("generated_at",)}),
    )

    def sentiment_breakdown_display(self, obj):
        bd = obj.sentiment_breakdown or {}
        total = sum(bd.values()) or 1
        pos = bd.get("positive", 0)
        neg = bd.get("negative", 0)
        return format_html(
            '<span style="color:#2e7d32">▲{p}%</span> '
            '<span style="color:#c62828">▼{n}%</span>',
            p=round(pos / total * 100),
            n=round(neg / total * 100),
        )
    sentiment_breakdown_display.short_description = "Sentiment split"

    def narrative_display(self, obj):
        sections = [
            ("💪 Strengths",   obj.strength_summary,  "#f1f8e9", "#2e7d32"),
            ("⚠ Weaknesses",  obj.weakness_summary,  "#fce4ec", "#c62828"),
            ("💡 Advice",      obj.actionable_advice, "#fff8e1", "#e65100"),
            ("📋 Summary",     obj.overall_narrative, "#e3f2fd", "#1565c0"),
        ]
        html = ""
        for title, text, bg, colour in sections:
            if text:
                html += (
                    f'<div style="background:{bg};padding:10px;border-radius:8px;'
                    f'border-left:4px solid {colour};margin-bottom:10px">'
                    f'<strong style="color:{colour}">{title}</strong>'
                    f'<p style="margin:6px 0 0;font-size:13px">{text}</p></div>'
                )
        return mark_safe(html) if html else "—"
    narrative_display.short_description = "AI-generated insights"

    @admin.action(description="Regenerate insights for selected properties")
    def regenerate_insights(self, request, queryset):
        from home.tasks import generate_property_insights
        for insight in queryset:
            generate_property_insights.delay(property_id=insight.property_id)
        self.message_user(request, f"Queued insight regeneration for {queryset.count()} properties.")

    actions = ["regenerate_insights"]


# ── SentimentSnapshot Admin ────────────────────────────────────────────────
@admin.register(SentimentSnapshot)
class SentimentSnapshotAdmin(UnfoldModelAdmin):
    change_list_template = "admin/home/change_list_with_panel.html"
    
    def changelist_view(self, request, extra_context=None):
        extra = extra_context or {}
        total_snapshots = SentimentSnapshot.objects.count()
        # Count snapshots by positive count (high positivity >= 70%, low < 50%)
        # Using positive_count relative to total_home as a proxy for percentage
        pos_count = 0
        neg_count = 0
        for snap in SentimentSnapshot.objects.all():
            if snap.total_home > 0:
                pct = (snap.positive_count / snap.total_home) * 100
                if pct >= 70:
                    pos_count += 1
                elif pct < 50:
                    neg_count += 1
        neu_count = total_snapshots - pos_count - neg_count
        extra["module_name"] = "Sentiment Snapshots"
        extra["stats"] = {
            "total":     total_snapshots,
            "processed": total_snapshots,  # All snapshots are processed
            "positive":  pos_count,
            "negative":  neg_count,
            "neutral":   neu_count,
        }
        return super().changelist_view(request, extra_context=extra)

    list_display = [
        "property_name", "snapshot_date", "total_home",
        "positive_pct_display", "avg_score",
    ]
    list_filter  = ["snapshot_date"]
    search_fields = ["property_name", "property_id"]
    date_hierarchy = "snapshot_date"
    ordering = ["-snapshot_date"]
    readonly_fields = [f.name for f in SentimentSnapshot._meta.get_fields()]

    def positive_pct_display(self, obj):
        if obj.total_home > 0:
            pct = round((obj.positive_count / obj.total_home) * 100)
        else:
            pct = 0
        colour = "#2e7d32" if pct >= 70 else "#e65100" if pct >= 50 else "#c62828"
        return format_html(
            '<span style="color:{c};font-weight:600">{p}%</span>',
            c=colour, p=pct,
        )
    positive_pct_display.short_description = "Positive %"


# ── Documentation View ─────────────────────────────────────────────────────
class DocumentationView:
    """
    Standalone admin view that renders the documentation page.
    """
    
    @staticmethod
    def view(request):
        return render(request, "admin/home/documentation.html", {
            **admin.site.each_context(request),
            "title": "NLP Documentation",
        })


# ── Custom Dashboard View ──────────────────────────────────────────────────
class ReviewDashboardAdmin:
    """
    Standalone admin view that renders the Chart.js insight dashboard.
    Registered as a custom URL on the admin site from home/apps.py.
    """

    @staticmethod
    def view(request):
        from django.db.models.functions import TruncDate

        # Overall sentiment distribution
        sent_counts = dict(
            Review.objects.filter(is_processed=True)
            .values("sentiment")
            .annotate(n=Count("id"))
            .values_list("sentiment", "n")
        )

        # Sentiment over time (last 90 days, daily)
        from datetime import date, timedelta
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

        # Aspect averages across all home
        import statistics
        aspect_all: dict[str, list] = {}
        for asp in Review.objects.filter(is_processed=True).values_list("aspect_scores", flat=True).iterator():
            if asp:
                for k, v in asp.items():
                    if v is not None:
                        aspect_all.setdefault(k, []).append(float(v))
        aspect_avgs = {}
        for k, v in aspect_all.items():
            if v:
                try:
                    aspect_avgs[k] = round(statistics.mean(v) * 100)
                except:
                    aspect_avgs[k] = 0

        # Get property insights count
        property_insights_count = PropertyInsight.objects.count()

        context = {
            **admin.site.each_context(request),
            "title":             "Review Sentiment Dashboard",
            "sent_counts":       sent_counts,
            "timeline":          timeline,
            "top_topics":        top_topics,
            "problem_props":     problem_props,
            "lang_counts":       lang_counts,
            "aspect_avgs":       aspect_avgs,
            "total_home":        Review.objects.count(),
            "processed":         Review.objects.filter(is_processed=True).count(),
            "property_insights": property_insights_count,
        }
        return render(request, "admin/home/dashboard.html", context)
    

class NLPAdminSiteMixin:
    """
    Mixin that injects the two endpoints the command palette JS calls:
      POST /admin/home/api/chat/           → handleChatQuery()
      POST /admin/home/api/command-palette/ → executeCommand() + fetchStatus()
    """

    def get_urls(self):
        from django.urls import path
        custom = [
            path(
                "home/api/chat/",
                self.admin_view(self._nlp_chat_view),
                name="home_nlp_chat",
            ),
            path(
                "home/api/command-palette/",
                self.admin_view(self._nlp_command_view),
                name="home_nlp_command",
            ),
        ]
        return custom + super().get_urls()

    # ── module-level engine singleton ──────────────────────────────────
    _engine = None

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            from home.nlp import NLPQueryEngine
            cls._engine = NLPQueryEngine()
        return cls._engine

    # ── /admin/home/api/chat/ ──────────────────────────────────────────
    def _nlp_chat_view(self, request):
        if request.method != "POST":
            return JsonResponse({"success": False, "error": "POST only"}, status=405)
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

        query   = (body.get("query") or "").strip()
        history = body.get("history", [])

        if not query:
            return JsonResponse({"success": False, "error": "query required"}, status=400)

        try:
            result = self._get_engine().process_query(query, history=history)
            return JsonResponse({
                "success":  True,
                "response": result["response"],
                "data":     result.get("data", {}),
            })
        except Exception as e:
            logging.getLogger(__name__).exception("chat view error")
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    # ── /admin/home/api/command-palette/ ──────────────────────────────
    def _nlp_command_view(self, request):
        if request.method != "POST":
            return JsonResponse({"success": False, "error": "POST only"}, status=405)
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

        command = body.get("command", "")
        params  = body.get("params", {})

        handlers = {
            "get_status":        self._cmd_get_status,
            "analyze_sentiment": self._cmd_analyze_sentiment,
            "extract_topics":    self._cmd_extract_topics,
            "generate_insights": self._cmd_generate_insights,
            "update_clusters":   self._cmd_update_clusters,
            "build_snapshots":   self._cmd_build_snapshots,
        }

        handler = handlers.get(command)
        if not handler:
            return JsonResponse({"success": False, "error": f"Unknown command: {command}"}, status=400)

        try:
            return JsonResponse(handler(params))
        except Exception as e:
            logging.getLogger(__name__).exception(f"command {command} error")
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    # ── command handlers ───────────────────────────────────────────────
    def _cmd_get_status(self, params):
        from home.models import Review, TopicCluster, PropertyInsight
        from django.db.models import Count

        total     = Review.objects.count()
        processed = Review.objects.filter(is_processed=True).count()
        swahili   = Review.objects.filter(language="sw").count()
        clusters  = TopicCluster.objects.count()
        insights  = PropertyInsight.objects.count()

        return {
            "success": True,
            "data": {
                "reviews": {
                    "total":           total,
                    "processed":       processed,
                    "processing_rate": round(processed / total * 100) if total else 0,
                },
                "languages": {"swahili": swahili},
                "topics":    {"clusters": clusters},
                "insights":  {"generated": insights},
            },
        }

    def _cmd_analyze_sentiment(self, params):
        from home.tasks import bulk_process_home
        batch = params.get("batch_size", 200)
        task  = bulk_process_home.delay(batch_size=batch)
        return {"success": True, "message": f"Sentiment analysis queued (batch={batch})", "task_id": task.id}

    def _cmd_extract_topics(self, params):
        from home.tasks import extract_topics_task
        task = extract_topics_task.delay(update_clusters=params.get("update_clusters", True))
        return {"success": True, "message": "Topic extraction queued", "task_id": task.id}

    def _cmd_generate_insights(self, params):
        from home.tasks import generate_property_insights
        task = generate_property_insights.delay()
        return {"success": True, "message": "Insight generation queued", "task_id": task.id}

    def _cmd_update_clusters(self, params):
        from home.tasks import update_topic_clusters
        task = update_topic_clusters.delay()
        return {"success": True, "message": "Cluster update queued", "task_id": task.id}

    def _cmd_build_snapshots(self, params):
        from home.tasks import build_sentiment_snapshots
        task = build_sentiment_snapshots.delay()
        return {"success": True, "message": "Snapshot build queued", "task_id": task.id}


