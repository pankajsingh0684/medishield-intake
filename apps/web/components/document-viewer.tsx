"use client";

/* eslint-disable @next/next/no-img-element -- signed MinIO URLs are deliberately not proxied or persisted. */

import { useCallback, useEffect, useState } from "react";

type BoundingBox = {
  text: string;
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
};

export function DocumentViewer({
  url,
  mimeType,
  selectedBox,
}: {
  url: string;
  mimeType: string;
  selectedBox?: BoundingBox | null;
}) {
  const [zoom, setZoom] = useState(100);
  const [page, setPage] = useState(selectedBox?.page ?? 1);
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
            <div className="relative" style={{ width: `${zoom}%` }}>
              <img
                alt="Submitted case document"
                className="w-full max-w-none object-contain shadow"
                src={url}
                draggable={false}
              />
              {selectedBox?.page === page && (
                <div
                  aria-label={`Highlighted field: ${selectedBox.text}`}
                  className="pointer-events-none absolute border-4 border-yellow-500 bg-yellow-300/30"
                  style={{
                    left: `${selectedBox.x * 100}%`,
                    top: `${selectedBox.y * 100}%`,
                    width: `${selectedBox.w * 100}%`,
                    height: `${selectedBox.h * 100}%`,
                  }}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
