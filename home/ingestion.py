# reviews/ingestion.py
"""
Data ingestion pipeline for the two starter datasets.

Dataset 1 — Kaggle 515K Hotel Reviews (CSV)
  Columns: Hotel_Address, Additional_Number_of_Scoring, Review_Date,
           Average_Score, Hotel_Name, Reviewer_Nationality,
           Negative_Review, Review_Total_Negative_Word_Counts,
           Total_Number_of_Reviews, Positive_Review,
           Review_Total_Positive_Word_Counts, Total_Number_of_Reviews_Reviewer_Has_Given,
           Reviewer_Score, Tags, days_since_review, lat, lng

Dataset 2 — AfriSenti (TSV / parquet)
  Columns: tweet, label, language
  label: positive / negative / neutral

Usage:
  from home.ingestion import KaggleIngester, AfriSentiIngester
  KaggleIngester().ingest("path/to/Hotel_Reviews.csv", batch_size=1000)
  AfriSentiIngester().ingest("path/to/sw.tsv")
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from typing import Iterator

logger = logging.getLogger(__name__)


# ── Kaggle 515K Ingester ───────────────────────────────────────────────────

class KaggleIngester:
    """
    Streams the 515K CSV in batches to avoid loading it all into memory.
    Deduplicates by (property_name, reviewer_score, text hash).
    """

    DATE_FORMATS = ["%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y"]

    def ingest(
        self,
        csv_path: str,
        batch_size: int = 500,
        limit: int = None,
        queue_nlp: bool = True,
    ) -> dict:
        """
        Ingest the Kaggle CSV file into Review rows.

        Args:
            csv_path:  Absolute path to Hotel_Reviews.csv
            batch_size: DB bulk_create batch size
            limit:     If set, stop after this many rows (for testing)
            queue_nlp: If True, queue Celery NLP tasks for each batch

        Returns:
            {"ingested": N, "skipped": N, "errors": N}
        """
        from home.models import Review

        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        ingested = skipped = errors = 0
        batch: list[Review] = []

        for i, row in enumerate(self._stream_csv(csv_path)):
            if limit and i >= limit:
                break
            try:
                review = self._row_to_review(row)
                if review is None:
                    skipped += 1
                    continue
                batch.append(review)
                if len(batch) >= batch_size:
                    saved, sk = self._flush(batch, queue_nlp)
                    ingested += saved
                    skipped  += sk
                    batch = []
                    logger.info(f"Kaggle ingestion: {ingested} ingested so far...")
            except Exception as e:
                errors += 1
                logger.debug(f"Row {i} error: {e}")
                continue

        # Final batch
        if batch:
            saved, sk = self._flush(batch, queue_nlp)
            ingested += saved
            skipped  += sk

        result = {"ingested": ingested, "skipped": skipped, "errors": errors}
        logger.info(f"Kaggle ingestion complete: {result}")
        return result

    def _stream_csv(self, path: str) -> Iterator[dict]:
        """Lazily stream rows from the CSV."""
        with open(path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield row

    def _row_to_review(self, row: dict):
        """Convert a CSV row dict to a Review instance (unsaved)."""
        from home.models import Review

        hotel_name     = row.get("Hotel_Name", "").strip()
        positive_text  = row.get("Positive_Review", "").strip()
        negative_text  = row.get("Negative_Review", "").strip()

        # Skip completely empty reviews
        if not hotel_name:
            return None
        pos_empty = positive_text in ("", "No Positive", "Nothing")
        neg_empty = negative_text in ("", "No Negative", "Nothing")
        if pos_empty and neg_empty:
            return None

        # Build external_id for deduplication
        import hashlib
        raw     = f"{hotel_name}|{positive_text}|{negative_text}"
        ext_id  = hashlib.md5(raw.encode()).hexdigest()

        # Parse reviewer score
        try:
            rs = float(row.get("Reviewer_Score", "") or 0) or None
        except (ValueError, TypeError):
            rs = None

        # Parse date
        review_date = None
        date_str    = row.get("Review_Date", "").strip()
        for fmt in self.DATE_FORMATS:
            try:
                review_date = datetime.strptime(date_str, fmt).date()
                break
            except (ValueError, TypeError):
                continue

        # Tags
        tags_raw = row.get("Tags", "[]")
        try:
            import ast
            tags = [t.strip() for t in ast.literal_eval(tags_raw) if t.strip()]
        except Exception:
            tags = []

        # Property ID from lat/lng (unique per hotel, approximated)
        lat = row.get("lat", "").strip()
        lng = row.get("lng", "").strip()
        prop_id = f"hotel_{hashlib.md5(hotel_name.encode()).hexdigest()[:12]}"

        return Review(
            property_name  = hotel_name[:255],
            property_id    = prop_id,
            reviewer_score = rs,
            positive_text  = positive_text[:5000],
            negative_text  = negative_text[:5000],
            full_text      = f"{positive_text} {negative_text}".strip()[:10000],
            tags           = tags,
            source         = Review.SOURCE_KAGGLE,
            language       = Review.LANG_EN,  # Kaggle dataset is English
            review_date    = review_date,
            external_id    = ext_id,
            is_processed   = False,
        )

    def _flush(self, batch: list, queue_nlp: bool) -> tuple[int, int]:
        """Bulk insert a batch, skip duplicates."""
        from home.models import Review

        # Filter out existing external_ids
        ext_ids    = [r.external_id for r in batch if r.external_id]
        existing   = set(
            Review.objects.filter(external_id__in=ext_ids)
            .values_list("external_id", flat=True)
        )
        new_batch  = [r for r in batch if r.external_id not in existing]
        skipped    = len(batch) - len(new_batch)

        if not new_batch:
            return 0, skipped

        created    = Review.objects.bulk_create(new_batch, ignore_conflicts=True)
        saved      = len(created)

        if queue_nlp and saved:
            self._queue_nlp(created)

        return saved, skipped

    @staticmethod
    def _queue_nlp(reviews: list) -> None:
        try:
            from home.tasks import process_review_task
            from celery import group
            group(
                process_review_task.s(str(r.pk)) for r in reviews
            ).apply_async()
        except Exception as e:
            logger.debug(f"Could not queue NLP tasks: {e}")


# ── AfriSenti Ingester ─────────────────────────────────────────────────────

class AfriSentiIngester:
    """
    Ingests the AfriSenti Swahili sentiment TSV/parquet.
    Columns: tweet, label, language
    label values: positive / negative / neutral
    """

    LABEL_MAP = {
        "positive": "positive",
        "negative": "negative",
        "neutral":  "neutral",
        "pos":      "positive",
        "neg":      "negative",
        "neu":      "neutral",
    }

    def ingest(
        self,
        file_path: str,
        batch_size: int = 500,
        queue_nlp: bool = False,  # AfriSenti labels are ground truth — no NLP needed
    ) -> dict:
        """
        Ingest AfriSenti TSV or parquet file.
        Swahili tweets are stored with pre-computed labels as ground truth.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".tsv", ".txt", ".csv"):
            rows = self._stream_tsv(file_path, ext)
        elif ext in (".parquet",):
            rows = self._stream_parquet(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        return self._process_rows(rows, batch_size, queue_nlp)

    def _stream_tsv(self, path: str, ext: str) -> Iterator[dict]:
        delimiter = "\t" if ext == ".tsv" else ","
        with open(path, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                yield row

    def _stream_parquet(self, path: str) -> Iterator[dict]:
        try:
            import pandas as pd
            df = pd.read_parquet(path)
            for _, row in df.iterrows():
                yield row.to_dict()
        except ImportError:
            raise ImportError("pandas is required to read parquet files: pip install pandas pyarrow")

    def _process_rows(self, rows: Iterator[dict], batch_size: int, queue_nlp: bool) -> dict:
        from home.models import Review
        import hashlib

        ingested = skipped = errors = 0
        batch = []

        for row in rows:
            try:
                tweet = (
                    str(row.get("tweet", "") or row.get("text", "") or "").strip()
                )
                if not tweet:
                    skipped += 1
                    continue

                raw_label = str(
                    row.get("label", "") or row.get("sentiment", "") or ""
                ).lower().strip()
                label = self.LABEL_MAP.get(raw_label, "neutral")

                lang = str(row.get("language", "sw") or "sw").lower()[:5]
                if lang not in ("en", "sw"):
                    lang = "sw"

                ext_id = hashlib.md5(tweet.encode()).hexdigest()

                review = Review(
                    property_name  = "AfriSenti Training",
                    property_id    = "afrisenti_corpus",
                    positive_text  = tweet if label == "positive" else "",
                    negative_text  = tweet if label == "negative" else "",
                    full_text      = tweet,
                    source         = Review.SOURCE_AFRISENTI,
                    language       = lang,
                    external_id    = ext_id,
                    # Pre-assign ground-truth label — no NLP needed
                    sentiment      = label,
                    sentiment_score= 0.90,
                    sentiment_model= "afrisenti_groundtruth",
                    is_processed   = True,  # Already labelled
                )
                batch.append(review)

                if len(batch) >= batch_size:
                    ingested += self._flush_afrisenti(batch)
                    batch = []

            except Exception as e:
                errors += 1
                logger.debug(f"AfriSenti row error: {e}")

        if batch:
            ingested += self._flush_afrisenti(batch)

        result = {"ingested": ingested, "skipped": skipped, "errors": errors}
        logger.info(f"AfriSenti ingestion complete: {result}")
        return result

    @staticmethod
    def _flush_afrisenti(batch: list) -> int:
        from home.models import Review
        existing = set(
            Review.objects.filter(
                external_id__in=[r.external_id for r in batch]
            ).values_list("external_id", flat=True)
        )
        new = [r for r in batch if r.external_id not in existing]
        if not new:
            return 0
        Review.objects.bulk_create(new, ignore_conflicts=True)
        return len(new)
    
