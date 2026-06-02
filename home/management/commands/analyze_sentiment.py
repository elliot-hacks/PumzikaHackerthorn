# home/management/commands/analyze_sentiment.py
"""
Django management command to trigger sentiment analysis on unprocessed reviews.
Used by the command palette for quick NLP operations.
"""
from django.core.management.base import BaseCommand, CommandError
from home.models import Review
from home.nlp import review_pipeline
from home.tasks import bulk_process_home


class Command(BaseCommand):
    help = "Analyze sentiment for unprocessed reviews using NLP pipeline"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of reviews to process in this run (default: 100)",
        )
        parser.add_argument(
            "--async",
            dest="async_mode",
            action="store_true",
            help="Queue as Celery task instead of running synchronously",
        )
        parser.add_argument(
            "--property",
            type=str,
            help="Filter by property ID",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        async_mode = options["async_mode"]
        property_id = options["property"]

        # Count unprocessed reviews
        unprocessed_qs = Review.objects.filter(is_processed=False)
        if property_id:
            unprocessed_qs = unprocessed_qs.filter(property_id=property_id)

        total_unprocessed = unprocessed_qs.count()

        if total_unprocessed == 0:
            self.stdout.write(
                self.style.SUCCESS("All reviews have been processed!")
            )
            return

        self.stdout.write(
            f"Found {total_unprocessed} unprocessed reviews"
        )

        if async_mode:
            # Queue as Celery task
            if property_id:
                self.stdout.write(
                    self.style.WARNING(
                        "Async mode doesn't support property filtering, "
                        "processing all unprocessed reviews"
                    )
                )
            task = bulk_process_home.delay(batch_size=batch_size)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued sentiment analysis task (ID: {task.id})"
                )
            )
        else:
            # Run synchronously
            self.stdout.write("Processing reviews synchronously...")
            pipeline = review_pipeline
            result = pipeline.process_batch(unprocessed_qs, limit=batch_size)

            self.stdout.write()

