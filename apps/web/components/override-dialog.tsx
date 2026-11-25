"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { CaseDetail, DocType } from "@/lib/types";

export function OverrideDialog({
  item,
  onComplete,
}: {
  item: CaseDetail;
  onComplete?: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [action, setAction] = useState<"APPROVE" | "REJECT" | "RECLASSIFY">(
    "APPROVE",
  );
  const [reason, setReason] = useState("");
  const [docType, setDocType] = useState<DocType>("UNKNOWN");
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () =>
      action === "RECLASSIFY"
        ? apiFetch(`/cases/${item.case_id}/reclassify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ doc_type: docType, reason }),
          })
        : apiFetch(`/cases/${item.case_id}/override`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ to_decision: action, reason }),
          }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["case", item.case_id] }),
        client.invalidateQueries({ queryKey: ["review-queue"] }),
        client.invalidateQueries({ queryKey: ["audit", item.case_id] }),
      ]);
      dialog.current?.close();
      onComplete?.();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (reason.trim().length >= 10) mutation.mutate();
  }
  return (
    <>
      <button
        className="button-primary"
        type="button"
        onClick={() => dialog.current?.showModal()}
      >
        Review action
      </button>
      <dialog
        ref={dialog}
        className="m-auto w-full max-w-lg rounded-lg border border-slate-400 p-0 shadow-xl"
        onClose={() => mutation.reset()}
      >
        <form className="p-5" onSubmit={submit}>
          <h2 className="text-lg font-bold">Review case</h2>
          <p className="mt-1 break-all font-mono text-xs text-slate-600">
            {item.case_id}
          </p>
          <label className="mt-4 block text-sm font-medium">
            Action
            <select
              className="input mt-1"
              value={action}
              onChange={(event) =>
                setAction(event.target.value as typeof action)
              }
            >
              <option value="APPROVE">Approve</option>
              <option value="REJECT">Reject</option>
              <option value="RECLASSIFY">Reclassify</option>
            </select>
          </label>
          {action === "RECLASSIFY" && (
            <label className="mt-3 block text-sm font-medium">
              Document type
              <select
                className="input mt-1"
                value={docType}
                onChange={(event) => setDocType(event.target.value as DocType)}
              >
                {[
                  "CLAIM_FORM",
                  "ID_DOCUMENT",
                  "DISCHARGE_SUMMARY",
                  "PRESCRIPTION",
                  "POLICY_AMENDMENT",
                  "UNKNOWN",
                ].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          )}
          <label className="mt-3 block text-sm font-medium">
            Reason
            <textarea
              className="input mt-1 min-h-24"
              minLength={10}
              required
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <span className="text-xs text-slate-600">
              At least 10 characters.
            </span>
          </label>
          {mutation.error && (
            <p role="alert" className="mt-3 text-sm text-red-800">
              {(mutation.error as Error).message}
            </p>
          )}
          <div className="mt-5 flex justify-end gap-2">
            <button
              className="button-secondary"
              type="button"
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button
              className="button-primary"
              disabled={mutation.isPending || reason.trim().length < 10}
              type="submit"
            >
              {mutation.isPending ? "Saving…" : "Submit action"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
