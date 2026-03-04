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
        info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        # Use gspread.Client directly — gspread.authorize() is deprecated in v5+
        return gspread.Client(auth=creds)
    except Exception as exc:
        return str(exc)   # return error message so callers can surface it


def log_lead(
    name: str,
    email: str,
    country: str = "",
    company: str = "",
    linkedin: str = "",
    files_uploaded: int = 0,
    total_length_m: float = 0.0,
) -> tuple[bool, str]:
    """
    Append one lead row to the configured Google Sheet.

    Returns:
        (True, "")           on success
        (False, reason_str)  on failure (secrets missing, auth error, API error)

    Sheet column order:
        timestamp | name | company | country | email | linkedin | files_uploaded | total_length_m
    """
    try:
        import streamlit as st

        sheet_id = st.secrets.get("gsheets", {}).get("spreadsheet_id", "")
        if not sheet_id:
            return False, "spreadsheet_id not found in [gsheets] secrets"

        client = _get_client()
        if isinstance(client, str):
            # _get_client returned an error message
            return False, f"Auth error: {client}"

        sheet = client.open_by_key(sheet_id).sheet1
        sheet.append_row(
            [
                datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                name,
                company,         # column 3 — kept blank if not collected
                country,
                email,
                linkedin,
                files_uploaded,
                round(total_length_m, 0),
            ],
            value_input_option="USER_ENTERED",
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)


def leads_configured() -> bool:
    """Check if Google Sheets secrets are present."""
    try:
        import streamlit as st
        return bool(st.secrets.get("gsheets", {}).get("spreadsheet_id"))
    except Exception:
        return False
