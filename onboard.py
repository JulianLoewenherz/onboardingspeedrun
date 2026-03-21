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
    parser.add_argument("--name",  required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role",  required=True)
    parser.add_argument("--team",  required=True)
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full agent responses and tool calls")
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
    """Extract and print every tool call the agent made."""
    try:
        for msg in result.new_messages():
            # Tool call requests (assistant side)
            if hasattr(msg, "content") and isinstance(msg.content, list):
                for block in msg.content:
                    if hasattr(block, "type") and block.type == "tool_use":
                        print(f"     🔧 Tool call: {block.name}")
                        if hasattr(block, "input") and block.input:
                            for k, v in block.input.items():
                                val_str = str(v)[:120]
                                print(f"        {k}: {val_str}")
            # Tool results (tool side)
            if hasattr(msg, "role") and msg.role == "tool":
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    content = " ".join(str(c) for c in content)
                print(f"     📥 Tool result: {str(content)[:300]}")
    except Exception as e:
        print(f"     (could not extract tool calls: {e})")


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def run_step(agent, prompt, verbose=False):
    """
    Run one agent step.
    Always prints the full agent response.
    Returns (success, output, auth_url).
    """
    if verbose:
        print(f"\n  PROMPT →\n  {prompt}\n")

    t0 = time.time()
    result = Runner.run_sync(starting_agent=agent, input=prompt)
    elapsed = time.time() - t0
    output = result.final_output or ""

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


def prompt_github(email, github_repo):
    owner, repo = github_repo.split("/", 1)
    return (
        f"Invite the email address {email} as a collaborator to the GitHub repository '{repo}' owned by '{owner}'. "
        f"Use the 'add collaborator to repo' tool with the email address {email} directly — do NOT look up a username. "
        f"The full repo path is {github_repo}."
    )


def prompt_slack(name, email, role, team):
    return (
        f"Do the following in Slack (workspace: testingworksp-2az7337.slack.com):\n"
        f"1. Invite the email address {email} to the Slack workspace.\n"
        f"2. Post to #all-testing-workspace: \"👋 Please welcome {name} to the team! "
        f"They're joining as {role} on the {team} team. Say hello!\"\n"
        f"3. Post to #social: \"{name} | {role} | {team} — starting today!\"\n"
        f"For each action, confirm whether it succeeded or failed."
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
        f"2. Invite {email} to the Notion workspace so they can access the page.\n"
        f"Return the URL of the created page and confirm whether the invite was sent."
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
            "Execute exactly the tasks given using the available Composio tools. "
            "Do NOT ask the user questions — just execute each task. "
            "For each sub-task, report: what you did, whether it succeeded or failed, and any relevant URLs or IDs. "
            "If a tool is unavailable or requires authentication, say so explicitly."
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

    # Steps: (label, app_name, prompt_or_None)
    steps = [
        ("📧 Sending welcome email",   "Gmail",  prompt_gmail(name, email, role, team)),
        ("🐙 Inviting to GitHub repo", "GitHub", prompt_github(email, github_repo) if github_repo else None),
        ("💬 Posting to Slack",        "Slack",  prompt_slack(name, email, role, team) if slack_enabled else None),
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
