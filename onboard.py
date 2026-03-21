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
    parser.add_argument("--name",             required=True)
    parser.add_argument("--email",            required=True)
    parser.add_argument("--role",             required=True)
    parser.add_argument("--team",             required=True)
    parser.add_argument("--github-username",  required=False, default=None, help="New hire's GitHub username (e.g. julianpt2)")
    parser.add_argument("--slack-invite-url", required=False, default=None, help="Slack workspace invite link to include in welcome email")
    parser.add_argument("--verbose", "-v",    action="store_true", help="Show full agent responses and tool calls")
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


def prompt_slack(name, role, team):
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

    name             = args.name
    email            = args.email
    role             = args.role
    team             = args.team
    github_username  = args.github_username
    slack_invite_url = args.slack_invite_url

    github_repo    = env["GITHUB_REPO"]
    notion_page_id = env["NOTION_PARENT_PAGE_ID"]
    slack_enabled  = env["SLACK_ENABLED"]

    if slack_invite_url:
        print(f"  Slack invite URL provided — will include in welcome email.")
    else:
        print(f"  ℹ️  No --slack-invite-url provided — Slack link won't appear in email.")

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

    results  = {}
    failures = []
    notion_url = None

    # ------------------------------------------------------------------
    # Step 1 — Notion (run first so we can include the URL in the email)
    # ------------------------------------------------------------------
    notion_label = "📝 Creating Notion page"
    print(f"{'='*50}")
    if notion_page_id:
        print(f"[1/4] {notion_label}...")
        try:
            success, output, auth_url = run_step(agent, prompt_notion(name, email, role, team, notion_page_id), verbose=verbose)
            if success:
                notion_url = extract_notion_url(output)
                print(f"✓ {notion_label} — Done")
                if notion_url:
                    print(f"  📎 Page URL: {notion_url}")
                else:
                    print("  ⚠️  Could not extract Notion page URL from response")
                results[notion_label] = output
            else:
                print(f"✗ {notion_label} — Auth required")
                failures.append((notion_label, "Notion", output, auth_url))
                if auth_url:
                    print(f"  → Connect Notion here: {auth_url}")
        except Exception as exc:
            print(f"✗ {notion_label} — Error: {exc}")
            failures.append((notion_label, "Notion", str(exc), None))
    else:
        print(f"[1/4] {notion_label}... ⏭  Skipped (NOTION_PARENT_PAGE_ID not set)")

    # ------------------------------------------------------------------
    # Step 2 — Gmail (now has Notion URL + Slack invite link)
    # ------------------------------------------------------------------
    gmail_label = "📧 Sending welcome email"
    print(f"{'='*50}")
    print(f"[2/4] {gmail_label}...")
    if notion_url:
        print(f"  ℹ️  Including Notion page URL in email: {notion_url}")
    if slack_invite_url:
        print(f"  ℹ️  Including Slack invite URL in email: {slack_invite_url}")
    try:
        success, output, auth_url = run_step(
            agent,
            prompt_gmail(name, email, role, team, notion_url=notion_url, slack_invite_url=slack_invite_url),
            verbose=verbose,
        )
        if success:
            print(f"✓ {gmail_label} — Done")
            results[gmail_label] = output
        else:
            print(f"✗ {gmail_label} — Auth required")
            failures.append((gmail_label, "Gmail", output, auth_url))
            if auth_url:
                print(f"  → Connect Gmail here: {auth_url}")
    except Exception as exc:
        print(f"✗ {gmail_label} — Error: {exc}")
        failures.append((gmail_label, "Gmail", str(exc), None))

    # ------------------------------------------------------------------
    # Step 3 — GitHub
    # ------------------------------------------------------------------
    github_label = "🐙 Inviting to GitHub repo"
    print(f"{'='*50}")
    if github_repo:
        print(f"[3/4] {github_label}...")
        try:
            success, output, auth_url = run_step(agent, prompt_github(email, github_repo, github_username), verbose=verbose)
            if success:
                print(f"✓ {github_label} — Done")
                results[github_label] = output
            else:
                print(f"✗ {github_label} — Auth required")
                failures.append((github_label, "GitHub", output, auth_url))
                if auth_url:
                    print(f"  → Connect GitHub here: {auth_url}")
        except Exception as exc:
            print(f"✗ {github_label} — Error: {exc}")
            failures.append((github_label, "GitHub", str(exc), None))
    else:
        print(f"[3/4] {github_label}... ⏭  Skipped (GITHUB_REPO not set)")

    # ------------------------------------------------------------------
    # Step 4 — Slack
    # ------------------------------------------------------------------
    slack_label = "💬 Posting to Slack"
    print(f"{'='*50}")
    if slack_enabled:
        print(f"[4/4] {slack_label}...")
        try:
            success, output, auth_url = run_step(agent, prompt_slack(name, role, team), verbose=verbose)
            if success:
                print(f"✓ {slack_label} — Done")
                results[slack_label] = output
            else:
                print(f"✗ {slack_label} — Auth required")
                failures.append((slack_label, "Slack", output, auth_url))
                if auth_url:
                    print(f"  → Connect Slack here: {auth_url}")
        except Exception as exc:
            print(f"✗ {slack_label} — Error: {exc}")
            failures.append((slack_label, "Slack", str(exc), None))
    else:
        print(f"[4/4] {slack_label}... ⏭  Skipped (SLACK_ENABLED not set)")

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    print(f"\n{'='*50}")
    if not failures:
        print(f"🎉 Onboarding complete for {name}!")
    else:
        print(f"⚠️  Onboarding finished: {len(results)} done, {len(failures)} failed")

    if results:
        print("\nCompleted:")
        for label, output in results.items():
            first_line = output.strip().split("\n")[0][:120]
            print(f"  ✓ {label}: {first_line}")

    if notion_url:
        print(f"\n  📎 Notion page: {notion_url}")

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
