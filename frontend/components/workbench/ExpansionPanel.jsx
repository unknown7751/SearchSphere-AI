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
import { runQueryExpansion } from "@/lib/api";
import { formatScore } from "@/lib/formatters";
import { DocLink, RankingTable, SectionTitle } from "./shared";

export default function ExpansionPanel() {
  const [query, setQuery] = useState("neural networks");
  const { data, error, loading, run } = useAsync(runQueryExpansion);

  const submit = (e) => {
    e.preventDefault();
    if (query.trim()) run({ query: query.trim(), topK: 8 });
  };

  const added = data?.expanded_terms.filter((t) => t.selected) || [];

  return (
    <div className="space-y-6">
      <Notice tone="teal">
        <strong>Corpus-based query expansion.</strong> Extra terms are mined from the top-ranked documents of this corpus. No external language
        model or thesaurus is involved.
      </Notice>

      <Card>
        <CardHeader title="Query expansion" />
        <CardBody>
          <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <TextField label="Query" value={query} onChange={(e) => setQuery(e.target.value)} className="flex-1" maxLength={500} />
            <Button type="submit" variant="primary" loading={loading} disabled={!query.trim()}>
              Expand query
            </Button>
          </form>
        </CardBody>
      </Card>

      {error && <ErrorState error={error} onRetry={() => run({ query: query.trim(), topK: 8 })} />}

      {data && (
        <>
          <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Card>
              <CardHeader title="Original → expanded" />
              <CardBody className="space-y-3">
                <Flow
                  steps={[
                    { label: "Original query", value: data.original_query, note: `index terms: ${data.preprocessing.index_terms.join(", ") || "none"}` },
                    {
                      label: "Feedback documents",
                      value: (
                        <ul className="font-sans text-sm">
                          {data.feedback_documents.map((d) => (
                            <li key={d.doc_id}>
                              <span className="mr-1 font-mono text-xs text-mute">#{d.doc_id}</span>
                              <DocLink id={d.doc_id} title={d.title} />
                            </li>
                          ))}
                        </ul>
                      ),
                      note: "top-ranked for the original query",
                    },
                    { label: "Expansion terms", value: <TokenList tokens={added.map((t) => t.display)} tone="teal" emptyLabel="none selected" /> },
                    { label: "Expanded query", value: <strong>{data.final_expanded_query}</strong> },
                  ]}
                />
                {data.message && <Notice tone="warn">{data.message}</Notice>}
                <p className="text-xs text-mute">{data.method}</p>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Why these terms?" description="Candidates scored by the centroid of the feedback documents' TF-IDF vectors." />
              <Table caption="Candidate expansion terms">
                <thead>
                  <tr>
                    <Th>Term</Th>
                    <Th align="right">Score</Th>
                    <Th align="right">Support</Th>
                    <Th align="right">DF</Th>
                    <Th align="right">IDF</Th>
                    <Th>Selected</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.candidate_terms.map((c) => (
                    <tr key={c.term} className={c.selected ? "bg-teal-50" : ""}>
                      <Td>{c.display}</Td>
                      <Td align="right" mono>{formatScore(c.score)}</Td>
                      <Td align="right" mono>{c.support}</Td>
                      <Td align="right" mono>{c.document_frequency}</Td>
                      <Td align="right" mono>{formatScore(c.idf, 3)}</Td>
                      <Td>{c.selected ? <Badge tone="teal">added</Badge> : <span className="text-mute">—</span>}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <p className="border-t border-mute-line px-3 py-2 text-xs text-mute">Support = number of feedback documents containing the term.</p>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Ranking before" description="Original query only" />
              <CardBody>
                <RankingTable rows={data.ranking_before} caption="Ranking before expansion" />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Ranking after" description="Expanded query vector" />
              <CardBody>
                <SectionTitle>Rank movement versus the original</SectionTitle>
                <RankingTable rows={data.ranking_after} caption="Ranking after expansion" showChange />
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
