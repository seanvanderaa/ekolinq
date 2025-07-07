import datetime
import re
import os

import gspread
from flask import current_app
from sqlalchemy import or_, desc
from gspread.exceptions import WorksheetNotFound

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

def weekly_export() -> None:
    """Export all PickupRequest rows to Google Sheets via ghost-sheet swap.

    * Keeps most recent snapshot in 'Requests' tab.
    * Keeps previous snapshot in 'Requests_Temp' tab.
    * Dynamically generates headers from DB columns, using explicit map for renames.
    * Writes entire dump in a single atomic RPC (`values.batchUpdate`).
    * Orders rows by date_filed desc (newest first).
    """
    logger = current_app.logger
    logger.info("[export] Starting weekly export job…")

    # — auth & select spreadsheet —
    creds   = get_google_credentials()
    client  = gspread.authorize(creds)
    cfg     = os.getenv("FLASK_CONFIG", "development").lower()
    env_tag = "[PRODUCTION]" if cfg == "production" else "[DEVELOPMENT]"
    ss      = client.open(f"{env_tag} [DO NOT EDIT] EkoLinq Website Requests")

    # — Step 1: Rotate main into temp —
    try:
        stale = ss.worksheet("Requests_Temp")
        ss.del_worksheet(stale)
    except WorksheetNotFound:
        pass

    try:
        main_ws = ss.worksheet("Requests")
        main_ws.update_title("Requests_Temp")
    except WorksheetNotFound:
        pass

    # — Step 2: Create fresh 'Requests' tab —
    try:
        new_ws = ss.worksheet("Requests")
        new_ws.clear()
    except WorksheetNotFound:
        # infer size from DB
        total = (
            PickupRequest.query
            .filter(
                or_(
                    PickupRequest.admin_notes.is_(None),
                    PickupRequest.admin_notes != _ADMIN_SKIP_NOTE,
                )
            )
            .count()
        )
        # +1 for timestamp column
        cols = len(PickupRequest.__table__.columns)  
        new_ws = ss.add_worksheet(title="Requests", rows=str(total + 1), cols=str(cols + 1))

    # — Step 3: Dynamic headers from DB schema (excluding 'id') —
    cols = [c.name for c in PickupRequest.__table__.columns if c.name != "id"]
    reverse_map = {v: k for k, v in _EXPLICIT_FIELD_MAP.items()}
    header_row = [
        reverse_map.get(col, col.replace("_", " ").title())
        for col in cols
    ]
    header_row.append(_TIMESTAMP_COL)
    attr_order = [_header_to_attr(h) for h in header_row]
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # — Step 4: Fetch all rows ordered by date_filed desc —
    all_reqs = (
        PickupRequest.query
        .filter(
            or_(
                PickupRequest.admin_notes.is_(None),
                PickupRequest.admin_notes != _ADMIN_SKIP_NOTE,
            )
        )
        .order_by(desc(PickupRequest.date_filed))
        .all()
    )

    # Build matrix: header + rows
    values = [header_row]
    for req in all_reqs:
        if (req.admin_notes or "").strip() == _ADMIN_SKIP_NOTE:
            continue
        row = []
        for attr in attr_order:
            if attr is None:
                row.append(timestamp)
            else:
                val = getattr(req, attr, "")
                row.append(str(val) if val is not None else "")
        values.append(row)

    # — Step 5: Write dump in one atomic RPC —
    new_ws.update("A1", values, value_input_option="RAW")

    # — Step 6: Cleanup stray worksheets —
    for ws in ss.worksheets():
        if ws.title not in ("Requests", "Requests_Temp"):
            ss.del_worksheet(ws)

    db.session.commit()
    logger.info(
        "[export] Weekly export complete — 'Requests' holds current dump; 'Requests_Temp' holds prior dump."
    )
