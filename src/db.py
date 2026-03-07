from __future__ import annotations

import os
from typing import Any

import requests

try:
    from supabase import create_client, Client
except Exception:
    create_client = None
    Client = Any  # type: ignore


def _get_config(*keys: str) -> str | None:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value

    try:
        import streamlit as st

        for key in keys:
            if key in st.secrets and st.secrets[key]:
                return str(st.secrets[key])
    except Exception:
        pass

    return None


SUPABASE_URL = _get_config("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = _get_config(
    "SUPABASE_KEY",
    "SUPABASE_ANON_KEY",
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY",
)
SUPABASE_LOG_TABLE = _get_config("SUPABASE_LOG_TABLE") or "log_user"

def init_supabase() -> Client | None:
    """Initialize and return the Supabase client if credentials are provided."""
    if create_client and SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"Error initializing Supabase client: {e}")
            return None
    return None

supabase = init_supabase()


def _rest_insert_log(payload: dict) -> str | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_LOG_TABLE}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=payload,
            timeout=5,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            if isinstance(data, list) and data:
                row_id = data[0].get("id")
                if row_id is not None:
                    return str(row_id)
        else:
            print(f"REST insert failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"REST insert exception: {e}")
    return None


def _rest_update_exit_time(row_id: str, now_iso: str) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY or not row_id:
        return

    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_LOG_TABLE}?id=eq.{row_id}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json={"exit_time": now_iso},
            timeout=5,
        )
        if resp.status_code not in (200, 204):
            print(f"REST update failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"REST update exception: {e}")

def get_public_ip() -> str:
    """Attempt to get the user's public IP address via an external API."""
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=3)
        if response.status_code == 200:
            return response.json().get('ip', 'unknown')
    except Exception:
        pass
    return "unknown"

def log_access(session_id: str) -> str | None:
    """Logs the start of a user session and returns the inserted DB row ID (if successful)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    
    ip_address = get_public_ip()
    from datetime import datetime
    now_iso = datetime.utcnow().isoformat()
    payload = {
        "session_id": session_id,
        "ip_address": ip_address,
        "exit_time": now_iso,
    }
    
    return _rest_insert_log(payload)

def update_access_exit_time(row_id: str):
    """Updates the exit_time for a given session log row."""
    if not SUPABASE_URL or not SUPABASE_KEY or not row_id:
        return
        
    from datetime import datetime
    now_iso = datetime.utcnow().isoformat()

    _rest_update_exit_time(str(row_id), now_iso)

def log_feedback(nome: str, email: str, feedback: str) -> bool:
    """Saves user feedback to the feedbacks table."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
        
    try:
        if supabase:
            supabase.table('feedbacks').insert({
                "nome": nome,
                "email": email,
                "feedback": feedback
            }).execute()
            return True

        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/feedbacks",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "nome": nome,
                "email": email,
                "feedback": feedback,
            },
            timeout=5,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"Error saving feedback to Supabase: {e}")
        return False
