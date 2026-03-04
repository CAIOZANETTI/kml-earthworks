"""
leads.py
Capture visitor info and append to a Google Sheet.

Setup (one-time):
1. Create a Google Sheet with headers in row 1:
   timestamp | name | company | country | email | linkedin | files_uploaded | total_length_m

2. Create a Google Cloud service account, share the sheet with it (Editor).

3. In Streamlit Cloud → Secrets, add:
   [gsheets]
   spreadsheet_id = "YOUR_SHEET_ID"
   [gcp_service_account]
   type = "service_account"
   project_id = "..."
   private_key_id = "..."
   private_key = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
   client_email = "..."
   client_id = "..."
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
"""

import datetime
from typing import Optional


def _get_client():
    """Return an authenticated gspread client from Streamlit secrets."""
    try:
        import streamlit as st
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=scopes,
        )
        return gspread.authorize(creds)
    except Exception:
        return None


def log_lead(
    name: str,
    email: str,
    country: str = "",
    linkedin: str = "",
    files_uploaded: int = 0,
    total_length_m: float = 0.0,
) -> bool:
    """
    Append one lead row to the configured Google Sheet.
    Returns True on success, False if secrets not configured.
    """
    try:
        import streamlit as st

        sheet_id = st.secrets.get("gsheets", {}).get("spreadsheet_id", "")
        if not sheet_id:
            return False

        client = _get_client()
        if client is None:
            return False

        sheet = client.open_by_key(sheet_id).sheet1
        sheet.append_row(
            [
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                name,
                country,
                email,
                linkedin,
                files_uploaded,
                round(total_length_m, 0),
            ],
            value_input_option="USER_ENTERED",
        )
        return True
    except Exception:
        return False


def leads_configured() -> bool:
    """Check if Google Sheets secrets are present."""
    try:
        import streamlit as st
        return bool(st.secrets.get("gsheets", {}).get("spreadsheet_id"))
    except Exception:
        return False
