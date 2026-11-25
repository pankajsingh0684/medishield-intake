"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useRole } from "@/lib/role";
import type { PolicyList } from "@/lib/types";
import { AppNav } from "@/components/app-nav";
import { LogoutButton } from "@/components/logout-button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui-state";

export function PoliciesView() {
  const role = useRole();
  const client = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const [error, setError] = useState("");
  const policies = useQuery<PolicyList>({
    queryKey: ["policies"],
    queryFn: () => apiFetch("/policies"),
    refetchInterval: (q) =>
      q.state.data?.items.some((policy) =>
        ["PENDING", "PROCESSING"].includes(policy.ingest_status ?? ""),
      )
        ? 5000
        : false,
  });
  const upload = useMutation({
    mutationFn: async (data: FormData) => {
      const response = await fetch("/api/backend/policies", {
        method: "POST",
        body: data,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.error?.message ?? "The policy could not be uploaded.",
        );
      }
    },
    onSuccess: () => {
      form.current?.reset();
      setError("");
      client.invalidateQueries({ queryKey: ["policies"] });
    },
    onError: (cause) => setError((cause as Error).message),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const from = String(data.get("effective_from"));
    const to = String(data.get("effective_to"));
    if (to && to < from) {
      setError("Effective end must not precede effective start.");
      return;
    }
    upload.mutate(data);
  }
  const canUpload =
    role.data && ["SUPERVISOR", "ADMIN"].includes(role.data.role);
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <h1 className="text-xl font-bold">Policies</h1>
            <AppNav />
          </div>
          <LogoutButton />
        </div>
      </header>
      <main className="mx-auto grid max-w-7xl gap-5 p-5 lg:grid-cols-[1fr_360px]">
        <section>
          {policies.isLoading && <LoadingState />}
          {policies.error && (
            <ErrorState message={(policies.error as Error).message} />
          )}
          {policies.data?.items.length === 0 && (
            <EmptyState message="No policies have been uploaded." />
          )}
          {!!policies.data?.items.length && (
            <div className="panel overflow-hidden">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Uploaded policies</caption>
                <thead className="bg-slate-100">
                  <tr>
                    <th className="p-3">Name</th>
                    <th className="p-3">Version</th>
                    <th className="p-3">Effective dates</th>
                    <th className="p-3">Ingestion</th>
                  </tr>
                </thead>
                <tbody>
                  {policies.data.items.map((policy) => (
                    <tr className="border-t" key={policy.policy_id}>
                      <td className="p-3 font-semibold">
                        {policy.name ?? policy.plan_code ?? "Policy"}
                      </td>
                      <td className="p-3">{policy.version ?? "—"}</td>
                      <td className="p-3">
                        {policy.effective_from ?? "—"}
                        {policy.effective_to
                          ? ` to ${policy.effective_to}`
                          : ""}
                      </td>
                      <td className="p-3">
                        <span className="rounded border px-2 py-1 text-xs font-semibold">
                          {policy.ingest_status ?? "UNKNOWN"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        {canUpload && (
          <section className="panel p-4">
            <h2 className="text-lg font-bold">Upload policy PDF</h2>
            <form ref={form} className="mt-4 space-y-3" onSubmit={submit}>
              <label className="block text-sm font-medium">
                Name
                <input
                  className="input mt-1"
                  name="name"
                  required
                  placeholder="MediShield Gold Plan"
                />
              </label>
              <label className="block text-sm font-medium">
                Version
                <input className="input mt-1" name="version" required />
              </label>
              <label className="block text-sm font-medium">
                Effective from
                <input
                  className="input mt-1"
                  name="effective_from"
                  type="date"
                  required
                />
              </label>
              <label className="block text-sm font-medium">
                Effective to
                <input className="input mt-1" name="effective_to" type="date" />
              </label>
              <label className="block text-sm font-medium">
                PDF
                <input
                  className="input mt-1"
                  name="file"
                  type="file"
                  accept="application/pdf,.pdf"
                  required
                />
              </label>
              {error && (
                <p role="alert" className="text-sm text-red-800">
                  {error}
                </p>
              )}
              <button
                className="button-primary w-full"
                disabled={upload.isPending}
                type="submit"
              >
                {upload.isPending ? "Uploading…" : "Upload policy"}
              </button>
            </form>
          </section>
        )}
      </main>
    </div>
  );
}
