"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FileSearch } from "lucide-react";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SelectField, TextField } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentCategories } from "@/hooks/useDocumentsCategories";
import { getDocuments } from "@/lib/api";
import { formatNumber } from "@/lib/formatters";
import DocumentDetail from "./DocumentDetail";
import DocumentTable from "./DocumentTable";

const PAGE_SIZE = 20;
const SOURCE_TYPES = [
  { value: "", label: "All sources" },
  { value: "seed", label: "Seed corpus" },
  { value: "user", label: "Uploaded" },
  { value: "crawled", label: "Crawled" },
];

/** Browse the indexed corpus with server-side pagination; page/filters/selection live in the URL. */
export default function DocumentsPageClient() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const categories = useDocumentCategories();
  const [titleFilter, setTitleFilter] = useState("");

  const page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  const sourceType = SOURCE_TYPES.some((s) => s.value === params.get("source")) ? params.get("source") || "" : "";
  const category = params.get("category") || "";
  const selectedId = Number.parseInt(params.get("id") || "", 10) || null;

  const list = useAsync(getDocuments);
  const { run } = list;

  const update = useCallback(
    (changes) => {
      const sp = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(changes)) {
        if (value === null || value === "" || value === undefined) sp.delete(key);
        else sp.set(key, String(value));
      }
      const qs = sp.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname);
    },
    [params, pathname, router],
  );

  useEffect(() => {
    run({ page, pageSize: PAGE_SIZE, category: category || undefined, sourceType: sourceType || undefined });
  }, [page, category, sourceType, run]);

  const visible = useMemo(() => {
    const items = list.data?.items || [];
    const needle = titleFilter.trim().toLowerCase();
    return needle ? items.filter((d) => d.title.toLowerCase().includes(needle) || String(d.id) === needle) : items;
  }, [list.data, titleFilter]);

  return (
    <>
      <PageHeader
        title="Document explorer"
        description="Browse the indexed corpus: seed documents, uploaded files and crawled pages."
        breadcrumbs={[{ label: "Explore" }]}
      />

      <div className={`grid gap-6 ${selectedId ? "xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" : ""}`}>
        <div className="min-w-0 space-y-4">
          <Card className="p-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <SelectField label="Source type" value={sourceType} onChange={(e) => update({ source: e.target.value, page: null })}>
                {SOURCE_TYPES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Category" value={category} onChange={(e) => update({ category: e.target.value, page: null })}>
                <option value="">All categories</option>
                {category && !categories.includes(category) && <option value={category}>{category}</option>}
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </SelectField>
              <TextField
                label="Filter this page by title or ID"
                value={titleFilter}
                onChange={(e) => setTitleFilter(e.target.value)}
                placeholder="e.g. network or 42"
              />
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-mute-line px-4 py-2 text-sm text-mute" role="status">
              {list.data ? (
                <span>
                  <strong className="text-ink">{formatNumber(list.data.total)}</strong> documents
                  {titleFilter && ` · ${visible.length} shown on this page`}
                </span>
              ) : (
                <span>Loading documents…</span>
              )}
            </div>
            {list.error ? (
              <div className="p-4">
                <ErrorState error={list.error} onRetry={() => run({ page, pageSize: PAGE_SIZE, category: category || undefined, sourceType: sourceType || undefined })} />
              </div>
            ) : !list.data ? (
              <TableSkeleton rows={8} cols={6} />
            ) : list.data.items.length === 0 && list.data.total > 0 ? (
              <div className="p-4">
                <EmptyState icon={FileSearch} title={`Page ${page} does not exist`} description={`These ${formatNumber(list.data.total)} documents fit on ${list.data.total_pages} pages.`}>
                  <Button variant="primary" onClick={() => update({ page: list.data.total_pages })}>
                    Go to the last page
                  </Button>
                </EmptyState>
              </div>
            ) : list.data.items.length === 0 ? (
              <div className="p-4">
                <EmptyState icon={FileSearch} title="No documents found" description="No documents match these filters yet. Upload files or run the crawler to add some." />
              </div>
            ) : visible.length === 0 ? (
              <div className="p-4">
                <EmptyState title="No documents on this page match the filter" />
              </div>
            ) : (
              <div className={list.loading ? "opacity-60" : ""}>
                <DocumentTable documents={visible} selectedId={selectedId} onSelect={(id) => update({ id })} />
              </div>
            )}
            <div className="border-t border-mute-line p-3">
              {list.data?.items.length > 0 && (
                <Pagination page={page} totalPages={list.data.total_pages || 0} onChange={(p) => update({ page: p })} disabled={list.loading} />
              )}
            </div>
          </Card>
        </div>

        {selectedId && (
          <div className="min-w-0 xl:sticky xl:top-20 xl:self-start">
            <DocumentDetail key={selectedId} documentId={selectedId} onClose={() => update({ id: null })} />
          </div>
        )}
      </div>
    </>
  );
}
