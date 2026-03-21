#!/usr/bin/env python3
"""Onboarding Speed Run — orchestrates Gmail, GitHub, Slack, and Notion via Composio MCP + OpenAI Agents."""

import argparse
import os
import re
import sys
import time
from datetime import date
from typing import Generator
from dotenv import load_dotenv
from composio import Composio
from agents import Agent, Runner, HostedMCPTool

load_dotenv()


# ---------------------------------------------------------------------------
# Auth detection
# ---------------------------------------------------------------------------

AUTH_PHRASES = [
    "connect.composio.dev",
    "please connect",
    "please complete",
    "need to connect",
    "requires authentication",
    "authenticate",
    "connect your",
    "not connected",
    "no available tools",
    "i don't have",
    "i do not have",
]

def detect_auth_required(text: str) -> tuple[bool, str | None]:
    lower = text.lower()
    needs_auth = any(phrase in lower for phrase in AUTH_PHRASES)
    match = re.search(r'https://connect\.composio\.dev/\S+', text)
    url = match.group(0).rstrip(').,]') if match else None
    return needs_auth, url


# ---------------------------------------------------------------------------
# Extract Notion page URL from agent response
# ---------------------------------------------------------------------------

def extract_notion_url(text: str) -> str | None:
    match = re.search(r'https://www\.notion\.so/\S+', text)
    return match.group(0).rstrip(').,]') if match else None


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def log_tool_calls(result):
    """Extract and print every tool call the agent made via raw_responses."""
    try:
        found_any = False
        for response in result.raw_responses:
            for item in getattr(response, "output", []):
                item_type = getattr(item, "type", "")
                if item_type == "mcp_call":
                    found_any = True
                    print(f"     🔧 Tool call: {getattr(item, 'name', '?')}")
                    inp = getattr(item, "arguments", None) or getattr(item, "input", None)
                    if inp:
                        if isinstance(inp, dict):
                            for k, v in inp.items():
                                print(f"        {k}: {str(v)[:120]}")
                        else:
                            print(f"        args: {str(inp)[:200]}")
                elif item_type == "mcp_result":
                    found_any = True
                    content = getattr(item, "output", "") or getattr(item, "content", "")
                    print(f"     📥 Tool result: {str(content)[:300]}")
        if not found_any:
            print("     (no tool calls recorded in raw_responses)")
    except Exception as e:
        print(f"     (could not extract tool calls: {e})")


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def run_step(agent, prompt, verbose=False):
    """
    Run one agent step with retry on rate limit (429).
    Always prints tool calls and full agent response.
    Returns (success, output, auth_url).
    """
    if verbose:
        print(f"\n  PROMPT →\n  {prompt}\n")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            t0 = time.time()
            result = Runner.run_sync(starting_agent=agent, input=prompt)
            elapsed = time.time() - t0
            output = result.final_output or ""
            break
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "rate_limit" in msg.lower():
                wait = 30 * attempt
                print(f"\n  ⏳ Rate limit hit (attempt {attempt}/{max_retries}) — waiting {wait}s...")
                time.sleep(wait)
                if attempt == max_retries:
                    raise
            else:
                raise

    print(f"\n  ⏱  {elapsed:.1f}s — Tool calls made:")
    log_tool_calls(result)

    print(f"\n  Agent response:\n  {'─'*40}")
    for line in output.strip().split("\n"):
        print(f"  {line}")
    print(f"  {'─'*40}\n")

    needs_auth, auth_url = detect_auth_required(output)
    if needs_auth:
        return False, output, auth_url

    return True, output, None


# ---------------------------------------------------------------------------
# Step prompts
# ---------------------------------------------------------------------------

def prompt_gmail(name, email, role, team, notion_url=None, slack_invite_url=None):
    links_section = ""
    if notion_url or slack_invite_url:
        links_section = "\n- A 'Your Links' section with the following:\n"
        if notion_url:
            links_section += f"  * Notion onboarding page: {notion_url}\n"
        if slack_invite_url:
            links_section += f"  * Join our Slack workspace: {slack_invite_url}\n"

    return (
        f"Send an email using Gmail to {email} with:\n"
        f'Subject: "Welcome to the team, {name}! 🎉"\n'
        f"Body: Write a warm, personalized welcome email that includes:\n"
        f"- A warm personal welcome addressing {name} by name\n"
        f"- Their role ({role}) and team ({team})\n"
        f"- What their first week will look like (standup, 1:1s, getting set up)\n"
        f"- A note that their accounts and tools are being set up right now\n"
        f"{links_section}"
        f'- Sign off as: "The Onboarding Bot, powered by Composio"'
    )


def prompt_github(email, github_repo, github_username=None):
    owner, repo = github_repo.split("/", 1)
    identity = f"username '{github_username}'" if github_username else f"email address {email}"
    username_note = (
        f"Use the GitHub username '{github_username}'."
        if github_username
        else f"No GitHub username was provided — try using the email address {email} directly."
    )
    return (
        f"Invite {identity} as a collaborator to the GitHub repository '{repo}' owned by '{owner}'. "
        f"{username_note} "
        f"The full repo path is {github_repo}. "
        f"Use the add-collaborator-to-repo tool (not an org invite)."
    )


def prompt_slack(name, role, team, slack_channels=None, workspace=None):
    channels = slack_channels or ["#general", "#social"]
    ch1, ch2 = (channels + ["#social"])[:2]
    workspace_hint = f" (workspace: {workspace})" if workspace else ""
    return (
        f"Post the following two messages in Slack{workspace_hint}:\n"
        f"1. To {ch1}: \"👋 Please welcome {name} to the team! "
        f"They're joining as {role} on the {team} team. Say hello!\"\n"
        f"2. To {ch2}: \"{name} | {role} | {team} — starting today!\"\n"
        f"Confirm whether each message was posted successfully."
    )


def prompt_notion(name, email, role, team, notion_page_id):
    today = date.today().strftime("%B %d, %Y")
    return (
        f"Do the following in Notion:\n"
        f"1. Create a new page inside the Notion page with ID {notion_page_id}.\n"
        f'   Page title: "{name} — Onboarding ({today})"\n'
        f"   Page content:\n"
        f'   - H1 header: "Welcome, {name}!"\n'
        f"   - Their role: {role}, team: {team}\n"
        f'   - H2 section "First Week Checklist" with checkboxes:\n'
        f"     * Set up your dev environment\n"
        f"     * Read the team wiki\n"
        f"     * 1:1 with your manager (Day 1)\n"
        f"     * Join team standup (Day 2)\n"
        f"     * Complete security training\n"
        f"     * Make your first PR\n"
        f"     * Meet with each team member (Week 1)\n"
        f"     * 30-day goals check-in\n"
        f'   - H2 section "Your Tools" listing: GitHub, Slack, Notion, Gmail\n'
        f"2. After creating the page, share it with {email} using the Notion share/invite tool "
        f"   on the newly created page (not the whole workspace — just that page). "
        f"   Use role 'reader' or 'editor'.\n"
        f"Return the URL of the created page and confirm whether the page share succeeded."
    )


# ---------------------------------------------------------------------------
# Core onboarding logic — importable generator
# ---------------------------------------------------------------------------

class OnboardingConfig:
    """All parameters needed to run an onboarding."""
    def __init__(
        self,
        name: str,
        email: str,
        role: str,
        team: str,
        github_username: str | None = None,
        slack_invite_url: str | None = None,
        # integration toggles
        enable_notion: bool = True,
        enable_gmail: bool = True,
        enable_github: bool = True,
        enable_slack: bool = True,
        # workspace config (overrides env vars when provided)
        github_repo: str | None = None,
        notion_parent_page_id: str | None = None,
        slack_channels: list[str] | None = None,
        slack_workspace: str | None = None,
        verbose: bool = False,
    ):
        self.name = name
        self.email = email
        self.role = role
        self.team = team
        self.github_username = github_username
        self.slack_invite_url = slack_invite_url
        self.enable_notion = enable_notion
        self.enable_gmail = enable_gmail
        self.enable_github = enable_github
        self.enable_slack = enable_slack
        self.github_repo = github_repo or os.getenv("GITHUB_REPO")
        self.notion_parent_page_id = notion_parent_page_id or os.getenv("NOTION_PARENT_PAGE_ID")
        self.slack_channels = slack_channels
        self.slack_workspace = slack_workspace
        self.verbose = verbose


def run_onboarding(config: OnboardingConfig) -> Generator[dict, None, None]:
    """
    Run the full onboarding workflow.
    Yields dicts describing each step's progress:
      {"step": "init",   "status": "running"}
      {"step": "notion", "status": "running"}
      {"step": "notion", "status": "success", "url": "https://..."}
      {"step": "notion", "status": "error",   "error": "..."}
      {"step": "notion", "status": "skipped"}
      {"step": "done",   "status": "success", "notion_url": "..."}
    """
    # --- Init ---
    yield {"step": "init", "status": "running"}
    try:
        composio = Composio()
        user_id = os.getenv("COMPOSIO_USER_ID")
        session = composio.create(user_id=user_id)
    except Exception as exc:
        yield {"step": "init", "status": "error", "error": str(exc)}
        return

    agent = Agent(
        name="Onboarding Agent",
        instructions=(
            "You are an onboarding automation agent. "
            "Execute exactly the tasks given using the available Composio tools. "
            "Do NOT ask the user questions — just execute each task. "
            "For each sub-task, report: what you did, whether it succeeded or failed, and any relevant URLs or IDs. "
            "If a tool is unavailable or requires authentication, say so explicitly."
        ),
        model="gpt-4o-mini",
        tools=[
            HostedMCPTool(
                tool_config={
                    "type": "mcp",
                    "server_label": "composio",
                    "server_url": session.mcp.url,
                    "require_approval": "never",
                    "headers": session.mcp.headers,
                }
            )
        ],
    )
    yield {"step": "init", "status": "success"}

    notion_url = None

    # --- Notion ---
    if config.enable_notion and config.notion_parent_page_id:
        yield {"step": "notion", "status": "running"}
        try:
            success, output, auth_url = run_step(
                agent,
                prompt_notion(config.name, config.email, config.role, config.team, config.notion_parent_page_id),
                verbose=config.verbose,
            )
            if success:
                notion_url = extract_notion_url(output)
                yield {"step": "notion", "status": "success", "url": notion_url, "output": output}
            else:
                yield {"step": "notion", "status": "error", "error": "Auth required", "auth_url": auth_url, "output": output}
        except Exception as exc:
            yield {"step": "notion", "status": "error", "error": str(exc)}
    else:
        reason = "disabled" if not config.enable_notion else "no_page_id"
        yield {"step": "notion", "status": "skipped", "reason": reason}

    # --- Gmail ---
    if config.enable_gmail:
        yield {"step": "gmail", "status": "running"}
        try:
            success, output, auth_url = run_step(
                agent,
                prompt_gmail(config.name, config.email, config.role, config.team,
                             notion_url=notion_url, slack_invite_url=config.slack_invite_url),
                verbose=config.verbose,
            )
            if success:
                yield {"step": "gmail", "status": "success", "output": output}
            else:
                yield {"step": "gmail", "status": "error", "error": "Auth required", "auth_url": auth_url, "output": output}
        except Exception as exc:
            yield {"step": "gmail", "status": "error", "error": str(exc)}
    else:
        yield {"step": "gmail", "status": "skipped", "reason": "disabled"}

    # --- GitHub ---
    if config.enable_github and config.github_repo:
        yield {"step": "github", "status": "running"}
        try:
            success, output, auth_url = run_step(
                agent,
                prompt_github(config.email, config.github_repo, config.github_username),
                verbose=config.verbose,
            )
            if success:
                yield {"step": "github", "status": "success", "output": output}
            else:
                yield {"step": "github", "status": "error", "error": "Auth required", "auth_url": auth_url, "output": output}
        except Exception as exc:
            yield {"step": "github", "status": "error", "error": str(exc)}
    else:
        reason = "disabled" if not config.enable_github else "no_repo"
        yield {"step": "github", "status": "skipped", "reason": reason}

    # --- Slack ---
    slack_env_enabled = os.getenv("SLACK_ENABLED", "").lower() in ("1", "true", "yes")
    if config.enable_slack and slack_env_enabled:
        yield {"step": "slack", "status": "running"}
        try:
            success, output, auth_url = run_step(
                agent,
                prompt_slack(config.name, config.role, config.team, config.slack_channels, config.slack_workspace),
                verbose=config.verbose,
            )
            if success:
                yield {"step": "slack", "status": "success", "output": output}
            else:
                yield {"step": "slack", "status": "error", "error": "Auth required", "auth_url": auth_url, "output": output}
        except Exception as exc:
            yield {"step": "slack", "status": "error", "error": str(exc)}
    else:
        reason = "disabled" if not config.enable_slack else "slack_env_disabled"
        yield {"step": "slack", "status": "skipped", "reason": reason}

    yield {"step": "done", "status": "success", "notion_url": notion_url}


# ---------------------------------------------------------------------------
# CLI (unchanged behaviour)
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Onboard a new team member across all tools.")
    parser.add_argument("--name",             required=True)
    parser.add_argument("--email",            required=True)
    parser.add_argument("--role",             required=True)
    parser.add_argument("--team",             required=True)
    parser.add_argument("--github-username",  required=False, default=None)
    parser.add_argument("--slack-invite-url", required=False, default=None)
    parser.add_argument("--verbose", "-v",    action="store_true")
    return parser.parse_args()


def validate_env():
    required = {
        "COMPOSIO_API_KEY": os.getenv("COMPOSIO_API_KEY"),
        "OPENAI_API_KEY":   os.getenv("OPENAI_API_KEY"),
        "COMPOSIO_USER_ID": os.getenv("COMPOSIO_USER_ID"),
    }
    missing_required = [k for k, v in required.items() if not v]
    if missing_required:
        print(f"❌ Missing required env vars: {', '.join(missing_required)}")
        sys.exit(1)


def main():
    args = parse_args()
    validate_env()

    config = OnboardingConfig(
        name=args.name,
        email=args.email,
        role=args.role,
        team=args.team,
        github_username=args.github_username,
        slack_invite_url=args.slack_invite_url,
        verbose=args.verbose,
        enable_slack=os.getenv("SLACK_ENABLED", "").lower() in ("1", "true", "yes"),
    )

    print(f"\n🚀 Starting onboarding for {config.name} ({config.email}) — {config.role} @ {config.team}\n")

    results  = {}
    failures = []
    notion_url = None

    for event in run_onboarding(config):
        step   = event["step"]
        status = event["status"]

        if step == "init":
            if status == "running":
                print("  Initializing Composio session...", end=" ", flush=True)
            elif status == "success":
                print("✓\n")
            elif status == "error":
                print(f"✗  {event['error']}")
                sys.exit(1)

        elif step == "done":
            notion_url = event.get("notion_url")

        elif status == "skipped":
            print(f"{'='*50}")
            print(f"⏭  {step} — Skipped ({event.get('reason', '')})")

        elif status == "running":
            print(f"{'='*50}")
            print(f"▶  {step}...")

        elif status == "success":
            print(f"✓  {step} — Done")
            results[step] = event.get("output", "")
            if step == "notion" and event.get("url"):
                print(f"   📎 Page URL: {event['url']}")

        elif status == "error":
            print(f"✗  {step} — {event.get('error', 'Unknown error')}")
            auth_url = event.get("auth_url")
            if auth_url:
                print(f"   → Reconnect: {auth_url}")
            failures.append((step, event.get("error"), auth_url))

    print(f"\n{'='*50}")
    if not failures:
        print(f"🎉 Onboarding complete for {config.name}!")
    else:
        print(f"⚠️  Onboarding finished: {len(results)} done, {len(failures)} failed")
    if notion_url:
        print(f"\n  📎 Notion page: {notion_url}")
    print()


if __name__ == "__main__":
    main()
