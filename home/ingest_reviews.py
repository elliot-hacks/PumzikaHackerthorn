# home/management/commands/ingest_home.py
"""
Management command for ingesting review datasets.

Usage:
  # Ingest Kaggle CSV (full)
  python manage.py ingest_home --source kaggle --file /data/Hotel_home.csv

  # Ingest first 10 000 rows only (for testing)
  python manage.py ingest_home --source kaggle --file /data/Hotel_home.csv --limit 10000

  # Ingest AfriSenti TSV
  python manage.py ingest_home --source afrisenti --file /data/sw.tsv

  # Run NLP processing immediately (sync, no Celery)
  python manage.py ingest_home --source kaggle --file /data/Hotel_home.csv --process-sync

  # Show current review counts
  python manage.py ingest_home --report
"""

import os
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Ingest hotel review datasets (Kaggle / AfriSenti) into the home app."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["kaggle", "afrisenti"],
                            help="Dataset source")
        parser.add_argument("--file", type=str, help="Path to the dataset file")
        parser.add_argument("--limit", type=int, default=None,
                            help="Max rows to ingest (for testing)")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--process-sync", action="store_true",
                            help="Run NLP pipeline synchronously after ingestion")
        parser.add_argument("--report", action="store_true",
                            help="Show review counts and exit")

    def handle(self, *args, **options):
        if options["report"]:
            self._print_report()
            return

        if not options.get("source"):
            raise CommandError("--source is required. Choose: kaggle or afrisenti")
        if not options.get("file"):
            raise CommandError("--file is required.")

        file_path = options["file"]
        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        source = options["source"]
        self.stdout.write(self.style.HTTP_INFO(
            f"Ingesting {source} dataset from: {file_path}"
        ))

        if source == "kaggle":
            self._ingest_kaggle(file_path, options)
        elif source == "afrisenti":
            self._ingest_afrisenti(file_path, options)

        if options["process_sync"]:
            self._process_sync(options["batch_size"])

    def _ingest_kaggle(self, file_path, options):
        from home.ingestion import KaggleIngester
        result = KaggleIngester().ingest(
            csv_path   = file_path,
            batch_size = options["batch_size"],
            limit      = options["limit"],
            queue_nlp  = not options["process_sync"],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Kaggle ingestion done: {result['ingested']} ingested, "
            f"{result['skipped']} skipped, {result['errors']} errors"
        ))

    def _ingest_afrisenti(self, file_path, options):
        from home.ingestion import AfriSentiIngester
        result = AfriSentiIngester().ingest(file_path=file_path)
        self.stdout.write(self.style.SUCCESS(
            f"AfriSenti ingestion done: {result['ingested']} ingested, "
            f"{result['skipped']} skipped, {result['errors']} errors"
        ))

    def _process_sync(self, batch_size):
        from home.models import Review
        from home.nlp import review_pipeline
        unprocessed = Review.objects.filter(is_processed=False).count()
        self.stdout.write(f"Running NLP on {unprocessed} unprocessed home...")
        result = review_pipeline.process_batch(
            Review.objects.filter(is_processed=False),
            limit=batch_size,
        )
        self.stdout.write(self.style.SUCCESS(
            f"NLP done: {result['succeeded']} succeeded, {result['failed']} failed"
        ))

    def _print_report(self):
        from home.models import Review, TopicCluster, PropertyInsight
        from django.db.models import Count

        total     = Review.objects.count()
        processed = Review.objects.filter(is_processed=True).count()
        self.stdout.write(self.style.HTTP_INFO("\nReview Sentiment Report\n" + "─" * 50))
        self.stdout.write(f"  Total home:     {total}")
        self.stdout.write(f"  Processed:         {processed}")
        self.stdout.write(f"  Unprocessed:       {total - processed}")

        for sent in ("positive", "negative", "neutral"):
            n = Review.objects.filter(sentiment=sent).count()
            self.stdout.write(f"  {sent.title():12s}: {n}")

        for lang, label in (("en", "English"), ("sw", "Swahili"), ("other", "Other")):
            n = Review.objects.filter(language=lang).count()
            self.stdout.write(f"  {label:12s}: {n}")

        self.stdout.write(f"\n  Topic clusters:    {TopicCluster.objects.count()}")
        self.stdout.write(f"  Property insights: {PropertyInsight.objects.count()}")

        