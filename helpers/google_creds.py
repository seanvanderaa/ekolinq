# google_creds.py
import base64, json, os, tempfile
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_google_credentials() -> Credentials:
    """
    • In prod: read GOOGLE_SA_B64, decode, build creds from dict.
    • In dev:  fall back to GOOGLE_SERVICE_ACCOUNT_JSON
              (or 'credentials/service_account.json').
    """
    if b64 := os.getenv("GOOGLE_SA_B64"):
        info = json.loads(base64.b64decode(b64))
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    json_path = (
        os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON",
                  "credentials/service_account.json")
    )
    return Credentials.from_service_account_file(json_path, scopes=SCOPES)
