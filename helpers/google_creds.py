# google_creds.py
import base64, json, os, tempfile
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_google_credentials() -> Credentials:
    json_path = (
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON",
                  "etc/secrets/service_account.json")
    )
    return Credentials.from_service_account_file(json_path, scopes=SCOPES)
