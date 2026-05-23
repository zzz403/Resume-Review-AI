import os
from dotenv import load_dotenv

load_dotenv()

_client = None

def _get_db():
    global _client
    if _client is not None:
        return _client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None
    from supabase import create_client
    _client = create_client(url, key)
    return _client

def save_review(resume_text: str, score: int | None, feedback: str) -> dict:
    db = _get_db()
    if db is None:
        return {}
    row = (
        db.table("reviews")
        .insert({"resume_text": resume_text, "score": score, "feedback": feedback})
        .execute()
    )
    return row.data[0]

def fetch_history() -> list[dict]:
    db = _get_db()
    if db is None:
        return []
    rows = (
        db.table("reviews")
        .select("id, score, feedback, created_at")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return rows.data
