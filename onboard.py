#!/usr/bin/env python3
"""Onboarding Speed Run — orchestrates Gmail, GitHub, Slack, and Notion via Composio MCP + OpenAI Agents."""

import argparse
import os
import re
import sys
import time
from datetime import date
from dotenv import load_dotenv
from composio import Composio
from agents import Agent, Runner, HostedMCPTool

load_dotenv()

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Onboard a new team member across all tools.")
    parser.add_argument("--name",            required=True)
    parser.add_argument("--email",           required=True)
    parser.add_argument("--role",            required=True)
    parser.add_argument("--team",            required=True)
    parser.add_argument("--github-username", required=False, default=None, help="New hire's GitHub username (e.g. alexchen)")
    parser.add_argument("--verbose", "-v",   action="store_true", help="Show full agent responses and tool calls")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def validate_env():
    required = {
        "COMPOSIO_API_KEY": os.getenv("COMPOSIO_API_KEY"),
        "OPENAI_API_KEY":   os.getenv("OPENAI_API_KEY"),
        "COMPOSIO_USER_ID": os.getenv("COMPOSIO_USER_ID"),
    }
    optional = {
        "GITHUB_REPO":           os.getenv("GITHUB_REPO"),
        "NOTION_PARENT_PAGE_ID": os.getenv("NOTION_PARENT_PAGE_ID"),
        "SLACK_ENABLED":         os.getenv("SLACK_ENABLED", "").lower() in ("1", "true", "yes"),
    }

    missing_required = [k for k, v in required.items() if not v]
    if missing_required:
        print(f"❌ Missing required env vars: {', '.join(missing_required)}")
        sys.exit(1)

    if not optional["GITHUB_REPO"]:
        print("⚠️  GITHUB_REPO not set — GitHub step will be skipped.")
    if not optional["NOTION_PARENT_PAGE_ID"]:
        print("⚠️  NOTION_PARENT_PAGE_ID not set — Notion step will be skipped.")
    if not optional["SLACK_ENABLED"]:
        print("⚠️  SLACK_ENABLED not set — Slack step will be skipped. Set SLACK_ENABLED=true in .env when ready.")

    return optional


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
    Always prints the full agent response.
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

    # Always show tool calls
    print(f"\n  ⏱  {elapsed:.1f}s — Tool calls made:")
    log_tool_calls(result)

    # Always show full agent response
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

def prompt_gmail(name, email, role, team):
    return (
        f"Send an email using Gmail to {email} with:\n"
        f'Subject: "Welcome to the team, {name}! 🎉"\n'
        f"Body: Write a warm, personalized welcome email that includes:\n"
        f"- A warm personal welcome addressing {name} by name\n"
        f"- Their role ({role}) and team ({team})\n"
        f"- What their first week will look like (standup, 1:1s, getting set up)\n"
        f"- A note that their accounts and tools are being set up right now\n"
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


def prompt_slack(name, role, team):
    # Note: inviting users to a Slack workspace requires admin.users:write scope
    # which is not available via standard OAuth. We skip that and just post announcements.
    return (
        f"Post the following two messages in Slack (workspace: testingworksp-2az7337.slack.com):\n"
        f"1. To #all-testing-workspace: \"👋 Please welcome {name} to the team! "
        f"They're joining as {role} on the {team} team. Say hello!\"\n"
        f"2. To #social: \"{name} | {role} | {team} — starting today!\"\n"
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
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    env = validate_env()
    verbose = args.verbose

    name            = args.name
    email           = args.email
    role            = args.role
    team            = args.team
    github_username = args.github_username

    github_repo    = env["GITHUB_REPO"]
    notion_page_id = env["NOTION_PARENT_PAGE_ID"]
    slack_enabled  = env["SLACK_ENABLED"]

    print(f"\n🚀 Starting onboarding for {name} ({email}) — {role} @ {team}\n")

    # Build Composio session + agent
    print("  Initializing Composio session...", end=" ", flush=True)
    composio = Composio()
    user_id  = os.getenv("COMPOSIO_USER_ID")
    session  = composio.create(user_id=user_id)
    print(f"✓  (session: {session.mcp.url.split('/')[-2]})\n")

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

    # Steps: (label, app_name, prompt_or_None)
    steps = [
        ("📧 Sending welcome email",   "Gmail",  prompt_gmail(name, email, role, team)),
        ("🐙 Inviting to GitHub repo", "GitHub", prompt_github(email, github_repo, github_username) if github_repo else None),
        ("💬 Posting to Slack",        "Slack",  prompt_slack(name, role, team) if slack_enabled else None),
        ("📝 Creating Notion page",    "Notion", prompt_notion(name, email, role, team, notion_page_id) if notion_page_id else None),
    ]

    total    = len(steps)
    results  = {}
    failures = []

    for i, (label, app, prompt) in enumerate(steps, start=1):
        print(f"{'='*50}")
        prefix = f"[{i}/{total}] {label}"

        if prompt is None:
            print(f"{prefix}... ⏭  Skipped (not configured)")
            continue

        print(f"{prefix}...")

        try:
            success, output, auth_url = run_step(agent, prompt, verbose=verbose)

            if success:
                print(f"✓ {label} — Done")
                results[label] = output
            else:
                print(f"✗ {label} — Auth required")
                failures.append((label, app, output, auth_url))
                if auth_url:
                    print(f"  → Connect {app} here: {auth_url}")
                else:
                    print(f"  → Visit https://app.composio.dev → All Toolkits → connect {app}")

        except Exception as exc:
            msg = str(exc)
            print(f"✗ {label} — Error: {msg}")
            failures.append((label, app, msg, None))

    # Final summary
    skipped   = sum(1 for s in steps if s[2] is None)
    succeeded = len(results)
    print(f"\n{'='*50}")
    if not failures:
        print(f"🎉 Onboarding complete for {name}!")
    else:
        print(f"⚠️  Onboarding finished: {succeeded} done, {len(failures)} failed, {skipped} skipped")

    if results:
        print("\nCompleted:")
        for label, output in results.items():
            first_line = output.strip().split("\n")[0][:120]
            print(f"  ✓ {label}: {first_line}")

    if failures:
        print("\nFailed (action needed):")
        for label, app, output, auth_url in failures:
            if auth_url:
                print(f"  ✗ {app}: {auth_url}")
            else:
                print(f"  ✗ {app}: check logs above")
    print()


if __name__ == "__main__":
    main()
