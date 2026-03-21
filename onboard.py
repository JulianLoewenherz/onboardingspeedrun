#!/usr/bin/env python3
"""Onboarding Speed Run — orchestrates Gmail, GitHub, Slack, and Notion via Composio MCP + OpenAI Agents."""

import argparse
import os
import re
import sys
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
    parser.add_argument("--name",  required=True, help="Full name, e.g. 'Alex Chen'")
    parser.add_argument("--email", required=True, help="Work email")
    parser.add_argument("--role",  required=True, help="Job title, e.g. 'Backend Engineer'")
    parser.add_argument("--team",  required=True, help="Team name, e.g. 'Platform'")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print full agent responses")
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

# Phrases the agent uses when a tool requires OAuth instead of actually acting
AUTH_PHRASES = [
    "connect.composio.dev",
    "please connect",
    "please complete",
    "need to connect",
    "requires authentication",
    "authenticate",
    "authorization",
    "connect your",
    "not connected",
    "no available tools",
    "i don't have",
    "i do not have",
    "unable to",
    "cannot ",
    "can't ",
]

def detect_auth_required(text: str) -> tuple[bool, str | None]:
    """Return (needs_auth, connect_url_or_None) by inspecting the agent response."""
    lower = text.lower()
    needs_auth = any(phrase in lower for phrase in AUTH_PHRASES)
    # Extract a composio.dev auth URL if present
    match = re.search(r'https://connect\.composio\.dev/\S+', text)
    url = match.group(0).rstrip(').,]') if match else None
    return needs_auth, url


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def run_step(agent, prompt, verbose=False):
    """
    Run a single agent call.
    Returns (success: bool, output: str).
    Raises on unexpected exceptions.
    """
    if verbose:
        print(f"\n  → Prompt sent to agent:\n    {prompt[:200]}{'...' if len(prompt) > 200 else ''}")

    result = Runner.run_sync(starting_agent=agent, input=prompt)
    output = result.final_output or ""

    if verbose:
        print(f"\n  ← Agent response:\n    {output}\n")

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


def prompt_github(email, github_repo):
    owner, repo = github_repo.split("/", 1)
    return (
        f"Invite {email} as a collaborator to the GitHub repository {github_repo}. "
        f"The owner is '{owner}' and the repo name is '{repo}'. "
        f"Use the GitHub add collaborator tool for a repo (not an org)."
    )


def prompt_slack(name, email, role, team):
    return (
        f"Do the following three things in Slack (workspace: testingworksp-2az7337.slack.com):\n"
        f"1. Invite {email} to the Slack workspace so they can join.\n"
        f"2. Post to #general: \"👋 Please welcome {name} to the team! "
        f"They're joining as {role} on the {team} team. Say hello!\"\n"
        f"3. Post to #announcements: \"{name} | {role} | {team} — starting today!\""
    )


def prompt_notion(name, role, team, notion_page_id):
    today = date.today().strftime("%B %d, %Y")
    return (
        f"Create a new page inside the Notion page with ID {notion_page_id}.\n"
        f'Page title: "{name} — Onboarding ({today})"\n'
        f"Page content:\n"
        f'- H1 header: "Welcome, {name}!"\n'
        f"- Their role: {role}, team: {team}\n"
        f'- H2 section "First Week Checklist" with these tasks as checkboxes:\n'
        f"  * Set up your dev environment\n"
        f"  * Read the team wiki\n"
        f"  * 1:1 with your manager (Day 1)\n"
        f"  * Join team standup (Day 2)\n"
        f"  * Complete security training\n"
        f"  * Make your first PR\n"
        f"  * Meet with each team member (Week 1)\n"
        f"  * 30-day goals check-in\n"
        f'- H2 section "Your Tools" listing: GitHub, Slack, Linear, Notion, Gmail\n'
        f"Return the URL of the created page."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    env = validate_env()
    verbose = args.verbose

    name  = args.name
    email = args.email
    role  = args.role
    team  = args.team

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
            "Execute exactly the task given to you using the available Composio tools. "
            "Do NOT ask the user questions — just execute. "
            "If the tool succeeds, confirm what was done and include any relevant URLs or IDs. "
            "If the tool is unavailable or requires authentication, say so explicitly."
        ),
        model="gpt-4o",
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

    # Define steps: (label, app_name, prompt_or_None)
    steps = [
        ("📧 Sending welcome email",   "Gmail",  prompt_gmail(name, email, role, team)),
        ("🐙 Inviting to GitHub repo", "GitHub", prompt_github(email, github_repo) if github_repo else None),
        ("💬 Posting to Slack",        "Slack",  prompt_slack(name, email, role, team) if slack_enabled else None),
        ("📝 Creating Notion page",    "Notion", prompt_notion(name, role, team, notion_page_id) if notion_page_id else None),
    ]

    total    = len(steps)
    results  = {}
    failures = []

    for i, (label, app, prompt) in enumerate(steps, start=1):
        prefix = f"[{i}/{total}] {label}"

        if prompt is None:
            reason = "not configured" if (app == "GitHub" and not github_repo) or (app == "Notion" and not notion_page_id) else "SLACK_ENABLED not set"
            print(f"{prefix}... ⏭  Skipped ({reason})")
            continue

        print(f"{prefix}...", end=" ", flush=True)
        try:
            success, output, auth_url = run_step(agent, prompt, verbose=verbose)

            if success:
                print("✓ Done")
                results[label] = output
                if not verbose:
                    # Show a brief confirmation line
                    first_line = output.strip().split("\n")[0][:120]
                    print(f"     {first_line}")
            else:
                print("✗ Auth required")
                failures.append((label, app, output, auth_url))
                print(f"   [{app}] Not connected to Composio.")
                if auth_url:
                    print(f"   → Connect here: {auth_url}")
                else:
                    print(f"   → Visit https://app.composio.dev → All Toolkits → connect {app}")
                if not verbose:
                    print(f"   Agent said: {output.strip()[:200]}")

        except Exception as exc:
            msg = str(exc)
            print(f"✗ Error: {msg[:120]}")
            failures.append((label, app, msg, None))

    # Final summary
    succeeded = total - len([s for s in steps if s[2] is None]) - len(failures)
    skipped   = len([s for s in steps if s[2] is None])

    print(f"\n{'─' * 50}")
    if not failures:
        print(f"🎉 Onboarding complete for {name}!")
    else:
        print(f"⚠️  Onboarding finished: {succeeded} done, {len(failures)} need attention, {skipped} skipped")

    if results:
        print("\nCompleted:")
        for label, output in results.items():
            first_line = output.strip().split("\n")[0][:100]
            print(f"  ✓ {label}: {first_line}")

    if failures:
        print("\nNeeds attention (connect these apps at app.composio.dev):")
        for label, app, output, auth_url in failures:
            print(f"  ✗ {app}: {auth_url or 'visit app.composio.dev → All Toolkits → ' + app}")

    print()


if __name__ == "__main__":
    main()
