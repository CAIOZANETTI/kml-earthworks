from __future__ import annotations

import os
from typing import Any, Dict

import requests

from src.logger import get_logger

logger = get_logger(__name__)

try:
    from supabase import create_client, Client
except Exception as e:
    logger.warning(f"Supabase library not available: {e}")
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
    except Exception as e:
        logger.debug(f"Could not access Streamlit secrets: {e}")

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
            logger.error(f"Error initializing Supabase client: {e}")
            return None
    return None

supabase = init_supabase()


def _rest_insert_log(payload: Dict[str, Any]) -> str | None:
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
            logger.warning(f"REST insert failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.error(f"REST insert exception: {e}", exc_info=True)
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
            logger.warning(f"REST update failed ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.error(f"REST update exception: {e}", exc_info=True)

def get_public_ip() -> str:
    """Attempt to get the client's public IP address from request headers."""
    try:
        import streamlit as st
        # Try to get the real client IP from X-Forwarded-For header
        # This works in Streamlit Cloud and other proxy deployments
        if hasattr(st, 'context') and hasattr(st.context, 'headers'):
            forwarded_for = st.context.headers.get("X-Forwarded-For")
            if forwarded_for:
                # X-Forwarded-For can contain multiple IPs, take the first (client)
                return forwarded_for.split(',')[0].strip()
    except Exception as e:
        logger.debug(f"Could not retrieve public IP from headers: {e}", exc_info=True)
    return "unknown"

def log_access(session_id: str) -> str | None:
    """Logs the start of a user session and returns the inserted DB row ID (if successful)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    ip_address = get_public_ip()
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "session_id": session_id,
        "ip_address": ip_address,
        "exit_time": now_iso,
    }

    return _rest_insert_log(payload)

def update_access_exit_time(row_id: str) -> None:
    """Updates the exit_time for a given session log row."""
    if not SUPABASE_URL or not SUPABASE_KEY or not row_id:
        return

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

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
        logger.error(f"Error saving feedback to Supabase: {e}", exc_info=True)
        return False
