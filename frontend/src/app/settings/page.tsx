"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Settings {
  github_repo: string;
  notion_parent_page_id: string;
  slack_invite_url: string;
  slack_channels: string;
  slack_workspace: string;
  default_notion: boolean;
  default_github: boolean;
  default_slack: boolean;
  default_email: boolean;
}

const DEFAULTS: Settings = {
  github_repo: "",
  notion_parent_page_id: "",
  slack_invite_url: "",
  slack_channels: "#general,#social",
  slack_workspace: "",
  default_notion: true,
  default_github: true,
  default_slack: true,
  default_email: true,
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API}/settings`)
      .then((r) => r.json())
      .then((s) => setSettings({ ...DEFAULTS, ...s }))
      .catch(() => toast.error("Could not load settings — is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch(`${API}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      toast.success("Settings saved.");
    } catch {
      toast.error("Failed to save settings.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-gray-500">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-gray-500 text-sm mt-1">Workspace configuration — saved and reused for every onboarding.</p>
      </div>

      <form onSubmit={save} className="space-y-6">
        {/* Integrations config */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Workspace config</CardTitle>
            <CardDescription>These values are used for every onboarding run.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="github_repo">GitHub repo <span className="text-gray-400 font-normal">(owner/repo)</span></Label>
              <Input
                id="github_repo"
                value={settings.github_repo}
                onChange={(e) => set("github_repo", e.target.value)}
                placeholder="acme/onboarding"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="notion_page_id">Notion parent page ID</Label>
              <Input
                id="notion_page_id"
                value={settings.notion_parent_page_id}
                onChange={(e) => set("notion_parent_page_id", e.target.value)}
                placeholder="32ae90f2babd802dbb26dd8b2c58ac15"
              />
              <p className="text-xs text-gray-400">The ID from your Notion page URL: notion.so/&lt;page-id&gt;</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="slack_invite_url">Slack invite link</Label>
              <Input
                id="slack_invite_url"
                value={settings.slack_invite_url}
                onChange={(e) => set("slack_invite_url", e.target.value)}
                placeholder="https://join.slack.com/t/yourworkspace/..."
              />
              <p className="text-xs text-gray-400">Included in the welcome email so the new hire can join Slack.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="slack_workspace">Slack workspace URL</Label>
              <Input
                id="slack_workspace"
                value={settings.slack_workspace}
                onChange={(e) => set("slack_workspace", e.target.value)}
                placeholder="yourcompany.slack.com"
              />
              <p className="text-xs text-gray-400">Your Slack workspace domain, e.g. acme.slack.com</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="slack_channels">Slack channels</Label>
              <Input
                id="slack_channels"
                value={settings.slack_channels}
                onChange={(e) => set("slack_channels", e.target.value)}
                placeholder="#general,#social"
              />
              <p className="text-xs text-gray-400">Comma-separated. First channel gets a welcome message, second gets a brief announcement.</p>
            </div>
          </CardContent>
        </Card>

        {/* Default toggles */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Default integrations</CardTitle>
            <CardDescription>Pre-select which integrations are enabled when starting a new onboarding.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {(
                [
                  ["default_notion", "📝 Notion page"],
                  ["default_email", "📧 Welcome email"],
                  ["default_github", "🐙 GitHub invite"],
                  ["default_slack", "💬 Slack announcement"],
                ] as [keyof Settings, string][]
              ).map(([key, label]) => (
                <div key={key} className="flex items-center justify-between">
                  <Label htmlFor={key} className="cursor-pointer text-sm">{label}</Label>
                  <Switch
                    id={key}
                    checked={settings[key] as boolean}
                    onCheckedChange={(v) => set(key, v)}
                  />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Separator />

        <Button type="submit" disabled={saving} className="w-full">
          {saving ? "Saving…" : "Save settings"}
        </Button>
      </form>
    </div>
  );
}
