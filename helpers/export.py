import datetime
import re

import gspread
from flask import current_app
from sqlalchemy import or_
from gspread.utils import rowcol_to_a1

from models import PickupRequest, db
from helpers.google_creds import get_google_credentials

###############################################################################
# Mapping helpers
###############################################################################

#: Spreadsheet column → ORM attribute.
_EXPLICIT_FIELD_MAP = {
    "Request ID": "request_id",
    "Secondary Address": "address2",
    "First Name": "fname",
    "Last Name": "lname",
    "Email Address": "email",
    "Phone": "phone_number",
    "Zipcode": "zipcode",
    "Gated (True or False)": "gated",
    "Pickup Completed Time": "pickup_complete_info",
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

def weekly_export() -> None:  # noqa: WPS231, WPS430
    """Export all PickupRequest rows to Google Sheets, updating or inserting as needed.

    * Exports every request unless admin_notes == _ADMIN_SKIP_NOTE.
    * If a row is not yet in the sheet, inserts it.
    * If already present and Status is not Complete/Incomplete, updates that row.
    * Skips updates for rows already marked Complete/Incomplete in the sheet.
    * Never scrubs or deletes data in the DB.
    """
    logger = current_app.logger
    logger.info("[export] Starting weekly export job…")

    creds = get_google_credentials()
    client = gspread.authorize(creds)
    spreadsheet = client.open("[DO NOT EDIT] EkoLinq Website Requests")
    worksheet = spreadsheet.worksheet("Requests")
    logger.debug("[export] Connected to sheet '%s' / tab '%s'.", spreadsheet.title, worksheet.title)

    # Read header and build mapping
    header_row: list[str] = worksheet.row_values(1)
    attr_order: list[str | None] = [_header_to_attr(h) for h in header_row]
    logger.debug("[export] Detected %d columns in header.", len(header_row))

    # Identify key column indexes
    try:
        reqid_idx = header_row.index("Request ID")
        status_idx = header_row.index("Status")
        ts_idx = header_row.index(_TIMESTAMP_COL)
    except ValueError as e:
        logger.error("[export] Missing required column: %s", e)
        return

    # Load existing sheet rows into map: request_id -> (row_number, status)
    sheet_values = worksheet.get_all_values()
    sheet_map: dict[str, tuple[int, str]] = {}
    for sheet_row_num, row in enumerate(sheet_values[1:], start=2):
        if len(row) > reqid_idx and row[reqid_idx]:
            rid = row[reqid_idx]
            status = row[status_idx] if status_idx < len(row) else ""
            sheet_map[rid] = (sheet_row_num, status)
    logger.debug("[export] Found %d existing rows in sheet.", len(sheet_map))

    # Fetch all PickupRequests, skipping admin-skip notes
    all_reqs = (
        PickupRequest.query
        .filter(
            or_(
                PickupRequest.admin_notes.is_(None),
                PickupRequest.admin_notes != _ADMIN_SKIP_NOTE,
            )
        )
        .all()
    )
    logger.debug("[export] Retrieved %d total requests from DB.", len(all_reqs))

    to_insert: list[PickupRequest] = []
    to_update: list[tuple[PickupRequest, int]] = []
    skipped_complete = skipped_admin = 0

    for req in all_reqs:
        if (req.admin_notes or "").strip() == _ADMIN_SKIP_NOTE:
            skipped_admin += 1
            continue

        mapping = sheet_map.get(req.request_id)
        if mapping is None:
            to_insert.append(req)
        else:
            row_num, sheet_status = mapping
            if sheet_status in ("Complete", "Incomplete"):
                skipped_complete += 1
            else:
                to_update.append((req, row_num))

    logger.info(
        "[export] %d new rows to insert, %d rows to update, skipped %d completed, %d admin-skip.",
        len(to_insert), len(to_update), skipped_complete, skipped_admin,
    )

    # Prepare timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # INSERT new rows at the top
    for req in to_insert:
        row_data: list[str] = []
        for attr in attr_order:
            if attr is None:
                row_data.append(timestamp)
            else:
                val = getattr(req, attr, "")
                row_data.append(str(val) if val is not None else "")
        worksheet.insert_row(row_data, index=2)
        logger.debug("[export] Inserted request_id=%s", req.request_id)

    # Determine sheet column span for updates
    last_col = rowcol_to_a1(1, len(header_row)).replace('1', '')

    # UPDATE existing rows
    for req, row_num in to_update:
        row_data: list[str] = []
        for attr in attr_order:
            if attr is None:
                row_data.append(timestamp)
            else:
                val = getattr(req, attr, "")
                row_data.append(str(val) if val is not None else "")
        cell_range = f"A{row_num}:{last_col}{row_num}"
        worksheet.update(cell_range, [row_data])
        logger.debug("[export] Updated request_id=%s at sheet row %d", req.request_id, row_num)

    # Commit DB transaction (no PII scrub or deletes)
    db.session.commit()
    logger.info(
        "[export] Weekly export complete — %d inserted, %d updated.",
        len(to_insert), len(to_update),
    )
