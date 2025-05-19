# website/helpers/export.py
import os, datetime, gspread
from google.oauth2.service_account import Credentials
from flask import current_app        # <── only need the *current* app
from models import PickupRequest, db


def weekly_export() -> None:
    """
    Export completed / incomplete PickupRequests to a Google Sheet
    and scrub the PII in the DB.
    Caller must already be inside an application context.
    """
    # Google creds
    creds_path = current_app.config.get(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials/service_account.json")
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

    # Existing ids in the sheet
    rows        = worksheet.get_all_values()[1:]        # skip header
    existing_id = {r[0] for r in rows if r}

    # DB rows to export
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
            r.request_id, r.fname or "", r.lname or "", r.email or "",
            r.phone_number or "", r.address or "", r.city or "", r.zipcode or "",
            r.notes or "", r.status or "", str(r.gated),
            r.request_date or "", r.request_time or "", r.date_filed or "",
            r.pickup_complete_info or "",
        ])

    if new_rows:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in reversed(new_rows):          # newest ends up just after header
            row.append(ts)
            worksheet.insert_row(row, index=2)

    # scrub PII and commit
    for r in to_export:
        if r.request_id not in existing_id:
            r.fname = r.lname = r.email = r.phone_number = "NA"

    db.session.commit()
    current_app.logger.info("Weekly export completed")
