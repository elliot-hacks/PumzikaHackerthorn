# home/management/commands/build_snapshots.py
"""
Django management command to build daily sentiment snapshots.
Pre-computes aggregate statistics per property for fast dashboard rendering.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone
from datetime import datetime, date, timedelta
from home.models import Review, SentimentSnapshot
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Build daily sentiment snapshots for properties (pre-computed aggregates)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Specific date to build snapshot for (YYYY-MM-DD format)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days to build snapshots for (default: 7)",
        )
        parser.add_argument(
            "--property",
            type=str,
            help="Build snapshots for a specific property ID only",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Build snapshots for all dates with reviews",
        )
        parser.add_argument(
            "--regenerate",
            action="store_true",
            help="Regenerate snapshots even if they already exist",
        )
        parser.add_argument(
            "--async",
            dest="async_mode",
            action="store_true",
            help="Queue as Celery task instead of running synchronously",
        )

    def handle(self, *args, **options):
        specific_date = options["date"]
        days = options["days"]
        property_id = options["property"]
        build_all = options["all"]
        regenerate = options["regenerate"]
        async_mode = options["async_mode"]

        if async_mode:
            from home.tasks import build_sentiment_snapshots
            task = build_sentiment_snapshots.delay()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued snapshot building (Task ID: {task.id})"
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    "Note: Async task builds all snapshots. "
                    "For specific dates, run synchronously."
                )
            )
            return

        # Synchronous execution
        if specific_date:
            # Build for specific date
            try:
                target_date = datetime.strptime(specific_date, "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR("Invalid date format. Use YYYY-MM-DD")
                )
                return

            self._build_snapshot_for_date(target_date, property_id, regenerate)

        elif build_all:
            # Build for all dates that have reviews
            self._build_all_snapshots(property_id, regenerate)

        else:
            # Build for last N days
            today = date.today()
            self.stdout.write(f"Building snapshots for last {days} days...")

            for i in range(days):
                target_date = today - timedelta(days=i)
                self._build_snapshot_for_date(target_date, property_id, regenerate)

        # Show summary
        self._show_snapshot_summary()

    def _build_snapshot_for_date(self, target_date, property_id=None, regenerate=False):
        """Build snapshots for a specific date."""
        self.stdout.write(f"\n📅 Building snapshots for {target_date}...")

        # Get reviews for this date
        reviews = Review.objects.filter(
            review_date=target_date,
            is_processed=True
        )

        if property_id:
            reviews = reviews.filter(property_id=property_id)

        # Group by property
        properties = reviews.values("property_id", "property_name").distinct()

        if not properties:
            self.stdout.write(
                self.style.WARNING(f"  No processed reviews found for {target_date}")
            )
            return

        created = 0
        updated = 0
        skipped = 0

        for prop in properties:
            prop_id = prop["property_id"]
            prop_name = prop["property_name"]

            # Check if snapshot already exists
            existing = SentimentSnapshot.objects.filter(
                property_id=prop_id,
                snapshot_date=target_date
            ).first()

            if existing and not regenerate:
                skipped += 1
                continue

            # Calculate aggregates for this property and date
            prop_reviews = reviews.filter(property_id=prop_id)

            total = prop_reviews.count()
            positive = prop_reviews.filter(sentiment=Review.SENTIMENT_POSITIVE).count()
            negative = prop_reviews.filter(sentiment=Review.SENTIMENT_NEGATIVE).count()
            neutral = prop_reviews.filter(sentiment=Review.SENTIMENT_NEUTRAL).count()

            avg_score = prop_reviews.aggregate(Avg("reviewer_score"))["reviewer_score__avg"] or 0.0
            avg_sentiment = prop_reviews.aggregate(Avg("sentiment_score"))["sentiment_score__avg"] or 0.5

            # Get top topics for this property on this date
            from collections import Counter
            all_topics = []
            for review in prop_reviews:
                all_topics.extend(review.topic_labels)
            top_topics = Counter(all_topics).most_common(5)

            # Calculate aspect averages
            aspect_sums = {}
            aspect_counts = {}
            for review in prop_reviews:
                for aspect, score in review.aspect_scores.items():
                    if aspect not in aspect_sums:
                        aspect_sums[aspect] = 0
                        aspect_counts[aspect] = 0
                    aspect_sums[aspect] += score
                    aspect_counts[aspect] += 1

            aspect_averages = {}
            for aspect in aspect_sums:
                if aspect_counts[aspect] > 0:
                    aspect_averages[aspect] = round(
                        aspect_sums[aspect] / aspect_counts[aspect], 2
                    )

            # Create or update snapshot
            snapshot, created_flag = SentimentSnapshot.objects.update_or_create(
                property_id=prop_id,
                snapshot_date=target_date,
                defaults={
                    "property_name": prop_name,
                    "total_home": total,
                    "positive_count": positive,
                    "negative_count": negative,
                    "neutral_count": neutral,
                    "avg_score": round(avg_score, 2),
                    "avg_sentiment": round(avg_sentiment, 3),
                    "top_topics": [topic for topic, count in top_topics],
                    "aspect_averages": aspect_averages,
                }
            )

            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ Created: {created}, Updated: {updated}, Skipped: {skipped}"
            )
        )

    def _build_all_snapshots(self, property_id=None, regenerate=False):
        """Build snapshots for all dates that have reviews."""
        self.stdout.write("Building snapshots for all dates with reviews...")

        # Get all unique dates with processed reviews
        dates = (
            Review.objects
            .filter(is_processed=True)
            .dates("review_date", "day")
            .order_by("-review_date")
        )

        if property_id:
            dates = dates.filter(review__property_id=property_id)

        total_dates = len(dates)
        self.stdout.write(f"Found {total_dates} dates with reviews")

        for target_date in dates:
            self._build_snapshot_for_date(target_date, property_id, regenerate)

    def _show_snapshot_summary(self):
        """Show summary of existing snapshots."""
        total_snapshots = SentimentSnapshot.objects.count()
        total_properties = SentimentSnapshot.objects.values("property_id").distinct().count()

        if total_snapshots == 0:
            self.stdout.write("\n" + self.style.WARNING("No snapshots found in database"))
        else:
            latest_date = SentimentSnapshot.objects.latest("snapshot_date").snapshot_date
            self.stdout.write("\n" + self.style.SUCCESS("📊 Sentiment Snapshot Summary:"))
            self.stdout.write(f"  Total snapshots: {total_snapshots}")
            self.stdout.write(f"  Properties covered: {total_properties}")
            self.stdout.write(f"  Latest snapshot date: {latest_date}")

            # Show recent snapshots
            recent = SentimentSnapshot.objects.order_by("-snapshot_date", "-total_home")[:5]
            if recent:
                self.stdout.write("\n  Most recent snapshots:")
                for snap in recent:
                    self.stdout.write(
                        f"    • {snap.property_name} ({snap.snapshot_date}): "
                        f"{snap.total_home} reviews, "
                        f"{snap.positive_pct}% positive"
                    )