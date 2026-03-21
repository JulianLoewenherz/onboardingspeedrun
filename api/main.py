"""FastAPI backend for Onboarding Speedrun UI."""

import asyncio
import json
import os
import sys
import threading
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Ensure the project root (where onboard.py lives) is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from onboard import OnboardingConfig, run_onboarding  # noqa: E402
from api.supabase_client import (  # noqa: E402
    get_settings,
    upsert_settings,
    insert_onboarding,
    list_onboardings,
    get_onboarding,
)

app = FastAPI(title="Onboarding Speedrun API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class OnboardRequest(BaseModel):
    name: str
    email: str
    role: str
    team: str
    github_username: str | None = None
    # per-run toggles
    enable_notion: bool = True
    enable_gmail: bool = True
    enable_github: bool = True
    enable_slack: bool = True


class SettingsUpdate(BaseModel):
    github_repo: str | None = None
    notion_parent_page_id: str | None = None
    slack_invite_url: str | None = None
    slack_channels: str | None = None
    slack_workspace: str | None = None
    default_notion: bool | None = None
    default_github: bool | None = None
    default_slack: bool | None = None
    default_email: bool | None = None


# ---------------------------------------------------------------------------
# /onboard  — SSE streaming endpoint
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _stream_onboarding(req: OnboardRequest):
    # Pull workspace config from Supabase (or env fallback)
    try:
        settings = get_settings()
    except Exception:
        settings = {}

    slack_channels_raw = settings.get("slack_channels", "")
    slack_channels = [c.strip() for c in slack_channels_raw.split(",") if c.strip()] or None

    config = OnboardingConfig(
        name=req.name,
        email=req.email,
        role=req.role,
        team=req.team,
        github_username=req.github_username,
        slack_invite_url=settings.get("slack_invite_url") or None,
        enable_notion=req.enable_notion,
        enable_gmail=req.enable_gmail,
        enable_github=req.enable_github,
        enable_slack=req.enable_slack,
        github_repo=settings.get("github_repo") or None,
        notion_parent_page_id=settings.get("notion_parent_page_id") or None,
        slack_channels=slack_channels,
        slack_workspace=settings.get("slack_workspace") or None,
    )

    steps: list[dict] = []
    notion_url: str | None = None
    final_status = "success"

    # run_onboarding uses Runner.run_sync() which blocks the event loop.
    # Run it in a thread and feed events back via an async queue.
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run_in_thread():
        try:
            for event in run_onboarding(config):
                asyncio.run_coroutine_threadsafe(queue.put(event), loop)
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(
                queue.put({"step": "done", "status": "error", "error": str(exc)}), loop
            )
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)  # sentinel

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()

    try:
        while True:
            event = await queue.get()
            if event is None:
                break

            if event["step"] not in ("init", "done"):
                steps.append({
                    "name": event["step"],
                    "status": event["status"],
                    "url": event.get("url"),
                    "error": event.get("error"),
                })
                if event["status"] == "error":
                    final_status = "partial"

            if event["step"] == "done":
                notion_url = event.get("notion_url")

            yield _sse(event)
    except Exception as exc:
        final_status = "failed"
        yield _sse({"step": "done", "status": "error", "error": str(exc)})

    # Persist to Supabase
    try:
        record = {
            "name": req.name,
            "email": req.email,
            "role": req.role,
            "team": req.team,
            "github_username": req.github_username,
            "integrations": {
                "notion": req.enable_notion,
                "gmail": req.enable_gmail,
                "github": req.enable_github,
                "slack": req.enable_slack,
            },
            "steps": steps,
            "notion_url": notion_url,
            "status": final_status,
        }
        insert_onboarding(record)
    except Exception:
        pass  # don't break the stream if Supabase is misconfigured


@app.post("/onboard")
async def onboard(req: OnboardRequest):
    return StreamingResponse(
        _stream_onboarding(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------

@app.get("/settings")
def read_settings():
    try:
        return get_settings()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.put("/settings")
def write_settings(body: SettingsUpdate):
    data = body.model_dump(exclude_none=True)
    try:
        return upsert_settings(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# /onboardings  — history
# ---------------------------------------------------------------------------

@app.get("/onboardings")
def history(limit: int = 50):
    try:
        return list_onboardings(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/onboardings/{onboarding_id}")
def onboarding_detail(onboarding_id: str):
    try:
        record = get_onboarding(onboarding_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    return record


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}
