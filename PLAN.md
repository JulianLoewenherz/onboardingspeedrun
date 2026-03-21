# Onboarding Speed Run — Project Plan

## Status: READY TO BUILD

All setup is complete. The next session should start by running:
```bash
cd /Users/julianloewenherz/Desktop/onboardingspeedrun
source venv/bin/activate
```
Then immediately build `onboard.py` using the SDK pattern below.

---

## Goal

A Python CLI that onboards a new team member by orchestrating 5 real tools
(Gmail, GitHub, Slack, Notion, Linear) via Composio's MCP server + OpenAI.

```bash
python onboard.py --name "Alex Chen" --email "alex@example.com" \
  --role "Backend Engineer" --team "Platform"
```

---

## Architecture

```
onboard.py (Python CLI, argparse)
    ↓
OpenAI Agents SDK — gpt-4o as the orchestrator
    ↓
Composio Hosted MCP Server (session.mcp.url + session.mcp.headers)
    ↓
Real actions: Gmail / GitHub / Slack / Notion / Linear
```

---

## SDK Pattern — EXACTLY How to Use It

This is the correct pattern from the Composio quickstart. Follow it precisely.

### Install
```bash
pip install python-dotenv composio openai-agents
```

### Correct import and initialization
```python
from dotenv import load_dotenv
from composio import Composio
from agents import Agent, Runner, HostedMCPTool

load_dotenv()

# Initialize WITHOUT a provider — MCP mode needs no provider
composio = Composio()

# Create session — this generates the MCP URL + headers dynamically
session = composio.create(user_id=os.getenv("COMPOSIO_USER_ID"))

# Build agent with HostedMCPTool
agent = Agent(
    name="Onboarding Agent",
    instructions="...",
    model="gpt-4o",
    tools=[
        HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "composio",
                "server_url": session.mcp.url,       # from session, never hardcoded
                "require_approval": "never",
                "headers": session.mcp.headers,       # from session, never hardcoded
            }
        )
    ],
)

# Run
result = Runner.run_sync(starting_agent=agent, input="your prompt here")
print(result.final_output)
```

### NEVER do these (deprecated/wrong):
```python
# WRONG — old pattern
tools = composio.tools.get(user_id, { toolkits: ['github'] })
result = composio.tools.execute('GITHUB_STAR_REPO', {...})

# WRONG — don't pass a provider when using MCP
composio = Composio(provider=OpenAIAgentsProvider())

# WRONG — wrong package name
from composio_core import Composio
```

---

## .env File (already created with real keys)

```
OPENAI_API_KEY=<set>
COMPOSIO_API_KEY=<set>
COMPOSIO_USER_ID=pg-test-ytApHNyBbMZrYWz69AVlGcLnRYgHx1Iw
GITHUB_REPO=owner/repo-name        # e.g. julianloewenherz/my-project
NOTION_PARENT_PAGE_ID=<needs value>
```

GITHUB_REPO and NOTION_PARENT_PAGE_ID may still need to be filled in.
LINEAR is not used — remove LINEAR_TEAM_ID if present.

Note: Using a repo (not an org) for GitHub. Format is "owner/repo-name".

---

## Composio App Connections

Connected via OAuth in the Composio dashboard (user side).
If a step fails with an auth error, direct the user to:
app.composio.dev → All Toolkits → reconnect that app.

Apps that should be connected:
- Gmail
- GitHub
- Slack
- Notion
- Linear

The script should detect auth failures and print a clear message like:
"[GITHUB] Not connected — visit app.composio.dev to connect GitHub and retry."

---

## File Structure to Create

```
onboardingspeedrun/
├── PLAN.md            ← this file (done)
├── .env               ← done (keys set)
├── .env.example       ← to create
├── .gitignore         ← to create
├── onboard.py         ← main build target
└── README.md          ← after onboard.py works
```

---

## onboard.py — Full Spec

### CLI interface
```bash
python onboard.py --name "Alex Chen" --email "alex@example.com" \
  --role "Backend Engineer" --team "Platform"
```

### Startup validation
- Load .env
- Check GITHUB_ORG, NOTION_PARENT_PAGE_ID, LINEAR_TEAM_ID are set
- Warn for any missing, but continue (skip that step)

### Progress output
```
[1/4] 📧 Sending welcome email to alex@example.com...  ✓ Done
[2/4] 🐙 Inviting to GitHub repo...                    ✓ Done
[3/4] 💬 Posting to Slack...                           ✓ Done
[4/4] 📝 Creating Notion page...                       ✓ Done

🎉 Onboarding complete for Alex Chen!

Summary:
  Notion page:   https://notion.so/...
  GitHub invite: Sent to alex@example.com
```

### Error handling
- Wrap each step in try/except
- If a step fails, print: `[2/5] 🐙 GitHub... ✗ Failed: <error message>`
- Continue to remaining steps regardless
- List all failures in the final summary

### Agent prompt structure
Run each step as a separate agent call (cleaner progress tracking) OR
run one agent call with all 5 tasks and parse the streaming output.
Prefer separate calls — easier to show per-step progress.

---

## The 5 Steps — Exact Instructions to Give the Agent

### Step 1 — Gmail
```
Send an email using Gmail to {email} with:
Subject: "Welcome to the team, {name}! 🎉"
Body: Write a warm, personalized welcome email that includes:
- A warm personal welcome addressing {name} by name
- Their role ({role}) and team ({team})
- What their first week will look like (standup, 1:1s, getting set up)
- A note that their accounts and tools are being set up right now
- Sign off as: "The Onboarding Bot, powered by Composio"
```

### Step 2 — GitHub
```
Invite {email} as a collaborator to the GitHub repository {GITHUB_REPO}.
GITHUB_REPO is in the format "owner/repo-name" (e.g. julianloewenherz/my-project).
Use the GitHub add collaborator tool for a repo, not an org.
```

### Step 3 — Slack
```
Post two messages:
1. To #general: "👋 Please welcome {name} to the team! They're joining as {role} on the {team} team. Say hello!"
2. To #announcements: "{name} | {role} | {team} — starting today!"
```

### Step 4 — Notion
```
Create a new page inside the Notion page with ID {NOTION_PARENT_PAGE_ID}.
Page title: "{name} — Onboarding ({today_date})"
Page content:
- H1 header: "Welcome, {name}!"
- Their role: {role}, team: {team}
- H2 section "First Week Checklist" with these tasks as checkboxes:
  * Set up your dev environment
  * Read the team wiki
  * 1:1 with your manager (Day 1)
  * Join team standup (Day 2)
  * Complete security training
  * Make your first PR
  * Meet with each team member (Week 1)
  * 30-day goals check-in
- H2 section "Your Tools" listing: GitHub, Slack, Linear, Notion, Gmail
Return the URL of the created page.
```

### Step 5 — Linear
SKIPPED — removed from project scope.

---

## Key Rules (from Composio quickstart)

- `Composio()` — NO provider argument in MCP mode
- `composio.create(user_id=...)` — always create session first
- Use `session.mcp.url` and `session.mcp.headers` — never hardcode these
- Set `require_approval: "never"` in HostedMCPTool config
- API keys in .env only, loaded with dotenv

---

## Build Order for Next Session

1. Create `.gitignore` and `.env.example`
2. Build `onboard.py` skeleton (CLI args, .env loading, startup validation)
3. Add Composio session + OpenAI agent setup
4. Implement each of the 5 steps with progress printing
5. Add error handling and final summary
6. Test run: `python onboard.py --name "Julian" --email "julianloewenherz@gmail.com" --role "Engineer" --team "Engineering"`
7. Fix any auth/connection errors
8. Write `README.md`

---

## Demo Script (for interviews)

```bash
python onboard.py \
  --name "Julian Loewenherz" \
  --email "julianloewenherz@gmail.com" \
  --role "Software Engineer" \
  --team "Engineering"
```

Sends a real email, posts to real Slack, creates a real Notion page and Linear
project — all in one command. Run this live during the interview.
