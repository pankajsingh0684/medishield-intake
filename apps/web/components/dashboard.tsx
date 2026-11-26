"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import type { Case, DecisionKind } from "@/lib/types";
import { LogoutButton } from "@/components/logout-button";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui-state";
import { AppNav } from "@/components/app-nav";
import { useRole } from "@/lib/role";

type CatalogItem = Case & { effective_decision: DecisionKind | null };
type Result = { items: CatalogItem[]; total: number };
const pageSize = 20;

function relativeTime(value: string) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const [unit, size] = units.find(
    ([, duration]) => Math.abs(seconds) >= duration,
  ) ?? ["second", 1];
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
    Math.round(seconds / size),
    unit,
  );
}

export function Dashboard() {
  const searchParams = useSearchParams();
  const status = searchParams.get("status") ?? "";
  const decision = searchParams.get("decision") ?? "";
  const card = searchParams.get("card") ?? "";
  return (
    <DashboardContent
      key={`${status}:${decision}:${card}`}
      initialStatus={status}
      initialDecision={decision}
      initialCard={card}
    />
  );
}

function DashboardContent({
  initialStatus,
  initialDecision,
  initialCard,
}: {
  initialStatus: string;
  initialDecision: string;
  initialCard: string;
}) {
  const router = useRouter();
  const role = useRole();
  const [status, setStatus] = useState(initialStatus);
  const [decision, setDecision] = useState(initialDecision);
  const [card, setCard] = useState(initialCard);
  const [docType, setDocType] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (status) params.set("status", status);
  if (decision) params.set("decision", decision);
  if (card) params.set("card", card);
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
  const stats = useQuery({
    queryKey: ["case-stats"],
    queryFn: () =>
      fetch("/api/cases/stats", { cache: "no-store" }).then(
        async (response) => {
          if (!response.ok)
            throw new Error("Dashboard counts could not be loaded.");
          return response.json();
        },
      ),
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
          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-700">
              {role.data?.role.toLowerCase()}
            </span>
            <LogoutButton />
          </div>
        </div>
        <AppNav />
      </header>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        {stats.data && (
          <div className="flex items-center justify-between text-sm text-slate-700">
            <Link href="/" className="font-semibold underline">
              All cases: {stats.data.total}
            </Link>
            {card && (
              <button className="button-secondary" onClick={() => setCard("")}>
                Clear card filter
              </button>
            )}
          </div>
        )}
        <section
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          aria-label="Case status counts"
        >
          {stats.isLoading ? (
            [1, 2, 3, 4].map((i) => (
              <div className="panel h-20 animate-pulse" key={i} />
            ))
          ) : stats.error ? (
            <ErrorState message="Dashboard counts could not be loaded." />
          ) : (
            [
              {
                label: "Processing",
                count: stats.data?.processing ?? 0,
                href: "/?card=processing",
                tone: "neutral",
                icon: "◷",
              },
              {
                label: "Approved",
                count: stats.data?.approved ?? 0,
                href: "/?card=approved",
                tone: "green",
                icon: "✓",
              },
              {
                label: "Rejected",
                count: stats.data?.rejected ?? 0,
                href: "/?card=rejected",
                tone: "red",
                icon: "×",
              },
              {
                label: "Escalated",
                count: stats.data?.escalated ?? 0,
                href: "/?card=escalated",
                tone: "amber",
                icon: "!",
              },
              {
                label: "Needs review",
                count: stats.data?.needs_review ?? 0,
                href: "/?card=needs_review",
                tone: "amber",
                icon: "!",
              },
              {
                label: "Failed",
                count: stats.data?.failed ?? 0,
                href: "/?card=failed",
                tone: "red",
                icon: "✖",
              },
              {
                label: "No decision",
                count: stats.data?.no_decision ?? 0,
                href: "/?card=no_decision",
                tone: "neutral",
                icon: "⏳",
              },
            ]
              .filter(
                (card) =>
                  !["Failed", "No decision"].includes(card.label) ||
                  card.count > 0,
              )
              .map((card) => (
                <Link
                  href={card.href}
                  className="panel block p-4 transition hover:-translate-y-0.5 hover:shadow-md"
                  key={card.label}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-700">
                      {card.label}
                    </span>
                    <span
                      className={`flex h-7 w-7 items-center justify-center rounded-full font-bold text-white ${
                        card.tone === "green"
                          ? "bg-emerald-500"
                          : card.tone === "red"
                            ? "bg-red-500"
                            : card.tone === "amber"
                              ? "bg-amber-500"
                              : "bg-slate-400"
                      }`}
                      aria-hidden="true"
                    >
                      {card.icon}
                    </span>
                  </div>
                  <div className="mt-3 text-3xl font-bold text-slate-950">
                    {card.count}
                  </div>
                </Link>
              ))
          )}
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
                  <option key={v} value={v}>
                    {v.replaceAll("_", " ").toLowerCase()}
                  </option>
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
                  <option key={v} value={v}>
                    {v.toLowerCase()}
                  </option>
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
                  <option key={v} value={v}>
                    {v === "UNKNOWN"
                      ? "Not yet classified"
                      : v.replaceAll("_", " ").toLowerCase()}
                  </option>
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
                <thead className="sticky top-0 z-10 bg-slate-100 text-slate-700">
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
                        {item.doc_type && item.doc_type !== "UNKNOWN"
                          ? item.doc_type.replaceAll("_", " ").toLowerCase()
                          : "Not yet classified"}
                      </td>
                      <td className="p-3">
                        <time
                          dateTime={item.received_at}
                          title={new Date(item.received_at).toLocaleString()}
                        >
                          {relativeTime(item.received_at)}
                        </time>
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
