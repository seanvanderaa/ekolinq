import os, datetime, gspread
from google.oauth2.service_account import Credentials
from flask import current_app
from models import PickupRequest, db


def weekly_export() -> None:
    """
    1. Export every PickupRequest whose status is “Complete” or “Incomplete”
       to the shared Google Sheet (skipping any that have already been logged).
    2. Scrub PII for every newly-exported row.
    3. Delete every PickupRequest whose status is “Unfinished”.
       (All three steps are committed in the same DB transaction.)
    Caller must already be inside an application context.
    """
    # ── Google credentials ────────────────────────────────────────────────────
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
    client      = gspread.authorize(creds)
    spreadsheet = client.open("[DO NOT EDIT] EkoLinq Website Requests")
    worksheet   = spreadsheet.worksheet("Requests")

    # ── Already-exported IDs (row 0 is the header) ────────────────────────────
    existing_id = {row[0] for row in worksheet.get_all_values()[1:] if row}

    # ── Rows to export (Complete / Incomplete) ────────────────────────────────
    to_export = (
        PickupRequest.query
        .filter(PickupRequest.status.in_(["Complete", "Incomplete"]))
        .all()
    )

    new_rows = []
    for r in to_export:
        if r.request_id in existing_id:
            continue
        new_rows.append([
            r.request_id,
            r.fname or "", r.lname or "", r.email or "", r.phone_number or "",
            r.address or "", r.city or "", r.zipcode or "",
            r.notes or "", r.status or "", str(r.gated),
            r.request_date or "", r.request_time or "", r.date_filed or "",
            r.pickup_complete_info or "",
        ])

    if new_rows:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in reversed(new_rows):           # newest just after header
            row.append(timestamp)
            worksheet.insert_row(row, index=2)

    # ── Scrub PII on newly-exported rows ──────────────────────────────────────
    for r in to_export:
        if r.request_id not in existing_id:
            r.fname = r.lname = r.email = r.phone_number = "NA"

    # ── Delete every “Unfinished” request ─────────────────────────────────────
    unfinished = PickupRequest.query.filter_by(status="Unfinished").all()
    for r in unfinished:
        db.session.delete(r)

    # ── Commit everything in one shot ─────────────────────────────────────────
    db.session.commit()
    current_app.logger.info(
        "Weekly export completed — %d rows exported, %d unfinished rows deleted",
        len(new_rows), len(unfinished),
    )
