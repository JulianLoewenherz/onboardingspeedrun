# 🚀 Onboarding Speedrun

Onboarding Speedrun is an open-source new-hire onboarding assistant that turns a repetitive checklist into one guided workflow. Enter a teammate's name, email, role, team, and optional GitHub username, then the app can create their Notion onboarding page, send a Gmail welcome email, invite them to a GitHub repository, announce them in Slack, and save the run to Supabase history.

The project includes both a web app and a CLI. The web app gives operators a friendly dashboard with per-integration toggles, live progress updates, settings, and onboarding history. The CLI runs the same automation from a terminal.

## What it does

For each new hire, Onboarding Speedrun can:

- **Create a Notion onboarding page** with a first-week checklist, role/team context, and tool links.
- **Send a personalized Gmail welcome email** that can include the Notion page URL and a Slack invite link.
- **Invite the new hire to a GitHub repository** as a collaborator, preferably by GitHub username.
- **Post Slack announcements** to configured channels so the team knows who is joining.
- **Stream live step-by-step status** back to the browser using server-sent events (SSE).
- **Persist onboarding history** in Supabase so past runs, statuses, step results, and Notion links can be reviewed later.
- **Store workspace settings** such as default integration toggles, GitHub repo, Notion parent page, Slack channels, and Slack invite URL.

## How it works

```text
Next.js frontend
  ├─ Onboard form, settings, history, and Supabase login
  ↓
FastAPI backend
  ├─ /onboard streams live SSE events
  ├─ /settings reads/writes workspace settings
  └─ /onboardings stores and lists run history
  ↓
onboard.py workflow engine
  ├─ Builds prompts for Notion, Gmail, GitHub, and Slack
  ├─ Runs an OpenAI Agents SDK agent
  └─ Connects the agent to Composio Hosted MCP tools
  ↓
Real third-party actions
  └─ Notion, Gmail, GitHub, and Slack
```

The core workflow lives in `onboard.py`. It creates a Composio MCP session, gives that session to an OpenAI Agents SDK agent, then runs the integrations in this order:

1. **Notion** first, because the generated page URL can be inserted into the welcome email.
2. **Gmail** next, to send the new hire a useful welcome message.
3. **GitHub** next, to add repository access.
4. **Slack** last, to announce the teammate to configured channels.

Each step yields structured events such as `running`, `success`, `error`, or `skipped`. The FastAPI app streams those events to the frontend and stores the completed run in Supabase.

## Repository layout

```text
.
├── onboard.py                  # Core CLI and importable onboarding workflow
├── api/
│   ├── main.py                 # FastAPI API, SSE streaming, settings, history, health check
│   └── supabase_client.py      # Supabase settings and onboarding-history helpers
├── frontend/
│   ├── src/app/page.tsx        # Main onboarding form and live progress UI
│   ├── src/app/settings/       # Workspace configuration UI
│   ├── src/app/history/        # Past onboarding runs UI
│   ├── src/app/login/          # Supabase Auth login page
│   └── src/components/         # Navigation and shared UI components
├── supabase_schema.sql         # Database schema for settings and onboarding history
├── requirements.txt            # Python backend/CLI dependencies
├── Dockerfile                  # Backend container image
└── Procfile                    # Backend process command for Procfile-based hosts
```

## Tech stack

- **Backend:** Python, FastAPI, Uvicorn, Pydantic
- **Agent automation:** OpenAI Agents SDK, Composio Hosted MCP
- **Database/auth:** Supabase
- **Frontend:** Next.js, React, TypeScript, Tailwind CSS, shadcn-style UI components
- **Deployment helpers:** Dockerfile and Procfile for the FastAPI service

## Prerequisites

You will need:

- Python 3.12 or compatible Python 3.x environment
- Node.js and npm for the frontend
- A Supabase project
- A Composio account with connected Gmail, GitHub, Notion, and optionally Slack integrations
- An OpenAI API key

## Environment variables

Create a `.env` file in the repository root for the Python backend and CLI:

```env
# Required for the agent workflow
OPENAI_API_KEY=your_openai_api_key
COMPOSIO_API_KEY=your_composio_api_key
COMPOSIO_USER_ID=your_composio_user_id

# Required for FastAPI settings/history persistence
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Optional workflow defaults and fallbacks
GITHUB_REPO=owner/repository
NOTION_PARENT_PAGE_ID=your_notion_parent_page_id
SLACK_ENABLED=false
```

Create `frontend/.env.local` for the Next.js app:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
```

> **Security note:** keep `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, and `COMPOSIO_API_KEY` server-side only. Do not expose them through `NEXT_PUBLIC_` variables or commit them to git.

## Supabase setup

Run the SQL in `supabase_schema.sql` from your Supabase SQL editor. It creates:

- `settings`: a single-row workspace configuration table used by the Settings page and backend.
- `onboardings`: one row per onboarding run, including person details, selected integrations, step statuses, Notion URL, and final status.

The frontend also uses Supabase Auth. Configure the auth providers you want in Supabase, then sign in through `/login`.

## Running locally

### 1. Install backend dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the FastAPI backend

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

The backend exposes:

- `GET /health` — health check
- `POST /onboard` — starts an onboarding run and streams SSE progress events
- `GET /settings` / `PUT /settings` — reads and updates workspace settings
- `GET /onboardings` — lists onboarding history
- `GET /onboardings/{id}` — fetches one onboarding record

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Start the Next.js frontend

```bash
npm run dev
```

Open `http://localhost:3000`, sign in, configure `/settings`, then use the main page to run an onboarding.

## Running the CLI

You can run the same onboarding workflow without the web UI:

```bash
python onboard.py \
  --name "Alex Chen" \
  --email "alex@example.com" \
  --role "Backend Engineer" \
  --team "Platform" \
  --github-username "alexchen" \
  --slack-invite-url "https://join.slack.com/t/your-workspace/..."
```

Add `--verbose` to print the prompts and agent responses for debugging.

## Configuration tips

- **GitHub:** set `GITHUB_REPO` or save a repo in Settings using the `owner/repo` format. GitHub collaborator invites work best with a username.
- **Notion:** set `NOTION_PARENT_PAGE_ID` or save it in Settings. The generated onboarding page is created under that parent page.
- **Slack:** set `SLACK_ENABLED=true` before expecting Slack posts to run. Slack channels can be configured as a comma-separated list in Settings.
- **Gmail:** the welcome email automatically includes the Notion URL when Notion succeeds and the Slack invite URL when configured.
- **Defaults:** Settings controls which integrations are enabled by default on the onboarding form, but each run can toggle integrations on or off.

## Error handling and observability

The workflow is designed to keep moving when individual integrations fail:

- Missing optional configuration causes steps to be marked `skipped` rather than crashing the whole run.
- Tool authentication failures are detected from agent output and can include a Composio reconnect URL.
- OpenAI rate-limit errors are retried with backoff.
- The browser receives live step status over SSE.
- Completed runs are saved as `success`, `partial`, or `failed` in Supabase history.

## Deployment notes

The included `Dockerfile` and `Procfile` run the FastAPI backend with Uvicorn. Deploy the frontend separately as a Next.js app, set `NEXT_PUBLIC_API_URL` to the deployed backend URL, and configure both services with their required environment variables.

## Project status

This repository is a practical onboarding automation demo. It performs real actions in connected third-party tools, so use test workspaces and accounts while developing. Before production use, tighten CORS, review Supabase row-level security/auth policies, and confirm each connected tool has the minimum scopes required for your organization.
