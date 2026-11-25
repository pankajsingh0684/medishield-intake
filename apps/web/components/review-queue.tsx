"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { useRole } from "@/lib/role";
import type { ReviewQueue } from "@/lib/types";
import { AppNav } from "@/components/app-nav";
import { LogoutButton } from "@/components/logout-button";
import { OverrideDialog } from "@/components/override-dialog";
import { StatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui-state";

export function ReviewQueueView() {
  const queue = useQuery<ReviewQueue>({
    queryKey: ["review-queue"],
    queryFn: () => apiFetch("/review-queue?page_size=100"),
    refetchInterval: 5000,
  });
  const role = useRole();
  function age(date: string) {
    const minutes = Math.max(
      0,
      Math.floor(
        ((queue.dataUpdatedAt || 0) - new Date(date).getTime()) / 60000,
      ),
    );
    return minutes < 60
      ? `${minutes}m`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)}h`
        : `${Math.floor(minutes / 1440)}d`;
  }
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <h1 className="text-xl font-bold">Review queue</h1>
            <AppNav />
          </div>
          <LogoutButton />
        </div>
      </header>
      <main className="mx-auto max-w-7xl space-y-4 p-5">
        {queue.isLoading && <LoadingState />}
        {queue.error && <ErrorState message={(queue.error as Error).message} />}
        {queue.data?.items.length === 0 && (
          <EmptyState message="No cases need review." />
        )}
        {queue.data?.items.map((item) => {
          const reason =
            item.original_decision?.justification ??
            item.agent_runs.find((run) => run.error)?.error ??
            "Manual review required";
          return (
            <article className="panel p-4" key={item.case_id}>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <Link
                    className="break-all font-mono text-sm font-semibold text-blue-800 underline"
                    href={`/cases/${item.case_id}`}
                  >
                    {item.case_id}
                  </Link>
                  <div className="mt-2 flex items-center gap-2">
                    <StatusBadge item={item} />
                    <span className="text-sm text-slate-600">
                      Age {age(item.received_at)}
                    </span>
                  </div>
                  <p className="mt-3 max-w-3xl text-sm">{reason}</p>
                </div>
                {role.data && role.data.role !== "AUDITOR" && (
                  <OverrideDialog item={item} />
                )}
              </div>
            </article>
          );
        })}
      </main>
    </div>
  );
}
