import os
import requests
from supabase import create_client, Client

# Use environment variables if available (e.g. from .env or Streamlit Cloud Secrets)
SUPABASE_URL = (
    os.environ.get("SUPABASE_URL")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
)
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY")
)
SUPABASE_LOG_TABLE = (
    os.environ.get("SUPABASE_LOG_TABLE")
    or "log_user"
)

def init_supabase() -> Client | None:
    """Initialize and return the Supabase client if credentials are provided."""
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"Error initializing Supabase client: {e}")
            return None
    return None

supabase = init_supabase()

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
    if not supabase:
        return None
    
    ip_address = get_public_ip()
    
    try:
        from datetime import datetime
        now_iso = datetime.utcnow().isoformat()
        resp = supabase.table(SUPABASE_LOG_TABLE).insert({
            "session_id": session_id,
            "ip_address": ip_address,
            "exit_time": now_iso,
        }).execute()

        rows = getattr(resp, "data", None) or []
        if rows:
            return rows[0].get("id")
    except Exception as e:
        print(f"Error logging access to Supabase table '{SUPABASE_LOG_TABLE}': {e}")
    return None

def update_access_exit_time(row_id: str):
    """Updates the exit_time for a given session log row."""
    if not supabase or not row_id:
        return
        
    try:
        from datetime import datetime
        now_iso = datetime.utcnow().isoformat()
        supabase.table(SUPABASE_LOG_TABLE).update({
            "exit_time": now_iso
        }).eq("id", row_id).execute()
    except Exception as e:
        print(f"Error updating access exit time in Supabase table '{SUPABASE_LOG_TABLE}': {e}")

def log_feedback(nome: str, email: str, feedback: str) -> bool:
    """Saves user feedback to the feedbacks table."""
    if not supabase:
        return False
        
    try:
        supabase.table('feedbacks').insert({
            "nome": nome,
            "email": email,
            "feedback": feedback
        }).execute()
        return True
    except Exception as e:
        print(f"Error saving feedback to Supabase: {e}")
        return False
