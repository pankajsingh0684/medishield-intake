"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import type { AgentRun, AuditEvent, CaseDetail } from "@/lib/types";
import { DocumentViewer } from "@/components/document-viewer";
import { LogoutButton } from "@/components/logout-button";
import { StatusBadge } from "@/components/status-badge";
import { ErrorState, LoadingState } from "@/components/ui-state";

function JsonPanel({ run }: { run: AgentRun }) {
  return (
    <details
      className="border-b last:border-b-0"
      open={run.agent === "classifier"}
    >
      <summary className="flex items-center justify-between p-3 font-semibold">
        <span>{run.agent}</span>
        <span className="text-xs font-normal text-slate-600">
          {run.status} ·{" "}
          {run.confidence == null
            ? "No confidence"
            : `${Math.round(run.confidence * 100)}%`}
        </span>
      </summary>
      <div className="px-3 pb-3">
        <dl className="mb-2 grid grid-cols-2 gap-x-3 text-xs text-slate-600">
          <dt>Version</dt>
          <dd>{run.agent_version}</dd>
          <dt>Model</dt>
          <dd>{run.model ?? "—"}</dd>
          <dt>Prompt</dt>
          <dd>{run.prompt_version ?? "—"}</dd>
        </dl>
        {run.error ? (
          <p role="alert" className="text-sm text-red-800">
            {run.error}
          </p>
        ) : (
          <pre className="overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">
            {JSON.stringify(run.output, null, 2)}
          </pre>
        )}
      </div>
    </details>
  );
}

export function CaseDetailView({ id }: { id: string }) {
  const [tab, setTab] = useState<"agents" | "audit">("agents");
  const detail = useQuery<CaseDetail>({
    queryKey: ["case", id],
    queryFn: () => apiFetch(`/cases/${id}`),
    refetchInterval: (q) =>
      q.state.data &&
      !["DECIDED", "OVERRIDDEN", "FAILED", "NEEDS_REVIEW"].includes(
        q.state.data.status,
      )
        ? 5000
        : false,
  });
  const audit = useQuery<AuditEvent[]>({
    queryKey: ["audit", id],
    queryFn: () => apiFetch(`/cases/${id}/audit`),
    enabled: tab === "audit",
  });
  if (detail.isLoading)
    return (
      <main className="mx-auto max-w-7xl p-5">
        <LoadingState />
      </main>
    );
  if (detail.error || !detail.data)
    return (
      <main className="mx-auto max-w-7xl p-5">
        <ErrorState
          message={(detail.error as Error)?.message ?? "Case not found."}
        />
      </main>
    );
  const item = detail.data;
  const order = ["classifier", "ocr", "claims", "kyc", "policy", "fraud"];
  const runs = [...item.agent_runs].sort(
    (a, b) => order.indexOf(a.agent) - order.indexOf(b.agent),
  );
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <Link
              href="/"
              className="text-sm font-semibold text-blue-800 underline"
            >
              ← Cases
            </Link>
            <h1 className="mt-1 font-mono text-lg font-bold">{item.case_id}</h1>
          </div>
          <LogoutButton />
        </div>
      </header>
      <main className="mx-auto grid max-w-7xl gap-5 p-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(340px,.7fr)]">
        <DocumentViewer url={item.document_url} mimeType={item.mime_type} />
        <div className="space-y-4">
          <section className="panel p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs font-semibold uppercase text-slate-600">
                  Case status
                </div>
                <div className="mt-2">
                  <StatusBadge item={item} />
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs text-slate-600">Document</div>
                <div className="text-sm font-semibold">
                  {item.doc_type?.replaceAll("_", " ") ?? "Pending"}
                </div>
              </div>
            </div>
          </section>
          <section className="panel p-4" aria-label="Decision">
            <h2 className="text-lg font-bold">Decision</h2>
            {item.original_decision ? (
              <>
                <div className="mt-3 flex items-end justify-between">
                  <span className="font-semibold">
                    {item.effective_decision ?? "Pending"}
                  </span>
                  <span className="text-sm">
                    Confidence{" "}
                    {Math.round(item.original_decision.confidence * 100)}%
                  </span>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm">
                  {item.original_decision.justification}
                </p>
                <details className="mt-3">
                  <summary className="font-semibold">Rule trace</summary>
                  <pre className="mt-2 overflow-auto rounded bg-slate-50 p-3 text-xs">
                    {JSON.stringify(item.original_decision.rule_trace, null, 2)}
                  </pre>
                </details>
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-600">
                No decision has been recorded.
              </p>
            )}
            <details className="mt-4 border-t pt-3">
              <summary className="font-semibold">
                Overrides ({item.overrides.length})
              </summary>
              {item.overrides.length ? (
                <ol className="mt-2 space-y-2">
                  {item.overrides.map((override) => (
                    <li
                      key={override.override_id}
                      className="rounded bg-slate-50 p-2 text-sm"
                    >
                      <strong>
                        {override.from_decision ?? "None"} →{" "}
                        {override.to_decision}
                      </strong>
                      <p>{override.reason}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-2 text-sm text-slate-600">No overrides.</p>
              )}
            </details>
          </section>
          <section className="panel overflow-hidden" aria-label="Case analysis">
            <div className="flex border-b" role="tablist">
              <button
                role="tab"
                aria-selected={tab === "agents"}
                className={`flex-1 p-3 font-semibold ${tab === "agents" ? "border-b-4 border-blue-700" : ""}`}
                onClick={() => setTab("agents")}
              >
                Agent outputs
              </button>
              <button
                role="tab"
                aria-selected={tab === "audit"}
                className={`flex-1 p-3 font-semibold ${tab === "audit" ? "border-b-4 border-blue-700" : ""}`}
                onClick={() => setTab("audit")}
              >
                Audit log
              </button>
            </div>
            {tab === "agents" ? (
              runs.length ? (
                runs.map((run) => <JsonPanel key={run.run_id} run={run} />)
              ) : (
                <p className="p-5 text-sm text-slate-600">
                  No agent outputs are available.
                </p>
              )
            ) : audit.isLoading ? (
              <LoadingState />
            ) : audit.error ? (
              <ErrorState message={(audit.error as Error).message} />
            ) : (
              <ol className="divide-y">
                {audit.data?.map((event) => (
                  <li className="p-3 text-sm" key={event.event_id}>
                    <div className="font-semibold">{event.event_type}</div>
                    <time className="text-xs text-slate-600">
                      {new Date(event.ts).toLocaleString()}
                    </time>
                    <pre className="mt-2 overflow-auto whitespace-pre-wrap bg-slate-50 p-2 text-xs">
                      {JSON.stringify(event.payload, null, 2)}
                    </pre>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
