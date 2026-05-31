"""
Django management command to extract topics from reviews and update topic clusters.
Used by the command palette for quick NLP operations.
"""
from django.core.management.base import BaseCommand
from home.models import Review, TopicCluster
from home.nlp import topic_extractor
from home.tasks import update_topic_clusters
from collections import Counter
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Extract topics from reviews and rebuild topic clusters"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reprocess",
            action="store_true",
            help="Re-extract topics from all processed reviews (overwrites existing)",
        )
        parser.add_argument(
            "--update-clusters",
            action="store_true",
            help="Also update TopicCluster aggregates after extraction",
        )
        parser.add_argument(
            "--async",
            dest="async_mode",
            action="store_true",
            help="Queue as Celery task instead of running synchronously",
        )

    def handle(self, *args, **options):
        reprocess = options["reprocess"]
        update_clusters = options["update_clusters"]
        async_mode = options["async_mode"]

        # Get reviews to process
        if reprocess:
            reviews = Review.objects.filter(is_processed=True)
            self.stdout.write(
                f"Re-extracting topics from {reviews.count()} processed reviews"
            )
        else:
            # Only process reviews that have sentiment but no topics
            reviews = Review.objects.filter(
                is_processed=True,
                topic_labels=[],
            )
            self.stdout.write(
                f"Extracting topics from {reviews.count()} reviews without topics"
            )

        if reviews.count() == 0:
            self.stdout.write(
                self.style.SUCCESS("No reviews need topic extraction!")
            )
            return

        # Extract topics for each review
        extracted = 0
        topic_counter = Counter()

        for review in reviews[:200]:  # Limit for sync mode
            text = review.display_text
            if not text:
                continue

            try:
                extraction = topic_extractor.extract(
                    text, language=review.language
                )

                if extraction["topics"]:
                    review.topic_labels = extraction["topics"]
                    review.key_phrases = extraction["key_phrases"]
                    review.save(update_fields=["topic_labels", "key_phrases"])
                    extracted += 1
                    topic_counter.update(extraction["topics"])

            except Exception as e:
                logger.warning(f"Topic extraction failed for review {review.pk}: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Extracted topics for {extracted} reviews"
            )
        )

        # Show topic distribution
        if topic_counter:
            self.stdout.write("\nTop topics discovered:")
            for topic, count in topic_counter.most_common(10):
                self.stdout.write(f"  • {topic}: {count} reviews")

        # Update topic clusters if requested
        if update_clusters:
            if async_mode:
                task = update_topic_clusters.delay()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Queued topic cluster update (ID: {task.id})"
                    )
                )
            else:
                result = update_topic_clusters()
