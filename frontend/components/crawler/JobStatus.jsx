"use client";

import { useState } from "react";
import { Ban } from "lucide-react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import KeyValue from "@/components/ui/KeyValue";
import MetricCard from "@/components/ui/MetricCard";
import SafeLink from "@/components/ui/SafeLink";
import { ErrorState, Skeleton, Spinner } from "@/components/ui/States";
import { cancelCrawler } from "@/lib/api";
import { TERMINAL_JOB_STATUSES } from "@/lib/constants";
import { crawlStatusTone, formatDate, formatPercent, humanizeStatus } from "@/lib/formatters";

const LIFECYCLE = ["queued", "running", "completed"];

function Lifecycle({ status }) {
  const terminalOther = status === "failed" || status === "cancelled";
  const current = terminalOther ? 2 : LIFECYCLE.indexOf(status);
  const labels = terminalOther ? ["queued", "running", status] : LIFECYCLE;
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm" aria-label="Job lifecycle">
      {labels.map((label, i) => (
        <li key={label} className="flex items-center gap-2">
          <Badge tone={i === current ? crawlStatusTone(status) : i < current ? "green" : "neutral"}>{label}</Badge>
          {i < labels.length - 1 && <span className="text-mute-light" aria-hidden="true">→</span>}
        </li>
      ))}
    </ol>
  );
}

/** Live view of one crawl job (data comes from polling GET /api/crawler/{id}). */
export default function JobStatus({ job, error, polling, onRetry, onChanged }) {
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState(null);

  if (error && !job) return <ErrorState error={error} onRetry={onRetry} />;
  if (!job) {
    return (
      <Card aria-label="Crawl job status">
        <CardBody className="space-y-3" role="status">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-16 w-full" />
        </CardBody>
      </Card>
    );
  }

  const finished = TERMINAL_JOB_STATUSES.includes(job.status);
  const cancel = async () => {
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelCrawler(job.job_id);
      onChanged?.();
    } catch (err) {
      setCancelError(err);
    } finally {
      setCancelling(false);
    }
  };

  return (
    <Card aria-label="Crawl job status">
      <CardHeader
        title={`Crawl job #${job.job_id}`}
        description={<SafeLink href={job.seed_url} />}
        actions={
          <>
            {polling && !finished && <Spinner label="Live" />}
            {!finished && (
              <Button size="sm" variant="danger" onClick={cancel} loading={cancelling} disabled={job.cancel_requested}>
                <Ban className="h-4 w-4" aria-hidden="true" />
                {job.cancel_requested ? "Cancelling…" : "Cancel"}
              </Button>
            )}
          </>
        }
      />
      <CardBody className="space-y-4">
        <Lifecycle status={job.status} />

        <div>
          <div
            className="h-2 overflow-hidden rounded bg-paper-dark"
            role="progressbar"
            aria-label="Crawl progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round((job.progress || 0) * 100)}
          >
            <div className={`h-full transition-all ${job.status === "failed" ? "bg-red-600" : "bg-teal-600"}`} style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} />
          </div>
          <p className="mt-1 text-xs text-mute">{formatPercent(job.progress)} of discovered URLs processed</p>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <MetricCard label="Discovered" value={job.pages_discovered} />
          <MetricCard label="Crawled" value={job.pages_crawled} />
          <MetricCard label="Failed" value={job.pages_failed} />
          <MetricCard label="Blocked" value={job.pages_blocked} />
          <MetricCard label="Skipped" value={job.pages_skipped} />
        </div>

        <KeyValue
          items={[
            { label: "Status", value: <Badge tone={crawlStatusTone(job.status)}>{job.status}</Badge> },
            { label: "Limits", value: `${job.max_pages} pages · depth ${job.max_depth} · ${job.timeout_seconds}s timeout` },
            { label: "Created", value: formatDate(job.created_at) },
            { label: "Started", value: job.started_at ? formatDate(job.started_at) : null },
            { label: "Completed", value: job.completed_at ? formatDate(job.completed_at) : null },
            { label: "Stop reason", value: job.stop_reason ? humanizeStatus(job.stop_reason) : null },
            { label: "Job error", value: job.error },
          ]}
        />

        {cancelError && <ErrorState error={cancelError} />}
        {error && <ErrorState error={error} onRetry={onRetry} />}

        {job.recent_errors?.length > 0 && (
          <details className="rounded border border-mute-line">
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink-soft">
              Recent problems ({job.error_count})
            </summary>
            <ul className="divide-y divide-mute-line border-t border-mute-line text-sm">
              {job.recent_errors.map((e, i) => (
                <li key={`${e.url}-${i}`} className="px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={crawlStatusTone(e.status)}>{humanizeStatus(e.status)}</Badge>
                    {e.http_status && <span className="font-mono text-xs text-mute">HTTP {e.http_status}</span>}
                  </div>
                  <p className="mt-1 break-all font-mono text-xs text-mute">{e.url}</p>
                  <p className="mt-0.5 break-words text-ink-soft">{e.error}</p>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardBody>
    </Card>
  );
}
