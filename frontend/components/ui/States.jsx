import { AlertTriangle, Inbox, Loader2, RefreshCw } from "lucide-react";
import { describeError } from "@/lib/api";
import Button from "./Button";

export function Spinner({ label = "Loading", className = "" }) {
  return (
    <span role="status" className={`inline-flex items-center gap-2 text-sm text-mute ${className}`}>
      <Loader2 className="h-4 w-4 animate-spin text-teal-600" aria-hidden="true" />
      {label}…
    </span>
  );
}

export function Skeleton({ className = "" }) {
  return <div className={`animate-pulse rounded bg-paper-dark ${className}`} aria-hidden="true" />;
}

export function ResultsSkeleton({ rows = 4 }) {
  return (
    <div role="status" aria-label="Loading results" className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="rounded-md border border-mute-line bg-white p-4">
          <Skeleton className="h-5 w-2/5" />
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-4/5" />
        </div>
      ))}
      <span className="sr-only">Loading results…</span>
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 5 }) {
  return (
    <div role="status" aria-label="Loading table" className="space-y-2 p-4">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} className="h-4" />
          ))}
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}

/** Human-readable error with an optional retry button. Accepts an ApiError (or anything thrown). */
export function ErrorState({ error, onRetry, className = "" }) {
  const { title, message, retryable } = describeError(error);
  return (
    <div role="alert" className={`rounded-md border border-red-200 bg-red-50 p-4 ${className}`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-700" aria-hidden="true" />
        <div className="min-w-0">
          <p className="font-medium text-red-900">{title}</p>
          <p className="mt-0.5 break-words text-sm text-red-800">{message}</p>
          {onRetry && retryable && (
            <Button size="sm" variant="secondary" className="mt-3" onClick={onRetry}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Try again
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({ title, description, icon: Icon = Inbox, children, className = "" }) {
  return (
    <div className={`rounded-md border border-dashed border-mute-line bg-white px-6 py-10 text-center ${className}`}>
      <Icon className="mx-auto h-8 w-8 text-mute-light" aria-hidden="true" />
      <p className="mt-3 font-medium text-ink">{title}</p>
      {description && <p className="mx-auto mt-1 max-w-xl text-sm text-mute">{description}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}

const NOTICE_TONES = {
  info: "border-navy-200 bg-navy-50 text-navy-800",
  teal: "border-teal-200 bg-teal-50 text-teal-800",
  warn: "border-amber-200 bg-amber-50 text-amber-900",
};

export function Notice({ tone = "info", className = "", children }) {
  return <div className={`rounded border px-3 py-2 text-sm ${NOTICE_TONES[tone]} ${className}`}>{children}</div>;
}
