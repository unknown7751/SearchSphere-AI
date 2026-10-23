import Link from "next/link";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import Badge from "@/components/ui/Badge";
import { Table, Td, Th } from "@/components/ui/Table";
import { formatScore } from "@/lib/formatters";

export function DocLink({ id, title }) {
  return (
    <Link href={`/documents?id=${id}`} className="text-teal-700 hover:underline">
      {title || `Document ${id}`}
    </Link>
  );
}

/** Renders `{term: weight}` as a compact table, strongest components first. */
export function VectorTable({ vector, caption, limit = 12 }) {
  const entries = Object.entries(vector || {}).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]) || a[0].localeCompare(b[0]));
  if (entries.length === 0) return <p className="text-sm text-mute">Empty vector.</p>;
  return (
    <Table caption={caption}>
      <thead>
        <tr>
          <Th>Term (stem)</Th>
          <Th align="right">Weight</Th>
        </tr>
      </thead>
      <tbody>
        {entries.slice(0, limit).map(([term, weight]) => (
          <tr key={term}>
            <Td mono>{term}</Td>
            <Td align="right" mono>{formatScore(weight)}</Td>
          </tr>
        ))}
      </tbody>
      {entries.length > limit && (
        <tfoot>
          <tr>
            <Td colSpan={2} className="text-xs text-mute">
              Showing the {limit} largest of {entries.length} components.
            </Td>
          </tr>
        </tfoot>
      )}
    </Table>
  );
}

/** "+3" / "−2" / "–" badge for backend-computed rank movement (positive = moved up). */
export function RankChange({ change }) {
  if (change === null || change === undefined) return <Badge tone="amber">new</Badge>;
  if (change > 0)
    return (
      <span className="inline-flex items-center gap-0.5 font-mono text-xs text-green-700">
        <ArrowUp className="h-3 w-3" aria-hidden="true" />
        {change}
        <span className="sr-only"> places up</span>
      </span>
    );
  if (change < 0)
    return (
      <span className="inline-flex items-center gap-0.5 font-mono text-xs text-red-700">
        <ArrowDown className="h-3 w-3" aria-hidden="true" />
        {Math.abs(change)}
        <span className="sr-only"> places down</span>
      </span>
    );
  return (
    <span className="inline-flex items-center text-mute">
      <Minus className="h-3 w-3" aria-hidden="true" />
      <span className="sr-only">unchanged</span>
    </span>
  );
}

/** Backend ranking rows ({rank, doc_id, title, score, baseline_rank?, rank_change?}). */
export function RankingTable({ rows, caption, showChange = false }) {
  return (
    <Table caption={caption}>
      <thead>
        <tr>
          <Th align="right">Rank</Th>
          <Th>Document</Th>
          <Th align="right">Score</Th>
          {showChange && <Th align="right">Was</Th>}
          {showChange && <Th>Change</Th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.doc_id}>
            <Td align="right" mono>{r.rank}</Td>
            <Td>
              <span className="mr-2 font-mono text-xs text-mute">#{r.doc_id}</span>
              <DocLink id={r.doc_id} title={r.title} />
            </Td>
            <Td align="right" mono>{formatScore(r.score)}</Td>
            {showChange && <Td align="right" mono>{r.baseline_rank ?? "—"}</Td>}
            {showChange && <Td><RankChange change={r.rank_change} /></Td>}
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export function SectionTitle({ children }) {
  return <h3 className="mb-2 text-sm font-semibold text-navy-700">{children}</h3>;
}
