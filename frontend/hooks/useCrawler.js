"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getCrawlerStatus } from "@/lib/api";
import { POLL_INTERVAL_MS, TERMINAL_JOB_STATUSES } from "@/lib/constants";

/**
 * Poll one crawl job until it reaches a terminal state (completed / failed / cancelled), then stop.
 * Pass `jobId = null` to disable. `onUpdate` fires with each fresh job record.
 * Transient network failures are tolerated (up to 5 in a row) before the error is surfaced.
 */
export function useCrawlJob(jobId, { intervalMs = POLL_INTERVAL_MS } = {}) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const failures = useRef(0);

  const refresh = useCallback(async (signal) => {
    if (jobId == null) return null;
    try {
      const next = await getCrawlerStatus(jobId, { signal });
      failures.current = 0;
      setError(null);
      setJob(next);
      return next;
    } catch (err) {
      if (signal?.aborted) return null;
      failures.current += 1;
      if (failures.current >= 5 || err?.status === 404) setError(err);
      return null;
    }
  }, [jobId]);

  useEffect(() => {
    if (jobId == null) {
      return undefined;
    }
    const controller = new AbortController();
    let timer;
    let cancelled = false;
    failures.current = 0;

    const tick = async () => {
      const next = await refresh(controller.signal);
      if (cancelled) return;
      const done = next && TERMINAL_JOB_STATUSES.includes(next.status);
      if (done || failures.current >= 5) return;
      timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, intervalMs, refresh]);

  // Ignore a record left over from a previously selected job while the new one is loading.
  const current = jobId != null && job && job.job_id === jobId ? job : null;
  const finished = current ? TERMINAL_JOB_STATUSES.includes(current.status) : false;
  // Polling continues until a terminal status arrives or repeated failures surface an error.
  const polling = jobId != null && !finished && !error;
  return { job: current, error: jobId == null ? null : error, polling, finished, refresh };
}
