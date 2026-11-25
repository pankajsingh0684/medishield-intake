"use client";

/* eslint-disable @next/next/no-img-element -- signed MinIO URLs are deliberately not proxied or persisted. */

import { useCallback, useEffect, useState } from "react";

export function DocumentViewer({
  url,
  mimeType,
}: {
  url: string;
  mimeType: string;
}) {
  const [zoom, setZoom] = useState(100);
  const [page, setPage] = useState(1);
  const changeZoom = useCallback(
    (amount: number) =>
      setZoom((value) => Math.min(250, Math.max(50, value + amount))),
    [],
  );
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).matches("input, textarea, select"))
        return;
      if (event.key === "+" || event.key === "=") changeZoom(10);
      if (event.key === "-") changeZoom(-10);
      if (event.key === "ArrowRight") setPage((value) => value + 1);
      if (event.key === "ArrowLeft") setPage((value) => Math.max(1, value - 1));
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [changeZoom]);
  const isPdf = mimeType === "application/pdf";
  return (
    <section className="panel overflow-hidden" aria-label="Document viewer">
      <div className="flex flex-wrap items-center gap-2 border-b bg-slate-50 p-3">
        <button
          className="button-secondary"
          type="button"
          onClick={() => changeZoom(-10)}
          aria-label="Zoom out"
        >
          −
        </button>
        <span aria-live="polite" className="min-w-14 text-center text-sm">
          {zoom}%
        </span>
        <button
          className="button-secondary"
          type="button"
          onClick={() => changeZoom(10)}
          aria-label="Zoom in"
        >
          +
        </button>
        <span className="mx-1 h-6 border-l" />
        <button
          className="button-secondary"
          type="button"
          onClick={() => setPage((value) => Math.max(1, value - 1))}
        >
          Previous page
        </button>
        <label className="text-sm">
          Page{" "}
          <input
            className="input ml-1 inline-block w-16"
            aria-label="Page number"
            min={1}
            type="number"
            value={page}
            onChange={(event) =>
              setPage(Math.max(1, Number(event.target.value) || 1))
            }
          />
        </label>
        <button
          className="button-secondary"
          type="button"
          onClick={() => setPage((value) => value + 1)}
        >
          Next page
        </button>
        <p className="w-full text-xs text-slate-600">
          Keyboard: +/− zoom, left/right page.
        </p>
      </div>
      <div className="min-h-[70vh] overflow-auto bg-slate-200 p-4">
        {isPdf ? (
          <iframe
            title="Case document PDF"
            className="h-[70vh] w-full bg-white"
            src={`${url}#page=${page}&zoom=${zoom}`}
          />
        ) : (
          <div className="flex justify-center">
            <img
              alt="Submitted case document"
              className="max-w-none object-contain shadow"
              src={url}
              style={{ width: `${zoom}%` }}
            />
          </div>
        )}
      </div>
    </section>
  );
}
