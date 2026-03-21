"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type StepStatus = "idle" | "running" | "success" | "error" | "skipped";

interface StepState {
  status: StepStatus;
  url?: string | null;
  error?: string;
}

const STEPS = ["notion", "gmail", "github", "slack"] as const;
type StepName = (typeof STEPS)[number];

const STEP_LABELS: Record<StepName, string> = {
  notion: "📝 Notion page",
  gmail: "📧 Welcome email",
  github: "🐙 GitHub invite",
  slack: "💬 Slack announcement",
};

function StepRow({ name, state }: { name: StepName; state: StepState }) {
  const { status, url, error } = state;
  return (
    <div className="flex items-center justify-between py-2.5">
      <span className="text-sm font-medium">{STEP_LABELS[name]}</span>
      <div className="flex items-center gap-2">
        {status === "idle" && <Badge variant="outline" className="text-gray-400">Waiting</Badge>}
        {status === "running" && (
          <Badge variant="outline" className="border-blue-300 text-blue-600 animate-pulse">Running…</Badge>
        )}
        {status === "success" && (
          <>
            <Badge className="bg-green-100 text-green-700 border-green-200">Done</Badge>
            {url && (
              <a href={url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 underline">
                View →
              </a>
            )}
          </>
        )}
        {status === "error" && (
          <Badge className="bg-red-100 text-red-700 border-red-200" title={error}>Failed</Badge>
        )}
        {status === "skipped" && <Badge variant="outline" className="text-gray-400">Skipped</Badge>}
      </div>
    </div>
  );
}

type Phase = "form" | "running" | "done";

interface Settings {
  default_notion: boolean;
  default_github: boolean;
  default_slack: boolean;
  default_email: boolean;
}

export default function Home() {
  const [phase, setPhase] = useState<Phase>("form");

  // Form fields
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [team, setTeam] = useState("");
  const [githubUsername, setGithubUsername] = useState("");

  // Integration toggles
  const [enableNotion, setEnableNotion] = useState(true);
  const [enableGmail, setEnableGmail] = useState(true);
  const [enableGithub, setEnableGithub] = useState(true);
  const [enableSlack, setEnableSlack] = useState(true);

  // Step progress
  const [steps, setSteps] = useState<Record<StepName, StepState>>({
    notion: { status: "idle" },
    gmail: { status: "idle" },
    github: { status: "idle" },
    slack: { status: "idle" },
  });
  const [notionUrl, setNotionUrl] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);

  // Load default toggles from settings
  useEffect(() => {
    fetch(`${API}/settings`)
      .then((r) => r.json())
      .then((s: Settings) => {
        setEnableNotion(s.default_notion ?? true);
        setEnableGmail(s.default_email ?? true);
        setEnableGithub(s.default_github ?? true);
        setEnableSlack(s.default_slack ?? true);
      })
      .catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPhase("running");
    setStreamError(null);
    setNotionUrl(null);
    setSteps({
      notion: { status: "idle" },
      gmail: { status: "idle" },
      github: { status: "idle" },
      slack: { status: "idle" },
    });

    try {
      const res = await fetch(`${API}/onboard`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          email,
          role,
          team,
          github_username: githubUsername || undefined,
          enable_notion: enableNotion,
          enable_gmail: enableGmail,
          enable_github: enableGithub,
          enable_slack: enableSlack,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`API error: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (!line) continue;
          try {
            const event = JSON.parse(line);
            handleEvent(event);
          } catch {
            // ignore parse errors
          }
        }
      }
    } catch (err) {
      setStreamError(err instanceof Error ? err.message : String(err));
      setPhase("done");
    }
  }

  function handleEvent(event: Record<string, unknown>) {
    const step = event.step as string;
    const status = event.status as string;

    if (step === "done") {
      setNotionUrl((event.notion_url as string) ?? null);
      setPhase("done");
      return;
    }

    if (step === "init") return;

    if (STEPS.includes(step as StepName)) {
      setSteps((prev) => ({
        ...prev,
        [step]: {
          status: status as StepStatus,
          url: (event.url as string) ?? prev[step as StepName].url,
          error: (event.error as string) ?? undefined,
        },
      }));
    }
  }

  function reset() {
    setPhase("form");
    setName("");
    setEmail("");
    setRole("");
    setTeam("");
    setGithubUsername("");
    setStreamError(null);
    setNotionUrl(null);
  }

  const anyError = Object.values(steps).some((s) => s.status === "error");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Onboard a new hire</h1>
        <p className="text-gray-500 text-sm mt-1">
          Fill in the details below. We&apos;ll set up Notion, send a welcome email, invite to GitHub, and post to Slack.
        </p>
      </div>

      {phase === "form" && (
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="name">Full name</Label>
                  <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Alex Chen" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="alex@company.com" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="role">Role</Label>
                  <Input id="role" value={role} onChange={(e) => setRole(e.target.value)} required placeholder="Backend Engineer" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="team">Team</Label>
                  <Input id="team" value={team} onChange={(e) => setTeam(e.target.value)} required placeholder="Platform" />
                </div>
                <div className="space-y-1.5 col-span-2">
                  <Label htmlFor="github">GitHub username <span className="text-gray-400 font-normal">(optional)</span></Label>
                  <Input id="github" value={githubUsername} onChange={(e) => setGithubUsername(e.target.value)} placeholder="alexchen" />
                </div>
              </div>

              <Separator />

              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-700">Run these integrations</p>
                <div className="grid grid-cols-2 gap-3">
                  {(
                    [
                      ["notion", "📝 Notion page", enableNotion, setEnableNotion],
                      ["gmail", "📧 Welcome email", enableGmail, setEnableGmail],
                      ["github", "🐙 GitHub invite", enableGithub, setEnableGithub],
                      ["slack", "💬 Slack post", enableSlack, setEnableSlack],
                    ] as [string, string, boolean, (v: boolean) => void][]
                  ).map(([id, label, checked, setter]) => (
                    <div key={id} className="flex items-center justify-between rounded-lg border px-3 py-2.5">
                      <Label htmlFor={`toggle-${id}`} className="cursor-pointer text-sm">{label}</Label>
                      <Switch id={`toggle-${id}`} checked={checked} onCheckedChange={setter} />
                    </div>
                  ))}
                </div>
              </div>

              <Button type="submit" className="w-full">
                Start onboarding →
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {(phase === "running" || phase === "done") && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {phase === "running"
                ? `Onboarding ${name}…`
                : !anyError
                ? `🎉 ${name} is all set!`
                : `⚠️ Onboarding finished with issues`}
            </CardTitle>
            {phase === "done" && notionUrl && (
              <CardDescription>
                <a href={notionUrl} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                  View Notion onboarding page →
                </a>
              </CardDescription>
            )}
          </CardHeader>
          <CardContent className="space-y-0.5">
            <div className="divide-y">
              {STEPS.map((s) => (
                <StepRow key={s} name={s} state={steps[s]} />
              ))}
            </div>

            {streamError && (
              <p className="text-sm text-red-600 mt-3 p-3 bg-red-50 rounded-md">{streamError}</p>
            )}

            {phase === "done" && (
              <div className="pt-4">
                <Button variant="outline" className="w-full" onClick={reset}>
                  Onboard another person
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
