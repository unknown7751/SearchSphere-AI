"use client";

import { useEffect, useState } from "react";
import { History } from "lucide-react";
import Badge from "@/components/ui/Badge";
import { Card, CardHeader } from "@/components/ui/Card";
import Pagination from "@/components/ui/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { getCrawlerHistory } from "@/lib/api";
import { crawlStatusTone, formatDate, truncate } from "@/lib/formatters";

const PAGE_SIZE = 10;

/** Past and current crawl jobs (GET /api/crawler/history). Selecting a row opens that job's details. */
export default function CrawlHistory({ selectedJobId, onSelect, refreshKey, onLoaded }) {
  const [page, setPage] = useState(1);
  const history = useAsync(getCrawlerHistory);
  const { run } = history;

  useEffect(() => {
    run({ page, pageSize: PAGE_SIZE }).then((res) => res && onLoaded?.(res));
    // onLoaded is intentionally not a dependency: it only seeds the initial selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, refreshKey, run]);

  const data = history.data;
  return (
    <Card aria-label="Crawl history">
      <CardHeader title="Crawl history" icon={History} description={data ? `${data.total} job${data.total === 1 ? "" : "s"}` : undefined} />
      {history.error ? (
        <div className="p-4">
          <ErrorState error={history.error} onRetry={() => run({ page, pageSize: PAGE_SIZE })} />
        </div>
      ) : !data ? (
        <TableSkeleton rows={3} cols={6} />
      ) : data.items.length === 0 ? (
        <div className="p-4">
          <EmptyState title="No crawl jobs yet" description="Start a crawl above; it will appear here." />
        </div>
      ) : (
        <>
          <Table caption="Crawl jobs">
            <thead>
              <tr>
                <Th>Job</Th>
                <Th>Seed URL</Th>
                <Th>Status</Th>
                <Th align="right">Crawled</Th>
                <Th align="right">Failed</Th>
                <Th>Started</Th>
                <Th>Completed</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((j) => {
                const selected = j.job_id === selectedJobId;
                return (
                  <tr key={j.job_id} className={selected ? "bg-teal-50" : "hover:bg-paper"}>
                    <Td mono>
                      <button
                        type="button"
                        onClick={() => onSelect(j.job_id)}
                        aria-current={selected ? "true" : undefined}
                        className="font-medium text-navy-700 hover:text-teal-700 hover:underline"
                        aria-label={`Open crawl job ${j.job_id}`}
                      >
                        #{j.job_id}
                      </button>
                    </Td>
                    <Td className="max-w-xs break-all font-mono text-xs">{truncate(j.seed_url, 60)}</Td>
                    <Td><Badge tone={crawlStatusTone(j.status)}>{j.status}</Badge></Td>
                    <Td align="right" mono>{j.pages_crawled}</Td>
                    <Td align="right" mono>{j.pages_failed}</Td>
                    <Td className="whitespace-nowrap text-ink-soft">{formatDate(j.started_at)}</Td>
                    <Td className="whitespace-nowrap text-ink-soft">{formatDate(j.completed_at)}</Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
          <div className="border-t border-mute-line p-3">
            <Pagination page={page} totalPages={Math.max(1, Math.ceil(data.total / data.page_size))} onChange={setPage} disabled={history.loading} />
          </div>
        </>
      )}
    </Card>
  );
}
