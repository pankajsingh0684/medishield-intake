export function LoadingState() {
  return (
    <div role="status" className="panel py-12 text-center text-slate-600">
      Loading…
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="panel border-red-300 bg-red-50 py-8 text-center text-red-900"
    >
      {message}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="panel py-12 text-center text-slate-600">{message}</div>
  );
}
