"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Step {
  name: string;
  status: "success" | "error" | "skipped";
  url?: string | null;
}

interface Onboarding {
  id: string;
  created_at: string;
  name: string;
  email: string;
  role: string;
  team: string;
  github_username?: string;
  integrations: Record<string, boolean>;
  steps: Step[];
  notion_url?: string | null;
  status: "success" | "partial" | "failed";
}

const STEP_ICONS: Record<string, string> = {
  notion: "📝",
  gmail: "📧",
  github: "🐙",
  slack: "💬",
};

function StatusBadge({ status }: { status: string }) {
  if (status === "success") return <Badge className="bg-green-100 text-green-700 border-green-200">Success</Badge>;
  if (status === "partial") return <Badge className="bg-yellow-100 text-yellow-700 border-yellow-200">Partial</Badge>;
  return <Badge className="bg-red-100 text-red-700 border-red-200">Failed</Badge>;
}

function StepPills({ steps }: { steps: Step[] }) {
  return (
    <div className="flex gap-1 flex-wrap">
      {steps.map((s, i) => (
        <span
          key={`${s.name}-${i}`}
          title={`${s.name}: ${s.status}`}
          className={`text-xs px-1.5 py-0.5 rounded ${
            s.status === "success"
              ? "bg-green-50 text-green-700"
              : s.status === "error"
              ? "bg-red-50 text-red-600"
              : "bg-gray-100 text-gray-400"
          }`}
        >
          {STEP_ICONS[s.name] ?? s.name}
        </span>
      ))}
    </div>
  );
}

function DetailPanel({ row }: { row: Onboarding }) {
  return (
    <div className="px-4 pb-4 space-y-3 border-t bg-gray-50/50">
      <div className="pt-3 grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
        <div><span className="text-gray-500">Email:</span> {row.email}</div>
        {row.github_username && <div><span className="text-gray-500">GitHub:</span> @{row.github_username}</div>}
        {row.notion_url && (
          <div className="col-span-2">
            <span className="text-gray-500">Notion:</span>{" "}
            <a href={row.notion_url} target="_blank" rel="noreferrer" className="text-blue-600 underline">
              View page →
            </a>
          </div>
        )}
      </div>
      <div className="space-y-1">
        {row.steps.map((s, i) => (
          <div key={`${s.name}-${i}`} className="flex items-center gap-2 text-sm">
            <span>{STEP_ICONS[s.name] ?? s.name}</span>
            <span className="capitalize">{s.name}</span>
            <span className={`text-xs ${s.status === "success" ? "text-green-600" : s.status === "error" ? "text-red-600" : "text-gray-400"}`}>
              {s.status}
            </span>
            {s.url && (
              <a href={s.url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 underline">
                link
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function HistoryPage() {
  const [rows, setRows] = useState<Onboarding[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/onboardings`)
      .then((r) => r.json())
      .then(setRows)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function fmt(iso: string) {
    return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">History</h1>
        <p className="text-gray-500 text-sm mt-1">All past onboarding runs.</p>
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-400 text-sm">
            No onboardings yet. Go onboard someone! 🚀
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-0">
            <CardTitle className="text-base">{rows.length} onboarding{rows.length !== 1 ? "s" : ""}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Role / Team</TableHead>
                  <TableHead>Steps</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.flatMap((row) => {
                  const main = (
                    <TableRow
                      key={row.id}
                      className="cursor-pointer hover:bg-gray-50"
                      onClick={() => setExpanded(expanded === row.id ? null : row.id)}
                    >
                      <TableCell className="font-medium">{row.name}</TableCell>
                      <TableCell className="text-gray-500 text-sm">
                        {row.role} · {row.team}
                      </TableCell>
                      <TableCell>
                        <StepPills steps={row.steps} />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={row.status} />
                      </TableCell>
                      <TableCell className="text-gray-400 text-sm">{fmt(row.created_at)}</TableCell>
                    </TableRow>
                  );
                  if (expanded !== row.id) return [main];
                  return [
                    main,
                    <TableRow key={`${row.id}-detail`}>
                      <TableCell colSpan={5} className="p-0">
                        <DetailPanel row={row} />
                      </TableCell>
                    </TableRow>,
                  ];
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
