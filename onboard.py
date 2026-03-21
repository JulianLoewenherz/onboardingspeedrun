#!/usr/bin/env python3
"""Onboarding Speed Run — orchestrates Gmail, GitHub, Slack, and Notion via Composio MCP + OpenAI Agents."""

import argparse
import os
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
    }

    missing_required = [k for k, v in required.items() if not v]
    if missing_required:
        print(f"❌ Missing required env vars: {', '.join(missing_required)}")
        sys.exit(1)

    for key, val in optional.items():
        if not val:
            print(f"⚠️  {key} not set — that step will be skipped.")

    return optional


# ---------------------------------------------------------------------------
# Agent runner helper
# ---------------------------------------------------------------------------

def run_step(agent, prompt):
    """Run a single agent call and return the final output string."""
    result = Runner.run_sync(starting_agent=agent, input=prompt)
    return result.final_output


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


def prompt_slack(name, role, team):
    return (
        f"Post two messages:\n"
        f"1. To #general: \"👋 Please welcome {name} to the team! "
        f"They're joining as {role} on the {team} team. Say hello!\"\n"
        f"2. To #announcements: \"{name} | {role} | {team} — starting today!\""
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

    name  = args.name
    email = args.email
    role  = args.role
    team  = args.team

    github_repo    = env["GITHUB_REPO"]
    notion_page_id = env["NOTION_PARENT_PAGE_ID"]

    print(f"\n🚀 Starting onboarding for {name} ({email}) — {role} @ {team}\n")

    # Build Composio session + agent
    composio = Composio()
    user_id  = os.getenv("COMPOSIO_USER_ID")
    session  = composio.create(user_id=user_id)

    agent = Agent(
        name="Onboarding Agent",
        instructions=(
            "You are an onboarding automation agent. "
            "Execute exactly the task given to you using the available Composio tools. "
            "Be concise in your response — confirm what was done and include any relevant URLs or IDs."
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

    # Define steps: (label, prompt_or_None)
    steps = [
        ("📧 Sending welcome email",     prompt_gmail(name, email, role, team)),
        ("🐙 Inviting to GitHub repo",   prompt_github(email, github_repo) if github_repo else None),
        ("💬 Posting to Slack",          prompt_slack(name, role, team)),
        ("📝 Creating Notion page",      prompt_notion(name, role, team, notion_page_id) if notion_page_id else None),
    ]

    total    = len(steps)
    results  = {}
    failures = []

    for i, (label, prompt) in enumerate(steps, start=1):
        prefix = f"[{i}/{total}] {label}"

        if prompt is None:
            print(f"{prefix}... ⏭  Skipped (not configured)")
            continue

        print(f"{prefix}...", end=" ", flush=True)
        try:
            output = run_step(agent, prompt)
            print("✓ Done")
            results[label] = output
        except Exception as exc:
            msg = str(exc)
            print(f"✗ Failed: {msg}")
            failures.append((label, msg))

            # Auth hint
            for app in ("gmail", "github", "slack", "notion"):
                if app in msg.lower():
                    app_title = app.capitalize()
                    print(f"   → [{app_title}] Not connected — visit app.composio.dev to connect {app_title} and retry.")
                    break

    # Final summary
    print(f"\n{'🎉 Onboarding complete for ' + name + '!' if not failures else '⚠️  Onboarding finished with errors.'}\n")

    if results:
        print("Summary:")
        for label, output in results.items():
            # Print first meaningful line of each result
            first_line = output.strip().split("\n")[0][:120]
            print(f"  {label}: {first_line}")

    if failures:
        print("\nFailed steps:")
        for label, msg in failures:
            print(f"  ✗ {label}: {msg[:120]}")


if __name__ == "__main__":
    main()
