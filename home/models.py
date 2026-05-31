# home/models.py
"""
Data models for the Review Sentiment & NLP Analysis layer.

Design decisions:
  - Review is the atomic unit. One row per guest review.
    Stores raw text, computed sentiment, topics, and embedding.
  - TopicCluster stores the discovered topics (LDA / LLM-extracted).
    Many home belong to many topics via ReviewTopic.
  - SentimentSnapshot is a daily aggregate per property — used by
    the dashboard to plot trends without re-querying all home.
  - PropertyInsight stores the LLM-generated narrative summary for
    a property — refreshed weekly.

Language support:
  East African context means we track detected language per review
  and use AfriSenti-aware scoring for sw (Swahili) home.
"""
from __future__ import annotations
import uuid
from django.db import models
from django.conf import settings


class Review(models.Model):
    """
    A single guest/host review — ingested from Kaggle CSV,
    AfriSenti TSV, or submitted live via the API.
    """

    SOURCE_KAGGLE    = "kaggle"
    SOURCE_AFRISENTI = "afrisenti"
    SOURCE_LIVE      = "live"
    SOURCE_CHOICES   = [
        (SOURCE_KAGGLE,    "Kaggle 515k"),
        (SOURCE_AFRISENTI, "AfriSenti"),
        (SOURCE_LIVE,      "Live submission"),
    ]

    SENTIMENT_POSITIVE = "positive"
    SENTIMENT_NEGATIVE = "negative"
    SENTIMENT_NEUTRAL  = "neutral"
    SENTIMENT_CHOICES  = [
        (SENTIMENT_POSITIVE, "Positive"),
        (SENTIMENT_NEGATIVE, "Negative"),
        (SENTIMENT_NEUTRAL,  "Neutral"),
    ]

    LANG_EN = "en"
    LANG_SW = "sw"
    LANG_OTHER = "other"
    LANG_CHOICES = [
        (LANG_EN,    "English"),
        (LANG_SW,    "Swahili"),
        (LANG_OTHER, "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Raw content ────────────────────────────────────────────────────────
    property_name    = models.CharField(max_length=255, db_index=True)
    property_id      = models.CharField(max_length=100, blank=True, db_index=True)
    reviewer_score   = models.FloatField(null=True, blank=True)  # 1–10
    positive_text    = models.TextField(blank=True)
    negative_text    = models.TextField(blank=True)
    # Combined field used for analysis (positive + negative concatenated)
    full_text        = models.TextField(blank=True)
    tags             = models.JSONField(default=list, blank=True)  # ["Leisure trip", "Couple"]

    # ── Provenance ─────────────────────────────────────────────────────────
    source           = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True)
    language         = models.CharField(max_length=10, choices=LANG_CHOICES, default=LANG_EN, db_index=True)
    review_date      = models.DateField(null=True, blank=True, db_index=True)
    external_id      = models.CharField(max_length=100, blank=True, db_index=True)

    # ── Computed sentiment ─────────────────────────────────────────────────
    sentiment        = models.CharField(
        max_length=10, choices=SENTIMENT_CHOICES,
        null=True, blank=True, db_index=True,
    )
    sentiment_score  = models.FloatField(null=True, blank=True)  # 0–1 confidence
    sentiment_model  = models.CharField(max_length=50, blank=True)  # which model scored it

    # ── Topic extraction ───────────────────────────────────────────────────
    # Denormalised list of topic labels for fast filtering
    topic_labels     = models.JSONField(default=list, blank=True)
    # Key phrases extracted by LLM
    key_phrases      = models.JSONField(default=list, blank=True)
    # Aspect scores: {"cleanliness": 0.8, "staff": 0.9, "location": 0.7}
    aspect_scores    = models.JSONField(default=dict, blank=True)

    # ── Embedding ──────────────────────────────────────────────────────────
    # Stored using pgvector — same field type as EnterpriseBaseModel
    # We declare it manually since Review doesn't extend EnterpriseBaseModel
    # (intentional — we don't want audit trail / soft delete on review rows)
    embedding        = models.JSONField(null=True, blank=True)
    # Will be replaced by VectorField in migration:
    # embedding = VectorField(dimensions=1536, null=True, blank=True)

    # ── Flags ──────────────────────────────────────────────────────────────
    is_processed     = models.BooleanField(default=False, db_index=True)
    is_flagged       = models.BooleanField(default=False)  # spam / off-topic
    processing_error = models.TextField(blank=True)

    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-review_date", "-created_at"]
        indexes  = [
            models.Index(fields=["property_id", "sentiment", "review_date"]),
            models.Index(fields=["source", "language", "is_processed"]),
            models.Index(fields=["sentiment", "review_date"]),
        ]
        verbose_name        = "Review"
        verbose_name_plural = "home"

    def __str__(self):
        score = f"{self.reviewer_score:.1f}" if self.reviewer_score else "?"
        return f"{self.property_name} — {score}/10 ({self.sentiment or 'unscored'})"

    @property
    def display_text(self) -> str:
        """Return the most useful text for display / embedding."""
        parts = []
        if self.positive_text and self.positive_text.strip() not in ("", "No Positive"):
            parts.append(self.positive_text.strip())
        if self.negative_text and self.negative_text.strip() not in ("", "No Negative"):
            parts.append(self.negative_text.strip())
        return " ".join(parts) or self.full_text

    @property
    def combined_text(self) -> str:
        return f"{self.positive_text} {self.negative_text}".strip()


class TopicCluster(models.Model):
    """
    A discovered topic cluster — either LDA-extracted or LLM-named.
    home are linked via the denormalised topic_labels field on Review
    for read performance, and via ReviewTopic for analytics.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label       = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    keywords    = models.JSONField(default=list)   # top-10 keywords for this topic
    review_count = models.IntegerField(default=0)
    avg_sentiment_score = models.FloatField(default=0.5)  # 0=very negative, 1=very positive
    # Which properties are most affected by this topic
    top_properties = models.JSONField(default=list)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-review_count"]
        verbose_name        = "Topic cluster"
        verbose_name_plural = "Topic clusters"

    def __str__(self):
        return f"{self.label} ({self.review_count} home)"


class SentimentSnapshot(models.Model):
    """
    Daily aggregate sentiment stats per property.
    Pre-computed by a Celery Beat task so the dashboard renders instantly.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property_id     = models.CharField(max_length=100, db_index=True)
    property_name   = models.CharField(max_length=255)
    snapshot_date   = models.DateField(db_index=True)

    total_home   = models.IntegerField(default=0)
    positive_count  = models.IntegerField(default=0)
    negative_count  = models.IntegerField(default=0)
    neutral_count   = models.IntegerField(default=0)
    avg_score       = models.FloatField(default=0.0)      # 0–10 reviewer score avg
    avg_sentiment   = models.FloatField(default=0.5)      # 0–1 sentiment confidence avg

    # Top topics for this day
    top_topics      = models.JSONField(default=list)
    # Aspect scores averaged across all home for the day
    aspect_averages = models.JSONField(default=dict)

    class Meta:
        unique_together = [("property_id", "snapshot_date")]
        ordering        = ["-snapshot_date"]
        indexes         = [
            models.Index(fields=["property_id", "snapshot_date"]),
            models.Index(fields=["snapshot_date", "avg_sentiment"]),
        ]
        verbose_name        = "Sentiment snapshot"
        verbose_name_plural = "Sentiment snapshots"

    def __str__(self):
        return f"{self.property_name} — {self.snapshot_date} ({self.total_home} home)"

    @property
    def positive_pct(self) -> float:
        if not self.total_home:
            return 0.0
        return round(self.positive_count / self.total_home * 100, 1)

    @property
    def negative_pct(self) -> float:
        if not self.total_home:
            return 0.0
        return round(self.negative_count / self.total_home * 100, 1)


class PropertyInsight(models.Model):
    """
    LLM-generated narrative insight for a property.
    Refreshed weekly by a Celery Beat task.
    Surfaces in the admin dashboard and the command palette.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property_id     = models.CharField(max_length=100, unique=True, db_index=True)
    property_name   = models.CharField(max_length=255)

    # LLM-generated narrative
    strength_summary   = models.TextField(blank=True)   # What guests love
    weakness_summary   = models.TextField(blank=True)   # What guests dislike
    actionable_advice  = models.TextField(blank=True)   # What to fix
    overall_narrative  = models.TextField(blank=True)   # One-paragraph summary

    # Aggregate stats
    total_home      = models.IntegerField(default=0)
    avg_reviewer_score = models.FloatField(default=0.0)
    sentiment_breakdown = models.JSONField(default=dict)  # {"positive": N, "negative": N, "neutral": N}
    top_topics         = models.JSONField(default=list)
    aspect_scores      = models.JSONField(default=dict)

    # Swahili-specific insight (East African context)
    swahili_feedback_count = models.IntegerField(default=0)
    swahili_sentiment_avg  = models.FloatField(null=True, blank=True)

    generated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-total_home"]
        verbose_name        = "Property insight"
        verbose_name_plural = "Property insights"

    def __str__(self):
        return f"Insight: {self.property_name} ({self.total_home} home)"
    
