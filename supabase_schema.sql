-- Onboarding Speedrun — Supabase schema
-- Run this in the Supabase SQL editor: https://supabase.com/dashboard/project/<your-project>/sql

-- ---------------------------------------------------------------------------
-- Settings (one row, updated via the Settings page)
-- ---------------------------------------------------------------------------
create table if not exists settings (
  id int primary key default 1,
  github_repo text default '',
  notion_parent_page_id text default '',
  slack_invite_url text default '',
  slack_channels text default '#general,#social',
  default_notion boolean default true,
  default_github boolean default true,
  default_slack boolean default true,
  default_email boolean default true
);

-- Seed a default row so GET /settings always returns something
insert into settings (id) values (1) on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- Onboardings (one row per run)
-- ---------------------------------------------------------------------------
create table if not exists onboardings (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  name text not null,
  email text not null,
  role text not null,
  team text not null,
  github_username text,
  integrations jsonb default '{}'::jsonb,
  -- e.g. {"notion": true, "gmail": true, "github": false, "slack": true}
  steps jsonb default '[]'::jsonb,
  -- e.g. [{"name": "notion", "status": "success", "url": "https://..."}]
  notion_url text,
  status text default 'success'
  -- "success" | "partial" | "failed"
);

-- Index for sorting by date on the history page
create index if not exists onboardings_created_at_idx on onboardings (created_at desc);
