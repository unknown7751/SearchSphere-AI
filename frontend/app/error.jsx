"use client";

import { ErrorState } from "@/components/ui/States";

/** Last-resort boundary: a rendering failure shows a friendly message, never a stack trace. */
export default function GlobalError({ reset }) {
  return (
    <div className="mx-auto max-w-xl py-10">
      <ErrorState error={new Error("render")} onRetry={reset} />
    </div>
  );
}
