"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import Badge from "@/components/ui/Badge";
import SafeLink from "@/components/ui/SafeLink";
import { formatScore, sourceTypeMeta } from "@/lib/formatters";
import ExplanationPanel from "./ExplanationPanel";

/**
 * One search hit. `result.explanation` (when present) powers the "Why this result?" disclosure.
 * `as` sets the title's heading level (h2 on the results page, where the page title is the h1).
 */
export default function ResultCard({ result, as: Heading = "h2" }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const source = sourceTypeMeta(result.source_type);
  const hasScore = typeof result.score === "number";

  return (
    <article className="rounded-md border border-mute-line bg-white p-4">
      <div className="flex items-start gap-3">
        {result.rank != null && (
          <span className="mt-0.5 w-6 shrink-0 text-right font-mono text-sm text-mute">
            <span className="sr-only">Rank </span>
            {result.rank}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <Heading className="text-base font-semibold text-navy-700 [overflow-wrap:anywhere]">
            <Link href={`/documents?id=${result.doc_id}`} className="hover:text-teal-700 hover:underline">
              {result.title}
            </Link>
          </Heading>

          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <Badge tone={source.tone}>{source.label}</Badge>
            {result.category && <Badge>{result.category}</Badge>}
            <span className="font-mono text-mute">ID {result.doc_id}</span>
            {hasScore && (
              <span className="font-mono text-mute">
                score <strong className="text-ink">{formatScore(result.score)}</strong>
              </span>
            )}
          </div>

          {result.snippet && <p className="mt-2 text-sm leading-relaxed text-ink-soft [overflow-wrap:anywhere]">{result.snippet}</p>}

          {result.source_url && (
            <p className="mt-2 text-xs">
              <span className="mr-1 text-mute">Source:</span>
              <SafeLink href={result.source_url} />
            </p>
          )}

          {result.explanation && (
            <div className="mt-3">
              <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setOpen((v) => !v)}
                className="inline-flex items-center gap-1 text-sm font-medium text-teal-700 hover:underline"
              >
                {open ? <ChevronDown className="h-4 w-4" aria-hidden="true" /> : <ChevronRight className="h-4 w-4" aria-hidden="true" />}
                Why this result?
              </button>
              {open && (
                <div id={panelId} className="mt-2">
                  <ExplanationPanel explanation={result.explanation} score={result.score} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
