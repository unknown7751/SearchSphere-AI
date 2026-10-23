"use client";

import { useMemo, useState } from "react";
import { SearchX } from "lucide-react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Pagination from "@/components/ui/Pagination";
import { EmptyState, ErrorState, Notice, ResultsSkeleton } from "@/components/ui/States";
import { SEARCH_MODES } from "@/lib/constants";
import { filterResults } from "@/lib/searchModel";
import { formatMs } from "@/lib/formatters";
import ResultCard from "./ResultCard";
import ResultFilters from "./ResultFilters";
import { BooleanInsight, ExpansionInsight, QueryAnalysis, RocchioInsight, WildcardInsight } from "./SearchInsights";

/** Presents every state of a search: initial, loading, error, empty and results. */
export default function SearchResults({ query, mode, state, onPageChange, onRetry }) {
  const [filters, setFilters] = useState({ sourceType: null, category: null });
  // While a different query/mode is loading, the previous view must not be shown under the new query.
  const view = state.data?.request?.query === query && state.data.request.mode === mode ? state.data : null;
  const modeLabel = SEARCH_MODES.find((m) => m.value === mode)?.label || mode;

  const visible = useMemo(() => (view ? filterResults(view.results, filters) : []), [view, filters]);

  if (!query) {
    return (
      <EmptyState
        title="Enter a query to search the corpus"
        description="Try a phrase like “machine learning”, a Boolean expression like “network AND NOT firewall”, or a wildcard such as “mach*”."
      />
    );
  }
  if (state.status === "error") return <ErrorState error={state.error} onRetry={onRetry} />;
  if (!view) return <ResultsSkeleton />;

  const totalPages = Math.max(1, Math.ceil(view.total / view.pageSize));
  const loading = state.loading;
  const beyondLastPage = view.total > 0 && view.results.length === 0 && view.page > totalPages;

  return (
    <div className={`space-y-4 ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-mute" role="status">
        <span>
          Query <strong className="text-ink">“{query}”</strong>
        </span>
        <Badge tone="teal">{modeLabel}</Badge>
        <span>
          <strong className="text-ink">{view.total}</strong> {view.total === 1 ? "result" : "results"}
        </span>
        <span>{formatMs(view.tookMs)}</span>
      </div>

      <QueryAnalysis analysis={view.analysis} />
      {view.extras.expansion && <ExpansionInsight expansion={view.extras.expansion} />}
      {view.extras.rocchio && <RocchioInsight rocchio={view.extras.rocchio} />}
      {view.extras.boolean && <BooleanInsight data={view.extras.boolean} />}
      {view.extras.wildcard && <WildcardInsight data={view.extras.wildcard} />}

      {view.total === 0 ? (
        <EmptyState icon={SearchX} title="No documents matched your query." description={view.message !== "No documents matched your query." ? view.message : undefined} />
      ) : (
        <>
          <ResultFilters
            results={view.results}
            sourceType={filters.sourceType}
            category={filters.category}
            onChange={setFilters}
          />
          {view.extras.wildcard?.totalDocuments > view.total && (
            <Notice tone="warn">
              The backend lists at most {view.total} documents for a pattern; {view.extras.wildcard.totalDocuments} documents match in total.
            </Notice>
          )}
          {beyondLastPage ? (
            <EmptyState title={`Page ${view.page} does not exist`} description={`These ${view.total} results fit on ${totalPages} page${totalPages === 1 ? "" : "s"}.`}>
              <Button variant="primary" onClick={() => onPageChange(totalPages)}>
                Go to the last page
              </Button>
            </EmptyState>
          ) : visible.length === 0 ? (
            <EmptyState title="No results on this page match the filters" description="Clear the filters to see all retrieved results." />
          ) : (
            <ol className="space-y-3" aria-label="Search results">
              {visible.map((r) => (
                <li key={r.doc_id}>
                  <ResultCard result={r} />
                </li>
              ))}
            </ol>
          )}
          {!beyondLastPage && <Pagination page={view.page} totalPages={totalPages} onChange={onPageChange} disabled={loading} />}
        </>
      )}
    </div>
  );
}
