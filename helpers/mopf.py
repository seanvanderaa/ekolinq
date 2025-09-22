import datetime
import os

import gspread
from flask import current_app
from gspread.exceptions import WorksheetNotFound

from helpers.google_creds import get_google_credentials


_MOPF_SHEET_TITLE = "MOPF Submissions"
_HEADERS = [
    "First Name",
    "Last Name",
    "Email Address",
    "Address",
    "Address 2",
    "City",
    "Zipcode",
    "Donation Date",
    "Estimated Value",
    "Submitted At",
]


def _open_env_spreadsheet() -> gspread.Spreadsheet:
    """Open the environment-tagged spreadsheet used elsewhere in the app."""
    creds   = get_google_credentials()
    client  = gspread.authorize(creds)
    cfg     = os.getenv("FLASK_CONFIG", "development").lower()
    env_tag = "[PRODUCTION]" if cfg == "production" else "[DEVELOPMENT]"
    # Use the exact same spreadsheet name convention as the existing exporter.
    return client.open(f"{env_tag} [DO NOT EDIT] MOPF Entries")


def _get_or_create_mopf_sheet(ss: gspread.Spreadsheet) -> gspread.Worksheet:
    """
    Return the 'MOPF Submissions' worksheet, creating it with headers if missing.
    Ensures the header row exists and matches _HEADERS.
    """
    try:
        ws = ss.worksheet(_MOPF_SHEET_TITLE)
    except WorksheetNotFound:
        # Create with a modest default size; gspread auto-expands as needed.
        ws = ss.add_worksheet(title=_MOPF_SHEET_TITLE, rows="50", cols=str(len(_HEADERS)))
        ws.update("A1", [_HEADERS], value_input_option="RAW")
        return ws

    # Ensure header row exists; if empty, write it. If present but different, rewrite it.
    try:
        existing_header = ws.row_values(1)
    except Exception:
        existing_header = []

    if existing_header != _HEADERS:
        ws.resize(rows=max(50, ws.row_count))  # keep at least some headroom
        ws.update("A1", [_HEADERS], value_input_option="RAW")

    return ws


def save_donation_submission(
    fname, lname, email, address, address2, city, zip_, donation_date, estimated_value
):
    """
    Append a donation submission to the 'MOPF Submissions' sheet (prepend under header).

    Behavior:
    - Uses the same environment-specific spreadsheet as weekly_export().
    - Ensures the 'MOPF Submissions' sheet exists with canonical headers.
    - Inserts the new record at row 2 (top of the data, under the header).
    - Returns a JSON-style dict indicating success/failure.
    """
    logger = getattr(current_app, "logger", None)

    try:
        ss = _open_env_spreadsheet()
        ws = _get_or_create_mopf_sheet(ss)

        # Normalize values for consistent storage
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        zip_str = "" if zip_ is None else str(zip_).strip()
        donation_date_str = "" if donation_date is None else str(donation_date).strip()
        estimated_value_str = "" if estimated_value is None else str(estimated_value).strip()

        row = [
            "" if fname is None else str(fname).strip(),
            "" if lname is None else str(lname).strip(),
            "" if email is None else str(email).strip(),
            "" if address is None else str(address).strip(),
            "" if address2 is None else str(address2).strip(),
            "" if city is None else str(city).strip(),
            zip_str,
            donation_date_str,
            estimated_value_str,
            timestamp,
        ]

        # Insert at the top of the data (row 2). If the sheet is brand-new, header is at row 1.
        ws.insert_row(row, index=2, value_input_option="RAW")

        if logger:
            logger.debug("[MOPF] Saved donation submission.")

        return {
            "ok": True,
            "sheet": _MOPF_SHEET_TITLE,
            "inserted_at_row": 2,
            "submitted_at": timestamp,
        }

    except Exception as e:
        if logger:
            logger.exception("[MOPF] Failed to save donation submission: %s", e)
        # Keep response shape consistent; callers can jsonify and choose status codes.
        return {
            "ok": False,
            "error": str(e),
        }
