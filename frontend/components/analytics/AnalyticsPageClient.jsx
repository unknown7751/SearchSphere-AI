"use client";

import { useEffect } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import MetricCard from "@/components/ui/MetricCard";
import PageHeader from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { getAnalytics } from "@/lib/api";
import { apByQuery, categoryCounts, crawlJobSeries, jobStatusCounts, sourceTypeCounts, sum, wordCountHistogram } from "@/lib/analytics";
import { formatNumber, formatPercent, formatScore } from "@/lib/formatters";
import { HorizontalBars, VerticalBars } from "./charts";

const MODE_LABELS = { tfidf: "TF-IDF", expanded: "TF-IDF + expansion", rocchio: "Rocchio (pseudo)" };

/** Collapsible, accessible table equivalent of a chart. */
function TableView({ caption, columns, rows }) {
  return (
    <details className="mt-3 rounded border border-mute-line">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink-soft">Table view</summary>
      <Table caption={caption}>
        <thead>
          <tr>
            {columns.map((c, i) => (
              <Th key={c.key} align={i === 0 ? "left" : "right"}>
                {c.label}
              </Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              {columns.map((c, i) => (
                <Td key={c.key} align={i === 0 ? "left" : "right"} mono={i !== 0}>
                  {c.format ? c.format(r[c.key]) : r[c.key]}
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </Table>
    </details>
  );
}

function Section({ title, description, children }) {
  return (
    <section aria-label={title} className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-navy-800">{title}</h2>
        {description && <p className="text-sm text-mute">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function PartError({ result, label }) {
  return <ErrorState error={result.error} className="text-left" key={label} />;
}

function CorpusSection({ corpus }) {
  if (!corpus.ok) return <PartError result={corpus} label="corpus" />;
  const { items, total, truncated } = corpus.value;
  if (items.length === 0) return <EmptyState title="The corpus is empty" description="Seed the backend or upload documents to see corpus statistics." />;
  const categories = categoryCounts(items);
  const sources = sourceTypeCounts(items);
  const lengths = wordCountHistogram(items);
  return (
    <div className="space-y-4">
      {truncated && (
        <p className="text-sm text-amber-800">
          Charts use the first {formatNumber(items.length)} of {formatNumber(total)} documents (bounded to keep the page fast).
        </p>
      )}
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Documents per category" />
          <CardBody>
            <HorizontalBars data={categories} seriesName="Documents" />
            <TableView caption="Documents per category" columns={[{ key: "name", label: "Category" }, { key: "value", label: "Documents" }]} rows={categories} />
          </CardBody>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Documents by source" description="Where each indexed document came from." />
            <CardBody>
              <HorizontalBars data={sources} seriesName="Documents" height={Math.max(120, sources.length * 36 + 24)} />
              <TableView caption="Documents by source type" columns={[{ key: "name", label: "Source" }, { key: "value", label: "Documents" }]} rows={sources} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Document length" description="Number of documents by word count (length normalisation matters for cosine)." />
            <CardBody>
              <VerticalBars data={lengths} series={[{ key: "value", name: "Documents" }]} height={200} />
              <TableView caption="Document length distribution" columns={[{ key: "name", label: "Words" }, { key: "value", label: "Documents" }]} rows={lengths} />
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

function CrawlSection({ crawl }) {
  if (!crawl.ok) return <PartError result={crawl} label="crawl" />;
  const jobs = crawl.value.items;
  if (jobs.length === 0) return <EmptyState icon={BarChart3} title="No historical data available yet." description="Run a crawl on the Crawler page and its outcomes will be charted here." />;
  const series = crawlJobSeries(jobs);
  const statuses = jobStatusCounts(jobs);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <MetricCard label="Crawl jobs" value={formatNumber(crawl.value.total)} />
        <MetricCard label="Pages crawled" value={formatNumber(sum(jobs, "pages_crawled"))} />
        <MetricCard label="Failed" value={formatNumber(sum(jobs, "pages_failed"))} />
        <MetricCard label="Blocked" value={formatNumber(sum(jobs, "pages_blocked"))} hint="robots.txt or security" />
        <MetricCard label="Skipped" value={formatNumber(sum(jobs, "pages_skipped"))} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader title="Page outcomes per job" description={`Most recent ${series.length} job(s), oldest first.`} />
          <CardBody>
            <VerticalBars
              data={series}
              series={[
                { key: "crawled", name: "Crawled" },
                { key: "blocked", name: "Blocked" },
                { key: "failed", name: "Failed" },
              ]}
            />
            <TableView
              caption="Page outcomes per crawl job"
              columns={[{ key: "name", label: "Job" }, { key: "crawled", label: "Crawled" }, { key: "blocked", label: "Blocked" }, { key: "failed", label: "Failed" }]}
              rows={series}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Jobs by status" />
          <CardBody>
            <HorizontalBars data={statuses} seriesName="Jobs" height={Math.max(120, statuses.length * 36 + 24)} />
            <TableView caption="Jobs by status" columns={[{ key: "name", label: "Status" }, { key: "value", label: "Jobs" }]} rows={statuses} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function EvaluationSection({ evaluation }) {
  const results = Object.entries(evaluation);
  const okResults = results.filter(([, r]) => r.ok);
  if (okResults.length === 0) return <PartError result={results[0]?.[1] || { error: new Error("none") }} label="evaluation" />;
  const k = okResults[0][1].value.top_k;
  const summary = okResults.map(([mode, r]) => ({
    name: MODE_LABELS[mode] || mode,
    map: r.value.mean_average_precision,
    p: r.value.mean_precision_at_k,
    r: r.value.mean_recall_at_k,
  }));
  const { modes, rows } = apByQuery(evaluation);
  const base = okResults[0][1].value;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="MAP (TF-IDF)" value={formatScore(evaluation.tfidf?.ok ? evaluation.tfidf.value.mean_average_precision : null)} hint={`${base.query_count} judged queries`} />
        <MetricCard label={`Mean P@${k}`} value={formatScore(evaluation.tfidf?.ok ? evaluation.tfidf.value.mean_precision_at_k : null)} />
        <MetricCard label={`Mean R@${k}`} value={formatScore(evaluation.tfidf?.ok ? evaluation.tfidf.value.mean_recall_at_k : null)} />
        <MetricCard label="Best MAP mode" value={<span className="text-lg">{[...summary].sort((a, b) => b.map - a.map)[0].name}</span>} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Retrieval modes compared" description={`Mean metrics over the stored evaluation queries, cut-off K = ${k}.`} />
          <CardBody>
            <VerticalBars
              data={summary}
              series={[
                { key: "map", name: "MAP" },
                { key: "p", name: `Mean P@${k}` },
                { key: "r", name: `Mean R@${k}` },
              ]}
              valueFormatter={(v) => (typeof v === "number" ? v.toFixed(2) : v)}
              domain={[0, 1]}
              labelValues
            />
            <TableView
              caption="Mean metrics per retrieval mode"
              columns={[
                { key: "name", label: "Mode" },
                { key: "map", label: "MAP", format: formatScore },
                { key: "p", label: `P@${k}`, format: formatScore },
                { key: "r", label: `R@${k}`, format: formatScore },
              ]}
              rows={summary}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Average precision per query" description="One AP value per judged query and mode." />
          <CardBody>
            <VerticalBars
              data={rows}
              series={modes.map((m) => ({ key: m, name: MODE_LABELS[m] || m }))}
              valueFormatter={(v) => (typeof v === "number" ? v.toFixed(2) : v)}
              domain={[0, 1]}
              xAngle={-30}
              height={300}
            />
            <TableView
              caption="Average precision per query and mode"
              columns={[{ key: "name", label: "Query" }, ...modes.map((m) => ({ key: m, label: MODE_LABELS[m] || m, format: formatScore }))]}
              rows={rows}
            />
          </CardBody>
        </Card>
      </div>
      {results.some(([, r]) => !r.ok) && <p className="text-sm text-amber-800">Some retrieval modes could not be evaluated and are omitted.</p>}
    </div>
  );
}

export default function AnalyticsPageClient() {
  const { data, error, loading, run } = useAsync(getAnalytics);

  useEffect(() => {
    run();
  }, [run]);

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Statistics computed from the live backend: the corpus, the crawler and retrieval evaluation. Nothing here is sample data."
        breadcrumbs={[{ label: "Analytics" }]}
        actions={
          <Button onClick={() => run()} loading={loading}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
        }
      />

      {error && <ErrorState error={error} onRetry={() => run()} />}
      {!data && !error && (
        <div role="status" aria-label="Loading analytics" className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      )}

      {data && (
        <div className="space-y-10">
          <Section title="Corpus">
            {data.health.ok && (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <MetricCard label="Documents" value={formatNumber(data.health.value.documents)} />
                <MetricCard label="Indexed" value={formatNumber(data.health.value.indexed_documents)} hint={data.health.value.documents ? `${formatPercent(data.health.value.indexed_documents / data.health.value.documents)} of corpus` : undefined} />
                <MetricCard label="Vocabulary" value={formatNumber(data.health.value.vocabulary_size)} hint="distinct index terms" />
                <MetricCard label="Backend" value={<span className="text-lg">v{data.health.value.version}</span>} />
              </div>
            )}
            {!data.health.ok && <PartError result={data.health} label="health" />}
            <CorpusSection corpus={data.corpus} />
          </Section>

          <Section title="Search activity" description="Query volume and latency over time.">
            <EmptyState title="No historical data available yet." description="The backend does not record search history, so there are no query counts or latency trends to chart. Live latency is shown with each search." />
          </Section>

          <Section title="Crawling" description="Outcomes of web-crawl jobs.">
            <CrawlSection crawl={data.crawl} />
          </Section>

          <Section title="Retrieval evaluation" description="Evaluated live on the stored judged queries using the backend metric implementation.">
            <EvaluationSection evaluation={data.evaluation} />
          </Section>
        </div>
      )}
    </>
  );
}
