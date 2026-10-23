"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { SelectField } from "@/components/ui/Field";
import Pagination from "@/components/ui/Pagination";
import SafeLink from "@/components/ui/SafeLink";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { getCrawlerResults } from "@/lib/api";
import { crawlStatusTone, humanizeStatus, truncate } from "@/lib/formatters";

const STATUS_FILTERS = [
  "indexed",
  "updated",
  "unchanged",
  "duplicate_content",
  "blocked_by_robots",
  "blocked_by_security",
  "skipped",
  "failed",
];
const PAGE_SIZE = 25;

/**
 * Per-URL results of one crawl job. `refreshKey` changes while the job is running so the table follows
 * the crawl without its own timer; completed jobs are fetched once.
 */
export default function CrawlResults({ jobId, refreshKey }) {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const results = useAsync(getCrawlerResults);
  const { run } = results;

  useEffect(() => {
    run(jobId, { page, pageSize: PAGE_SIZE, status: status || undefined });
  }, [jobId, page, status, refreshKey, run]);

  const data = results.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 0;

  return (
    <Card aria-label="Crawl results">
      <CardHeader
        title="Crawl results"
        description={data ? `${data.total} URL${data.total === 1 ? "" : "s"} recorded` : undefined}
        actions={
          <SelectField
            label="Status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="w-48 [&_label]:sr-only"
          >
            <option value="">All statuses</option>
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {humanizeStatus(s)}
              </option>
            ))}
          </SelectField>
        }
      />
      {results.error ? (
        <div className="p-4">
          <ErrorState error={results.error} onRetry={() => run(jobId, { page, pageSize: PAGE_SIZE, status: status || undefined })} />
        </div>
      ) : !data ? (
        <TableSkeleton rows={5} cols={6} />
      ) : data.items.length === 0 ? (
        <div className="p-4">
          <EmptyState title="No results yet" description={status ? "No URLs have this status." : "The crawler has not recorded any URL for this job yet."} />
        </div>
      ) : (
        <>
          <Table caption="Crawled URLs">
            <thead>
              <tr>
                <Th>URL</Th>
                <Th>Status</Th>
                <Th align="right">Depth</Th>
                <Th align="right">HTTP</Th>
                <Th>Content type</Th>
                <Th align="right">Doc ID</Th>
                <Th>Indexed</Th>
                <Th>Error</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.url}>
                  <Td className="max-w-xs">
                    {r.title && <p className="font-medium">{truncate(r.title, 70)}</p>}
                    <SafeLink href={r.final_url || r.url} className="text-xs">
                      {truncate(r.url, 70)}
                    </SafeLink>
                  </Td>
                  <Td><Badge tone={crawlStatusTone(r.status)}>{humanizeStatus(r.status)}</Badge></Td>
                  <Td align="right" mono>{r.depth}</Td>
                  <Td align="right" mono>{r.http_status ?? "—"}</Td>
                  <Td className="whitespace-nowrap font-mono text-xs">{r.content_type ? truncate(r.content_type, 28) : "—"}</Td>
                  <Td align="right" mono>
                    {r.document_id ? (
                      <Link href={`/documents?id=${r.document_id}`} className="text-teal-700 hover:underline">
                        {r.document_id}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>{r.indexed ? <Badge tone="green">yes</Badge> : <Badge>no</Badge>}</Td>
                  <Td className="max-w-xs break-words text-xs text-ink-soft">{r.error || "—"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="border-t border-mute-line p-3">
            <Pagination page={page} totalPages={totalPages} onChange={setPage} disabled={results.loading} />
          </div>
        </>
      )}
    </Card>
  );
}
