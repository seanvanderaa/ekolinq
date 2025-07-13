# gcs_db_backup.py
"""Backup the PickupRequest table to Google Cloud Storage as a CSV.

* Creates a Flask app and pushes an application context **before** accessing the DB
  or the app logger.
* Works both locally (`python gcs_db_backup.py`) and in a Render Cron Job.
* Logs to **STDOUT** (Render captures it) *and* to an optional `backup.log`
  file beside the script—handy when you run it ad‑hoc on a dev machine.

Environment variables
---------------------
GOOGLE_APPLICATION_CREDENTIALS   → service‑account JSON path
GCS_BUCKET                       → bucket name (defaults to ekolinq_backup)
GCS_KMS_KEY                      → *(optional)* CMEK key
LOG_TO_FILE                      → if set to 1, also write `backup.log`
"""

from __future__ import annotations

import csv
import datetime as _dt
import logging
import os
from pathlib import Path
from typing import Any

from google.cloud import storage
from sqlalchemy import or_

from app import create_app          # Flask app factory
from models import db, PickupRequest

# ─── Logging setup ───────────────────────────────────────────────────────────

LOGGER_NAME = "gcs_db_backup"
log_handlers: list[logging.Handler] = [logging.StreamHandler()]
if os.getenv("LOG_TO_FILE") == "1":
    log_path = Path(__file__).with_name("backup.log")
    log_handlers.append(logging.FileHandler(log_path))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger(LOGGER_NAME)

# ─── Constants ───────────────────────────────────────────────────────────────

SKIP_NOTE = "Imported via import-backfill CLI"
DEFAULT_BUCKET = "ekolinq_backup"
DUMP_PREFIX = "pickup_requests_"
BATCH_SIZE = 500

# ─── Helpers ────────────────────────────────────────────────────────────────

def _timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _open_blob(bucket: storage.Bucket, object_name: str) -> storage.Blob:
    blob = bucket.blob(object_name)
    if kms_key := os.getenv("GCS_KMS_KEY"):
        blob.kms_key_name = kms_key
        logger.debug("Using CMEK key: %s", kms_key)
    return blob


# ─── Main routine ────────────────────────────────────────────────────────────

def dump_to_gcs() -> None:
    """Push the PickupRequest table into GCS as a CSV."""

    bucket_name = os.getenv("GCS_BUCKET", DEFAULT_BUCKET)
    object_name = f"{DUMP_PREFIX}{_timestamp()}.csv"

    logger.info("Starting backup → gs://%s/%s", bucket_name, object_name)

    app = create_app()
    with app.app_context():
        try:
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = _open_blob(bucket, object_name)

            columns = [c.name for c in PickupRequest.__table__.columns]
            row_count = 0

            with blob.open("w", newline="") as fp:
                writer = csv.writer(fp)
                writer.writerow(columns)

                query = (
                    PickupRequest.query
                    .filter(
                        or_(
                            PickupRequest.admin_notes.is_(None),
                            PickupRequest.admin_notes != SKIP_NOTE,
                        )
                    )
                    .yield_per(BATCH_SIZE)
                )

                for row in query:
                    writer.writerow([getattr(row, col) for col in columns])
                    row_count += 1

            db.session.commit()
            logger.info(
                "Backup complete: gs://%s/%s (rows=%d)", bucket_name, object_name, row_count
            )
        except Exception as exc:   # noqa: BLE001
            logger.exception("Backup FAILED: %s", exc)
            raise


if __name__ == "__main__":
    dump_to_gcs()
