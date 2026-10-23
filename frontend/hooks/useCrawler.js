"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getCrawlerStatus } from "@/lib/api";
import { POLL_INTERVAL_MS, TERMINAL_JOB_STATUSES } from "@/lib/constants";

const MAX_CONSECUTIVE_FAILURES = 5;

/**
 * Poll one crawl job until it reaches a terminal state (completed / failed / cancelled), then stop.
 * Pass `jobId = null` to disable.
 *
 * - Transient failures are tolerated (up to 5 in a row) before the error is surfaced and polling stops.
 * - A 404 means the job does not exist, so polling stops immediately.
 * - `retry()` restarts polling after it stopped on an error; `refresh()` is a one-off read (e.g. after Cancel).
 * - The timer and the in-flight request are cancelled on unmount and whenever `jobId` changes.
 */
export function useCrawlJob(jobId, { intervalMs = POLL_INTERVAL_MS } = {}) {
  const [job, setJob] = useState(null);
  // The error remembers which job it belongs to, so switching jobs never shows a previous job's error.
  const [failure, setFailure] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const failures = useRef(0);

  const refresh = useCallback(
    async (signal) => {
      if (jobId == null) return null;
      try {
        const next = await getCrawlerStatus(jobId, { signal });
        failures.current = 0;
        setFailure(null);
        setJob(next);
        return next;
      } catch (err) {
        if (signal?.aborted) return null;
        failures.current = err?.status === 404 ? MAX_CONSECUTIVE_FAILURES : failures.current + 1;
        if (failures.current >= MAX_CONSECUTIVE_FAILURES) setFailure({ jobId, error: err });
        return null;
      }
    },
    [jobId],
  );

  useEffect(() => {
    if (jobId == null) return undefined;
    const controller = new AbortController();
    let timer;
    let cancelled = false;
    failures.current = 0;

    const tick = async () => {
      const next = await refresh(controller.signal);
      if (cancelled) return;
      const done = next && TERMINAL_JOB_STATUSES.includes(next.status);
      if (done || failures.current >= MAX_CONSECUTIVE_FAILURES) return;
      timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, intervalMs, refresh, attempt]);

  const retry = useCallback(() => {
    setFailure(null);
    setAttempt((n) => n + 1);
  }, []);

  // Ignore a record left over from a previously selected job while the new one is loading.
  const current = jobId != null && job && job.job_id === jobId ? job : null;
  const error = jobId != null && failure && failure.jobId === jobId ? failure.error : null;
  const finished = current ? TERMINAL_JOB_STATUSES.includes(current.status) : false;
  // Polling continues until a terminal status arrives or repeated failures surface an error.
  const polling = jobId != null && !finished && !error;
  return { job: current, error, polling, finished, refresh, retry };
}
