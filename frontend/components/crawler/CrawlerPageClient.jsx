"use client";

import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { ButtonLink } from "@/components/ui/Button";
import PageHeader from "@/components/ui/PageHeader";
import { Notice } from "@/components/ui/States";
import { useCrawlJob } from "@/hooks/useCrawler";
import CrawlForm, { SafetyPanel } from "./CrawlForm";
import CrawlHistory from "./CrawlHistory";
import CrawlResults from "./CrawlResults";
import JobStatus from "./JobStatus";

/** Crawler control panel: start -> monitor (polling until terminal) -> results -> history. */
export default function CrawlerPageClient() {
  const [jobId, setJobId] = useState(null);
  const [historyKey, setHistoryKey] = useState(0);
  const [initialised, setInitialised] = useState(false);
  const [hasActiveJob, setHasActiveJob] = useState(false);

  const { job, error, polling, finished, refresh } = useCrawlJob(jobId);

  const handleStarted = (created) => {
    setJobId(created.job_id);
    setHasActiveJob(true);
    setHistoryKey((k) => k + 1);
  };

  // After a reload during a crawl, re-attach to the active job found in the history.
  const handleHistoryLoaded = useCallback(
    (res) => {
      const active = res.items.find((j) => j.status === "queued" || j.status === "running");
      setHasActiveJob(Boolean(active));
      if (!initialised) {
        setInitialised(true);
        if (active) setJobId(active.job_id);
      }
    },
    [initialised],
  );

  // The history re-reads once more when the watched job reaches a terminal state (the key changes then).
  const finishedKey = finished && job ? `${job.job_id}:${job.status}` : "";

  const activeNow = job ? !finished : hasActiveJob && jobId == null;
  const resultsKey = job ? `${job.status}:${job.pages_crawled}:${job.pages_failed}:${job.pages_blocked}:${job.pages_skipped}` : "none";

  return (
    <>
      <PageHeader
        title="Web crawler"
        description="Crawl a public website within strict, server-enforced safety limits and add the pages to the search index."
        breadcrumbs={[{ label: "Crawler" }]}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <CrawlForm onStarted={handleStarted} disabled={activeNow} />
        <SafetyPanel />
      </div>

      {jobId != null && (
        <div className="mt-6 space-y-6">
          <JobStatus job={job} error={error} polling={polling} onRetry={refresh} onChanged={refresh} />
          {finished && job.status === "completed" && job.pages_crawled > 0 && (
            <Notice tone="teal" className="flex flex-wrap items-center justify-between gap-2">
              <span>Crawl finished: {job.pages_crawled} page(s) fetched. Pages with status “indexed” or “updated” are searchable now.</span>
              <ButtonLink href="/documents?source=crawled" size="sm" variant="primary">
                <Search className="h-4 w-4" aria-hidden="true" />
                Browse crawled documents
              </ButtonLink>
            </Notice>
          )}
          <CrawlResults jobId={jobId} refreshKey={resultsKey} />
        </div>
      )}

      <div className="mt-6">
        <CrawlHistory selectedJobId={jobId} onSelect={setJobId} refreshKey={`${historyKey}|${finishedKey}`} onLoaded={handleHistoryLoaded} />
      </div>
    </>
  );
}
