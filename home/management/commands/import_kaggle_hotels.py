# home/management/commands/import_kaggle_hotels.py
"""
Django management command to import the Kaggle 515K Hotel Reviews dataset.
Usage: python manage.py import_kaggle_hotels --csv-path path/to/Hotel_Reviews.csv --batch-size 500
"""
import csv
import logging
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from home.models import Review

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import Kaggle 515K Hotel Reviews dataset"

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-path",
            type=str,
            required=True,
            help="Path to the Hotel_Reviews.csv file",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Batch size for bulk creation (default: 500)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of reviews to import (for testing)",
        )
        parser.add_argument(
            "--queue-nlp",
            action="store_true",
            help="Queue NLP processing for imported reviews",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        batch_size = options["batch_size"]
        limit = options["limit"]
        queue_nlp = options["queue_nlp"]

        self.stdout.write(f"Importing Kaggle Hotel Reviews from: {csv_path}")
        self.stdout.write(f"Batch size: {batch_size}")
        if limit:
            self.stdout.write(f"Limit: {limit} reviews")

        # Check if file exists
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                # Read just the header to validate
                reader = csv.reader(f)
                header = next(reader)
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f"File not found: {csv_path}")
            )
            return
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error reading file: {e}")
            )
            return

        self.stdout.write(f"CSV columns: {', '.join(header)}")

        # Parse and import reviews
        imported = 0
        skipped = 0
        batch = []

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    # Parse review date
                    review_date = None
                    if row.get("Review_Date"):
                        try:
                            review_date = datetime.strptime(
                                row["Review_Date"], "%m/%d/%Y"
                            ).date()
                        except ValueError:
                            try:
                                review_date = datetime.strptime(
                                    row["Review_Date"], "%Y-%m-%d"
                                ).date()
                            except ValueError:
                                pass

                    # Parse tags
                    tags = []
                    if row.get("Tags"):
                        # Tags are stored as a string representation of a list
                        tags_str = row["Tags"].strip().strip("[]")
                        if tags_str:
                            tags = [
                                tag.strip().strip("'\"")
                                for tag in tags_str.split(",")
                            ]

                    # Clean review text
                    positive_text = row.get("Positive_Review", "").strip()
                    negative_text = row.get("Negative_Review", "").strip()

                    # Skip if both are empty or "No Negative"/"No Positive"
                    if (
                        positive_text in ("", "No Positive")
                        and negative_text in ("", "No Negative")
                    ):
                        skipped += 1
                        continue

                    # Create Review object
                    review = Review(
                        property_name=row.get("Hotel_Name", "").strip(),
                        property_id=f"kaggle_{row.get('Hotel_Name', '').strip().replace(' ', '_')}",
                        reviewer_score=float(row["Reviewer_Score"])
                        if row.get("Reviewer_Score")
                        else None,
                        positive_text=positive_text
                        if positive_text not in ("", "No Positive")
                        else "",
                        negative_text=negative_text
                        if negative_text not in ("", "No Negative")
                        else "",
                        tags=tags,
                        source=Review.SOURCE_KAGGLE,
                        language=Review.LANG_EN,  # Kaggle dataset is English
                        review_date=review_date,
                        external_id="",  # No external ID in this dataset, use empty string
                    )

                    batch.append(review)

                    # Bulk create in batches
                    if len(batch) >= batch_size:
                        with transaction.atomic():
                            Review.objects.bulk_create(batch)
                        imported += len(batch)
                        self.stdout.write(
                            f"  Imported {imported} reviews...",
                            ending="\r",
                        )
                        batch = []

                    # Check limit
                    if limit and imported + len(batch) >= limit:
                        break

                except Exception as e:
                    logger.warning(f"Error importing row: {e}")
                    skipped += 1

        # Import remaining batch
        if batch:
            with transaction.atomic():
                Review.objects.bulk_create(batch)
            imported += len(batch)

        self.stdout.write("\n")
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully imported {imported} reviews"
            )
        )
        if skipped > 0:
            self.stdout.write(
                self.style.WARNING(f"Skipped {skipped} invalid rows")
            )

        # Queue NLP processing if requested
        if queue_nlp and imported > 0:
            from home.tasks import bulk_process_home

            self.stdout.write("Queuing NLP processing...")
            task = bulk_process_home.delay(batch_size=100)
            self.stdout.write(
                self.style.SUCCESS(f"NLP task queued (ID: {task.id})")
            )

        # Show summary
        total = Review.objects.count()
        processed = Review.objects.filter(is_processed=True).count()
        self.stdout.write(f"\nTotal reviews in database: {total}")
        self.stdout.write(f"Processed reviews: {processed}")
        