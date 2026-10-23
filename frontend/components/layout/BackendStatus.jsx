"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import { formatNumber } from "@/lib/formatters";

/** Small header indicator backed by GET /api/health (checked once on load and every 60 s). */
export default function BackendStatus() {
  const [state, setState] = useState({ status: "checking", health: null });

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const check = () =>
      getHealth({ signal: controller.signal, timeoutMs: 8000 }).then(
        (health) => !cancelled && setState({ status: "online", health }),
        () => !cancelled && !controller.signal.aborted && setState({ status: "offline", health: null }),
      );
    check();
    const id = setInterval(check, 60000);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(id);
    };
  }, []);

  const dot = state.status === "online" ? "bg-emerald-400" : state.status === "offline" ? "bg-red-400" : "bg-amber-300";
  const text =
    state.status === "online"
      ? `API online · ${formatNumber(state.health?.indexed_documents)} docs indexed`
      : state.status === "offline"
        ? "API offline"
        : "Checking API…";

  return (
    <span className="flex items-center gap-2 text-xs text-navy-100" role="status">
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      <span className="hidden sm:inline">{text}</span>
      <span className="sr-only sm:hidden">{text}</span>
    </span>
  );
}
