# Onboarding Speed Run — Project Plan

## Status: WORKING ✅

---

## What This Does

A Python CLI that onboards a new team member by orchestrating 4 real tools
(Gmail, GitHub, Slack, Notion) via Composio's MCP server + OpenAI Agents SDK.

```bash
python onboard.py \
  --name "Alex Chen" \
  --email "alex@example.com" \
  --role "Backend Engineer" \
  --team "Platform" \
  --github-username "alexchen" \
  --slack-invite-url "https://join.slack.com/t/yourworkspace/..."
```

---

## Architecture

```
onboard.py (Python CLI, argparse)
    ↓
OpenAI Agents SDK — gpt-4o-mini as the orchestrator
    ↓
Composio Hosted MCP Server (session.mcp.url + session.mcp.headers)
    ↓
Real actions: Notion / Gmail / GitHub / Slack
```

---

## Step Execution Order

Steps run in this order (Notion first so its URL can be injected into the email):

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | 📝 Notion — create onboarding page | ✅ Working | Page URL extracted and passed to Gmail |
| 2 | 📧 Gmail — send welcome email | ✅ Working | Includes Notion page URL + Slack invite link |
| 3 | 🐙 GitHub — invite collaborator | ✅ Working | Pass `--github-username`; invite by username |
| 4 | 💬 Slack — post to channels | ✅ Working | Posts to #all-testing-workspace and #social |

---

## CLI Parameters

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | ✅ | Full name |
| `--email` | ✅ | New hire's email (recipient) |
| `--role` | ✅ | Job title |
| `--team` | ✅ | Team name |
| `--github-username` | optional | GitHub username for repo invite |
| `--slack-invite-url` | optional | Static Slack workspace invite link (included in welcome email) |
| `--verbose` / `-v` | optional | Print full agent prompts and responses |

---

## .env File

```
COMPOSIO_API_KEY=...
OPENAI_API_KEY=...
COMPOSIO_USER_ID=pg-test-ytApHNyBbMZrYWz69AVlGcLnRYgHx1Iw
GITHUB_REPO=JulianLoewenherz/onboardingspeedrun
NOTION_PARENT_PAGE_ID=32ae90f2babd802dbb26dd8b2c58ac15
SLACK_ENABLED=true
```

---

## Composio App Connections

Connected via OAuth at app.composio.dev under `julianloewenherz@gmail.com`.

| App | Status |
|-----|--------|
| Gmail | ✅ Connected |
| GitHub | ✅ Connected |
| Slack | ✅ Connected |
| Notion | ✅ Connected |

Auth failures print the direct `connect.composio.dev` link to reconnect.

---

## Known Limitations & Workarounds

**Slack — workspace invite**
- `admin.users:write` scope required to invite users via API
- Not available on standard Slack OAuth (requires Enterprise Grid)
- **Workaround:** pass a static invite link via `--slack-invite-url`; it gets included in the welcome email

**Notion — workspace invite**
- Notion API has no endpoint for inviting users by email to a workspace
- Page-level sharing attempted but also hits permission limits
- **Workaround:** Notion page URL is included in the welcome email so the new hire can access it directly

**GitHub — invite by email**
- GitHub collaborator invite requires a valid GitHub username, not just an email
- **Workaround:** always pass `--github-username`

**OpenAI rate limits**
- Using `gpt-4o-mini` (200k TPM) instead of `gpt-4o` (30k TPM on Tier 1)
- Auto-retry with backoff (30s/60s/90s) on 429 errors

---

## Demo Command

```bash
python onboard.py \
  --name "Julian Loewenherz" \
  --email "juliancollege123@gmail.com" \
  --github-username "julianpt2" \
  --role "Software Engineer" \
  --team "Engineering" \
  --slack-invite-url "https://join.slack.com/t/testingworksp-2az7337/shared_invite/zt-3t7noz684-Nj52pVzDYmJU5wcofuZcAg"
```

Sends a real email (with Notion + Slack links), creates a real Notion page,
invites to GitHub, and posts to Slack — all in one command.
