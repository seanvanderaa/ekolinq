import os
import datetime
import re
import gspread
from google.oauth2.service_account import Credentials
from flask import current_app
from models import PickupRequest, db

###############################################################################
# Mapping helpers
###############################################################################

#: Spreadsheet column → ORM attribute.
_EXPLICIT_FIELD_MAP = {
    "Request ID": "request_id",
    "First Name": "fname",
    "Last Name": "lname",
    "Phone": "phone_number",
    "Zipcode": "zipcode",
    "Gated": "gated",
    "Completion Info": "pickup_complete_info",
}

#: Title of the “last updated” column in the sheet.
_TIMESTAMP_COL = "Exported At"

#: Admin note that should *never* be exported.
_ADMIN_SKIP_NOTE = "Imported via import-backfill CLI"

# ----------------------------------------------------------------------------
# Utility helpers
# ----------------------------------------------------------------------------

def _snake_case(s: str) -> str:
    """Convert a spreadsheet header (title‑case with spaces) to snake_case."""
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s).strip()
    return re.sub(r"\s+", "_", s).lower()


def _header_to_attr(header: str) -> str | None:
    """Map a sheet header to a :class:`PickupRequest` attribute (or ``None``)."""
    if header == _TIMESTAMP_COL:
        return None
    return _EXPLICIT_FIELD_MAP.get(header, _snake_case(header))


###############################################################################
# Main export function
###############################################################################

def weekly_export() -> None:  # noqa: WPS231, WPS430 – readability > strict rules
    """Export completed/incomplete requests to Google Sheets.

    * Tolerant of DB‑schema changes.
    * Skips rows with the admin‑note "Imported via import-backfill CLI".
    * Scrubs PII for exported rows inside the same DB transaction.
    * Emits detailed *non‑PII* logs for observability.
    """

    logger = current_app.logger  # local alias for brevity
    logger.info("[export] Starting weekly export job…")

    # ── Google credentials ───────────────────────────────────────────────────
    creds_path = current_app.config.get(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials/service_account.json"),
    )
    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open("[DO NOT EDIT] EkoLinq Website Requests")
    worksheet = spreadsheet.worksheet("Requests")
    logger.debug("[export] Connected to Google Sheet ‘%s’ / tab ‘%s’.", spreadsheet.title, worksheet.title)

    # ── Build (header -> attribute) map from the sheet itself ────────────────
    header_row: list[str] = worksheet.row_values(1)
    attr_order: list[str | None] = [_header_to_attr(h) for h in header_row]
    logger.debug("[export] Detected %d columns in sheet header.", len(header_row))

    # ── Already‑exported request_ids ─────────────────────────────────────────
    existing_id = {row[0] for row in worksheet.get_all_values()[1:] if row}
    logger.debug("[export] Sheet currently has %d exported requests.", len(existing_id))

    # ── Candidate rows to export ─────────────────────────────────────────────
    candidates: list[PickupRequest] = (
        PickupRequest.query
        .filter(PickupRequest.status.in_(["Complete", "Incomplete"]))
        .all()
    )
    logger.debug("[export] Fetched %d candidate requests (status Complete/Incomplete).", len(candidates))

    new_rows: list[list[str]] = []
    exported_ids: set[str] = set()
    skipped_existing = 0
    skipped_admin = 0

    for req in candidates:
        if req.request_id in existing_id:
            skipped_existing += 1
            logger.debug("[export] Skip existing request_id=%s", req.request_id)
            continue
        if (req.admin_notes or "").strip() == _ADMIN_SKIP_NOTE:
            skipped_admin += 1
            logger.debug("[export] Skip request_id=%s due to admin note filter", req.request_id)
            continue

        row: list[str] = []
        for attr in attr_order:
            if attr is None:
                row.append("«ts»")  # placeholder to be overwritten later
            else:
                value = getattr(req, attr, "")
                row.append(str(value) if value is not None else "")
        new_rows.append(row)
        exported_ids.add(req.request_id)

    logger.info(
        "[export] Prepared %d new rows (skipped %d existing, %d admin‑filtered).",
        len(new_rows), skipped_existing, skipped_admin,
    )

    # ── Bulk‑insert rows ─────────────────────────────────────────────────────
    if new_rows:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ts_col_idx = header_row.index(_TIMESTAMP_COL)
        for row in new_rows:
            row[ts_col_idx] = timestamp
            worksheet.insert_row(row, index=2)
        logger.info("[export] Inserted %d rows into Google Sheet (timestamp %s).", len(new_rows), timestamp)
    else:
        logger.info("[export] No new rows to insert this cycle.")

    # ── Scrub PII of exported rows ───────────────────────────────────────────
    if exported_ids:
        (
            PickupRequest.query
            .filter(PickupRequest.request_id.in_(exported_ids))
            .update({
                "fname": "NA",
                "lname": "NA",
                "email": "NA",
                "phone_number": "NA",
            }, synchronize_session=False)
        )
        logger.debug("[export] PII scrubbed for %d newly exported requests.", len(exported_ids))

    # ── Delete every “Unfinished” request ────────────────────────────────────
    deleted_count = (
        PickupRequest.query
        .filter_by(status="Unfinished")
        .delete(synchronize_session=False)
    )
    logger.debug("[export] Deleted %d ‘Unfinished’ requests.", deleted_count)

    # ── Commit everything in one shot ────────────────────────────────────────
    db.session.commit()
    logger.info(
        "[export] Weekly export complete — %d rows exported, %d unfinished rows deleted.",
        len(new_rows), deleted_count,
    )
