"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Case, DecisionKind } from "@/lib/types";
import { LogoutButton } from "@/components/logout-button";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui-state";

type CatalogItem = Case & { effective_decision: DecisionKind | null };
type Result = { items: CatalogItem[]; total: number };
const pageSize = 20;

function statusCount(items: CatalogItem[], kind: string) {
  if (kind === "Processing")
    return items.filter(
      (item) =>
        !["DECIDED", "OVERRIDDEN", "NEEDS_REVIEW", "FAILED"].includes(
          item.status,
        ),
    ).length;
  if (kind === "Escalated")
    return items.filter(
      (item) =>
        item.effective_decision === "ESCALATE" ||
        ["NEEDS_REVIEW", "FAILED"].includes(item.status),
    ).length;
  return items.filter((item) => item.effective_decision === kind.toUpperCase())
    .length;
}

export function Dashboard() {
  const router = useRouter();
  const [status, setStatus] = useState("");
  const [decision, setDecision] = useState("");
  const [docType, setDocType] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (status) params.set("status", status);
  if (decision) params.set("decision", decision);
  if (docType) params.set("doc_type", docType);
  if (search) params.set("q", search);
  const query = useQuery<Result>({
    queryKey: ["cases", params.toString()],
    queryFn: () =>
      fetch(`/api/cases?${params}`, { cache: "no-store" }).then(
        async (response) => {
          if (response.status === 401) {
            router.push("/login");
            throw new Error("Your session has expired.");
          }
          if (!response.ok)
            throw new Error(
              response.status === 403
                ? "You do not have access to these cases."
                : response.status === 429
                  ? "Too many requests. Please wait."
                  : "The cases could not be loaded.",
            );
          return response.json();
        },
      ),
    refetchInterval: (q) =>
      q.state.data?.items.some(
        (item) =>
          !["DECIDED", "OVERRIDDEN", "FAILED", "NEEDS_REVIEW"].includes(
            item.status,
          ),
      )
        ? 5000
        : false,
  });
  const totalPages = Math.max(
    1,
    Math.ceil((query.data?.total ?? 0) / pageSize),
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <h1 className="text-xl font-bold">MediShield cases</h1>
            <p className="text-sm text-slate-600">Document intake dashboard</p>
          </div>
          <LogoutButton />
        </div>
      </header>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <section
          className="grid gap-3 sm:grid-cols-4"
          aria-label="Status counts for this page"
        >
          {["Processing", "Approved", "Rejected", "Escalated"].map((kind) => (
            <div className="panel p-4" key={kind}>
              <div className="text-sm text-slate-600">{kind}</div>
              <div className="text-2xl font-bold">
                {statusCount(query.data?.items ?? [], kind)}
              </div>
            </div>
          ))}
        </section>
        <section className="panel p-4" aria-label="Case filters">
          <div className="grid gap-3 md:grid-cols-4">
            <label className="text-sm font-medium">
              Search case ID
              <input
                className="input mt-1"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="Case or member ID"
              />
            </label>
            <label className="text-sm font-medium">
              Status
              <select
                className="input mt-1"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All statuses</option>
                {[
                  "RECEIVED",
                  "CLASSIFIED",
                  "PROCESSING",
                  "FRAUD_CHECK",
                  "AGGREGATED",
                  "DECIDED",
                  "NEEDS_REVIEW",
                  "OVERRIDDEN",
                  "FAILED",
                ].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="text-sm font-medium">
              Decision
              <select
                className="input mt-1"
                value={decision}
                onChange={(e) => {
                  setDecision(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All decisions</option>
                {["APPROVE", "REJECT", "ESCALATE"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="text-sm font-medium">
              Document type
              <select
                className="input mt-1"
                value={docType}
                onChange={(e) => {
                  setDocType(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All document types</option>
                {[
                  "CLAIM_FORM",
                  "ID_DOCUMENT",
                  "DISCHARGE_SUMMARY",
                  "PRESCRIPTION",
                  "POLICY_AMENDMENT",
                  "UNKNOWN",
                ].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          </div>
        </section>
        {query.isLoading && <LoadingState />}
        {query.error && <ErrorState message={(query.error as Error).message} />}
        {query.data?.items.length === 0 && (
          <EmptyState message="No cases match these filters." />
        )}
        {!!query.data?.items.length && (
          <section className="panel overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">MediShield intake cases</caption>
                <thead className="bg-slate-100 text-slate-700">
                  <tr>
                    <th className="p-3">Case ID</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Document type</th>
                    <th className="p-3">Received</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((item) => (
                    <tr
                      className="border-t hover:bg-slate-50"
                      key={item.case_id}
                    >
                      <td className="p-3">
                        <Link
                          className="font-mono text-blue-800 underline underline-offset-2"
                          href={`/cases/${item.case_id}`}
                        >
                          {item.case_id}
                        </Link>
                      </td>
                      <td className="p-3">
                        <StatusBadge item={item} />
                      </td>
                      <td className="p-3">
                        {item.doc_type?.replaceAll("_", " ") ?? "Pending"}
                      </td>
                      <td className="p-3">
                        {new Date(item.received_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t p-3 text-sm">
              <span>{query.data.total} cases</span>
              <div className="flex items-center gap-2">
                <button
                  className="button-secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((v) => v - 1)}
                >
                  Previous
                </button>
                <span>
                  Page {page} of {totalPages}
                </span>
                <button
                  className="button-secondary"
                  disabled={page >= totalPages}
                  onClick={() => setPage((v) => v + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
