# website/helpers/export.py

import os
import datetime
import gspread
from google.oauth2.service_account import Credentials
from models import PickupRequest, db
from app import create_app

def weekly_export():
    """
    Exports completed and incomplete PickupRequests to a Google Sheet,
    then replaces sensitive fields in the DB with 'NA'.

    New rows are inserted right below the header row (row 1) so that the newest
    records appear at the top of the sheet. Additionally, a timestamp column is added 
    as the final column showing when the row was inserted.
    """
    # 1) Create/Use the Flask app and open an app context
    app = create_app()
    with app.app_context():
        # 2) Authorize Google Sheets with the service account
        creds_json_path = app.config.get('GOOGLE_SERVICE_ACCOUNT_JSON', 'credentials/service_account.json')
        creds = Credentials.from_service_account_file(
            creds_json_path,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        client = gspread.authorize(creds)

        # 3) Open the spreadsheet and select the worksheet by name
        spreadsheet = client.open("[DO NOT EDIT] EkoLinq Website Requests")
        worksheet = spreadsheet.worksheet("Requests")

        # 4) Retrieve existing rows (first row assumed to be header)
        all_rows = worksheet.get_all_values()
        data_rows = all_rows[1:] if len(all_rows) > 1 else []
        existing_ids = {row[0] for row in data_rows if row}

        # 5) Query the DB for PickupRequests with status 'Complete' or 'Incomplete'
        requests_to_export = PickupRequest.query.filter(
            PickupRequest.status.in_(["Complete", "Incomplete"])
        ).all()

        # 6) Build rows for insertion
        rows_to_insert = []
        for req in requests_to_export:
            if req.request_id not in existing_ids:
                row_data = [
                    req.request_id,
                    req.fname or "",
                    req.lname or "",
                    req.email or "",
                    req.phone_number or "",
                    req.address or "",
                    req.city or "",
                    req.zipcode or "",
                    req.notes or "",
                    req.status or "",
                    str(req.gated),
                    req.qr_code or "",
                    req.gate_code or "",
                    str(req.notify),
                    req.request_date or "",
                    req.request_time or "",
                    req.date_filed or "",
                    req.pickup_complete_info or "",
                ]
                rows_to_insert.append(row_data)

        # 7) Insert each new row at the top (just after the header row)
        #    and add a timestamp as the final column.
        if rows_to_insert:
            current_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Inserting in reverse order ensures that the row order remains as intended.
            for row in reversed(rows_to_insert):
                # Append the current date/time to the row data
                row.append(current_timestamp)
                # Insert at index 2 (row 1 is the header), so new data appears at the top.
                worksheet.insert_row(row, index=2)

        # 8) Wipe the PII from the exported requests in the DB
        for req in requests_to_export:
            if req.request_id not in existing_ids:
                req.fname = "NA"
                req.lname = "NA"
                req.email = "NA"
                req.phone_number = "NA"

        # 9) Commit the DB changes
        db.session.commit()

        print("Weekly export completed successfully!")

# Optional: allow running from the command line
if __name__ == "__main__":
    weekly_export()
