"""Supabase client — shared singleton for the FastAPI app."""

import os
from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "github_repo": "",
    "notion_parent_page_id": "",
    "slack_invite_url": "",
    "slack_channels": "#general,#social",
    "default_notion": True,
    "default_github": True,
    "default_slack": True,
    "default_email": True,
}


def get_settings() -> dict:
    db = get_client()
    result = db.table("settings").select("*").eq("id", 1).maybe_single().execute()
    if result.data:
        return {**DEFAULT_SETTINGS, **result.data}
    return DEFAULT_SETTINGS


def upsert_settings(data: dict) -> dict:
    db = get_client()
    payload = {"id": 1, **data}
    result = db.table("settings").upsert(payload).execute()
    return result.data[0] if result.data else payload


# ---------------------------------------------------------------------------
# Onboarding history helpers
# ---------------------------------------------------------------------------

def insert_onboarding(record: dict) -> dict:
    db = get_client()
    result = db.table("onboardings").insert(record).execute()
    return result.data[0] if result.data else record


def list_onboardings(limit: int = 50) -> list[dict]:
    db = get_client()
    result = (
        db.table("onboardings")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_onboarding(onboarding_id: str) -> dict | None:
    db = get_client()
    result = db.table("onboardings").select("*").eq("id", onboarding_id).maybe_single().execute()
    return result.data
