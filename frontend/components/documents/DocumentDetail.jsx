"use client";

import { useEffect } from "react";
import { Search, X } from "lucide-react";
import Badge from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import KeyValue from "@/components/ui/KeyValue";
import SafeLink from "@/components/ui/SafeLink";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useAsync } from "@/hooks/useAsync";
import { getDocument } from "@/lib/api";
import { formatDate, formatNumber, sourceTypeMeta } from "@/lib/formatters";
import { searchHref } from "@/lib/searchUrl";

function metadataItems(metadata) {
  if (!metadata || typeof metadata !== "object") return [];
  return Object.entries(metadata).map(([key, value]) => ({
    label: key.replaceAll("_", " "),
    // Untrusted values are rendered as text only; nested values are JSON-encoded.
    value: typeof value === "object" && value !== null ? JSON.stringify(value) : String(value),
  }));
}

/** Full document view (GET /api/documents/{id}). All content is rendered as text, never as HTML. */
export default function DocumentDetail({ documentId, onClose }) {
  const { data: doc, loading, error, run } = useAsync(getDocument);

  useEffect(() => {
    run(documentId);
  }, [documentId, run]);

  return (
    <Card aria-label="Document detail">
      <CardHeader
        title="Document detail"
        actions={
          onClose && (
            <button type="button" onClick={onClose} className="rounded p-1 text-mute hover:bg-paper-dark" aria-label="Close document detail">
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          )
        }
      />
      <CardBody>
        {error ? (
          <ErrorState error={error} onRetry={() => run(documentId)} />
        ) : !doc || loading ? (
          <div role="status" aria-label="Loading document" className="space-y-3">
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <DocumentBody doc={doc} />
        )}
      </CardBody>
    </Card>
  );
}

function DocumentBody({ doc }) {
  const source = sourceTypeMeta(doc.source_type);
  const meta = metadataItems(doc.metadata);
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-navy-800">{doc.title}</h3>
        <div className="mt-1 flex flex-wrap gap-1.5">
          <Badge tone={source.tone}>{source.label}</Badge>
          <Badge>{doc.category}</Badge>
          {doc.file_type && <Badge tone="navy">{doc.file_type.toUpperCase()}</Badge>}
          <Badge tone={doc.indexed ? "green" : "amber"}>{doc.indexed ? "Indexed" : "Not indexed"}</Badge>
        </div>
      </div>

      <KeyValue
        items={[
          { label: "Document ID", value: <span className="font-mono">{doc.id}</span> },
          { label: "Source type", value: <span className="font-mono">{doc.source_type}</span> },
          { label: "Source name", value: doc.source_name },
          { label: "Source URL", value: doc.source_url ? <SafeLink href={doc.source_url} /> : null },
          { label: "Created", value: formatDate(doc.ingested_at) },
          { label: "Updated", value: doc.updated_at ? formatDate(doc.updated_at) : null },
          { label: "Published", value: doc.published_at ? formatDate(doc.published_at) : null },
          { label: "Words", value: formatNumber(doc.word_count) },
          { label: "External ID", value: doc.external_id ? <span className="font-mono">{doc.external_id}</span> : null },
        ]}
      />

      {meta.length > 0 && (
        <details className="rounded border border-mute-line">
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink-soft">Ingestion / crawl metadata</summary>
          <div className="border-t border-mute-line p-3">
            <KeyValue items={meta} />
          </div>
        </details>
      )}

      <div>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-mute">Content</h4>
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded border border-mute-line bg-paper p-3 font-sans text-sm leading-relaxed text-ink">
          {doc.text}
        </pre>
      </div>

      <div className="flex flex-wrap gap-2">
        <ButtonLink href={searchHref(doc.title, "ranked")} size="sm" variant="primary">
          <Search className="h-4 w-4" aria-hidden="true" />
          Search this document
        </ButtonLink>
        <ButtonLink href="/workbench" size="sm">
          Open in workbench
        </ButtonLink>
      </div>
    </div>
  );
}
