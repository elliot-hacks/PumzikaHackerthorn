# home/management/commands/generate_insights.py
"""
Django management command to generate LLM-powered property insights.
Used by the command palette for quick insight generation.
"""
from django.core.management.base import BaseCommand
from home.models import Review, PropertyInsight
from home.tasks import generate_property_insights
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate AI-powered insights for properties based on review analysis"

    def add_arguments(self, parser):
        parser.add_argument(
            "--property",
            type=str,
            help="Generate insights for a specific property ID",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Generate insights for all properties with sufficient reviews",
        )
        parser.add_argument(
            "--min-reviews",
            type=int,
            default=5,
            help="Minimum number of processed reviews required (default: 5)",
        )
        parser.add_argument(
            "--async",
            dest="async_mode",
            action="store_true",
            help="Queue as Celery task instead of running synchronously",
        )
        parser.add_argument(
            "--regenerate",
            action="store_true",
            help="Regenerate insights even if they already exist",
        )

    def handle(self, *args, **options):
        property_id = options["property"]
        generate_all = options["all"]
        min_reviews = options["min_reviews"]
        async_mode = options["async_mode"]
        regenerate = options["regenerate"]

        if property_id:
            # Generate for specific property
            review_count = Review.objects.filter(
                property_id=property_id,
                is_processed=True
            ).count()

            if review_count < min_reviews:
                self.stdout.write(
                    self.style.WARNING(
                        f"Property {property_id} has only {review_count} processed reviews "
                        f"(minimum: {min_reviews})"
                    )
                )
                return

            if async_mode:
                task = generate_property_insights.delay(property_id=property_id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Queued insight generation for property {property_id} (Task ID: {task.id})"
                    )
                )
            else:
                from home.tasks import _generate_insight_for_property
                _generate_insight_for_property(property_id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated insights for property {property_id}"
                    )
                )

        elif generate_all:
            # Get all properties with sufficient reviews
            from django.db.models import Count
            properties = (
                Review.objects
                .filter(is_processed=True)
                .values("property_id", "property_name")
                .annotate(review_count=Count("id"))
                .filter(review_count__gte=min_reviews)
            )

            if not properties:
                self.stdout.write(
                    self.style.WARNING(
                        f"No properties found with {min_reviews}+ processed reviews"
                    )
                )
                return

            self.stdout.write(
                f"Found {properties.count()} properties with {min_reviews}+ reviews"
            )

            if async_mode:
                task = generate_property_insights.delay()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Queued insight generation for all properties (Task ID: {task.id})"
                    )
                )
            else:
                generated = 0
                for prop in properties[:20]:  # Limit for sync mode
                    try:
                        from home.tasks import _generate_insight_for_property
                        _generate_insight_for_property(prop["property_id"])
                        generated += 1
                        self.stdout.write(
                            f"  ✓ {prop['property_name']} ({prop['review_count']} reviews)"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate insight for {prop['property_id']}: {e}"
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Generated insights for {generated} properties"
                    )
                )
        else:
            # Show status of existing insights
            total_properties = Review.objects.values("property_id").distinct().count()
            properties_with_insights = PropertyInsight.objects.count()

            self.stdout.write("\n📊 Insight Generation Status:")
            self.stdout.write(f"  Total properties: {total_properties}")
            self.stdout.write(f"  Properties with insights: {properties_with_insights}")
            self.stdout.write(
                f"  Properties needing insights: {total_properties - properties_with_insights}"
            )

            # Show properties with most reviews but no insights
            from django.db.models import Count
            needy_properties = (
                Review.objects
                .filter(is_processed=True)
                .exclude(property_id__in=PropertyInsight.objects.values("property_id"))
                .values("property_id", "property_name")
                .annotate(review_count=Count("id"))
                .filter(review_count__gte=min_reviews)
                .order_by("-review_count")[:10]
            )

            if needy_properties:
                self.stdout.write(f"\n🏠 Top {needy_properties.count()} properties needing insights:")
                for prop in needy_properties:
                    self.stdout.write(
                        f"  • {prop['property_name']}: {prop['review_count']} reviews"
                    )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n💡 Run with --all to generate insights for all properties"
                    )
                )