"use client";

import { useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import Flow, { TokenList } from "@/components/ui/Flow";
import { ErrorState, Notice } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { tolerantSearch } from "@/lib/api";
import { WILDCARD_EXAMPLES } from "@/lib/constants";
import { DocLink } from "./shared";

export default function WildcardPanel() {
  const [pattern, setPattern] = useState(WILDCARD_EXAMPLES[0]);
  const { data, error, loading, run } = useAsync(tolerantSearch);

  const go = (value) => {
    if (value.trim()) run({ pattern: value.trim() });
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Prefix and wildcard lookup" description="A single word where * matches zero or more characters. Matching runs over the surface dictionary, then maps to index terms." />
        <CardBody>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              go(pattern);
            }}
            className="space-y-3"
          >
            <TextField label="Pattern" value={pattern} onChange={(e) => setPattern(e.target.value)} mono maxLength={100} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" variant="primary" loading={loading} disabled={!pattern.trim()}>
                Expand pattern
              </Button>
              <span className="text-xs text-mute">Examples:</span>
              {WILDCARD_EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => {
                    setPattern(ex);
                    go(ex);
                  }}
                  className="rounded border border-mute-line bg-white px-2 py-0.5 font-mono text-xs hover:border-teal-600"
                >
                  {ex}
                </button>
              ))}
            </div>
          </form>
        </CardBody>
      </Card>

      {error && <ErrorState error={error} onRetry={() => go(pattern)} />}

      {data && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <Card>
            <CardHeader title="Expansion" />
            <CardBody className="space-y-3">
              <Flow
                steps={[
                  { label: "Input pattern", value: data.pattern, note: data.kind },
                  { label: "Lookup strategy", value: data.strategy },
                  {
                    label: "Expanded terms",
                    value: <TokenList tokens={data.matched_terms.map((m) => m.term)} tone="teal" emptyLabel="no dictionary term matches" />,
                    note: `${data.matched_term_count} of ${data.total_matches}`,
                  },
                  { label: "Matching documents", value: `${data.total_documents} document(s)` },
                ]}
              />
              {data.message && <Notice tone={data.total_matches === 0 ? "warn" : "info"}>{data.message}</Notice>}
            </CardBody>
          </Card>

          <div className="min-w-0 space-y-6">
            {data.matched_terms.length > 0 && (
              <Card>
                <CardHeader title="Matching dictionary terms" actions={data.truncated ? <Badge tone="amber">truncated</Badge> : null} />
                <Table caption="Dictionary terms matching the pattern">
                  <thead>
                    <tr>
                      <Th>Term</Th>
                      <Th>Index term</Th>
                      <Th align="right">Documents</Th>
                      <Th>Document IDs</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.matched_terms.map((m) => (
                      <tr key={m.term}>
                        <Td mono>{m.term}</Td>
                        <Td mono>{m.index_term}</Td>
                        <Td align="right" mono>{m.document_count}</Td>
                        <Td className="max-w-xs font-mono text-xs text-mute">{m.doc_ids.slice(0, 12).join(", ")}{m.doc_ids.length > 12 ? "…" : ""}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Card>
            )}
            {data.documents.length > 0 && (
              <Card>
                <CardHeader title="Matching documents" description={data.total_documents > data.documents.length ? `First ${data.documents.length} of ${data.total_documents}` : undefined} />
                <CardBody>
                  <ul className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                    {data.documents.map((d) => (
                      <li key={d.doc_id} className="truncate">
                        <span className="mr-2 font-mono text-xs text-mute">#{d.doc_id}</span>
                        <DocLink id={d.doc_id} title={d.title} />
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
