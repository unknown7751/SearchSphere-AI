"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import Formula from "@/components/ui/Formula";
import { TokenList } from "@/components/ui/Flow";
import { ErrorState } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { getTFIDF } from "@/lib/api";
import { formatScore } from "@/lib/formatters";
import DocumentPicker from "./DocumentPicker";
import { DocLink, SectionTitle } from "./shared";

/** Weight table whose last column shows tf × idf with the numbers the backend returned. */
function WeightTable({ rows, numDocs, caption }) {
  return (
    <Table caption={caption}>
      <thead>
        <tr>
          <Th>Term</Th>
          <Th align="right">TF</Th>
          <Th align="right">DF</Th>
          <Th align="right">IDF</Th>
          <Th align="right">TF-IDF</Th>
          <Th>Calculation</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.term}>
            <Td mono>{r.term}</Td>
            <Td align="right" mono>{r.tf}</Td>
            <Td align="right" mono>{r.df}</Td>
            <Td align="right" mono>{formatScore(r.idf)}</Td>
            <Td align="right" mono className="font-semibold">{formatScore(r.tfidf)}</Td>
            <Td className="whitespace-nowrap font-mono text-xs text-mute">
              idf = ln(({numDocs}+1)/({r.df}+1))+1 = {formatScore(r.idf, 3)} · {r.tf} × {formatScore(r.idf, 3)}
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function TfidfPanel() {
  const [docIds, setDocIds] = useState([30]);
  const [query, setQuery] = useState("machine learning");
  const { data, error, loading, run } = useAsync(getTFIDF);

  const submit = (e) => {
    e.preventDefault();
    if (docIds.length) run({ documentIds: docIds, query: query.trim() || undefined, topN: 10 });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="space-y-6">
        <Card>
          <CardHeader title="TF-IDF weighting" description="Pick documents and (optionally) a query to see term weights." />
          <CardBody>
            <form onSubmit={submit} className="space-y-3">
              <DocumentPicker label="Documents" value={docIds} onChange={setDocIds} max={20} />
              <TextField label="Query (optional)" value={query} onChange={(e) => setQuery(e.target.value)} hint="Shows each query term's weight in every chosen document." />
              <Button type="submit" variant="primary" loading={loading} disabled={docIds.length === 0}>
                Compute TF-IDF
              </Button>
            </form>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Formulas used by the backend" />
          <CardBody className="space-y-2">
            <Formula>tf(t, d) = raw count of t in d</Formula>
            <Formula>idf(t) = ln( (N + 1) / (df(t) + 1) ) + 1</Formula>
            <Formula caption="The same quantity is written log(...) in textbooks; the backend uses the natural logarithm with +1 smoothing.">
              tfidf(t, d) = tf(t, d) × idf(t)
            </Formula>
          </CardBody>
        </Card>
      </div>

      <div className="min-w-0 space-y-6">
        {error && <ErrorState error={error} onRetry={() => run({ documentIds: docIds, query: query.trim() || undefined, topN: 10 })} />}
        {!data && !error && <p className="rounded border border-dashed border-mute-line p-6 text-center text-sm text-mute">Results appear here.</p>}
        {data && (
          <>
            {data.query_terms && (
              <Card>
                <CardHeader title="Query terms" description={`N = ${data.num_documents} indexed documents`} />
                <CardBody className="space-y-2">
                  {data.query_terms.length ? (
                    <WeightTable rows={data.query_terms} numDocs={data.num_documents} caption="Query term weights" />
                  ) : (
                    <p className="text-sm text-mute">No query term is present in the index.</p>
                  )}
                  {data.unknown_terms.length > 0 && (
                    <p className="text-sm text-mute">
                      Not in index: <TokenList tokens={data.unknown_terms} />
                    </p>
                  )}
                </CardBody>
              </Card>
            )}
            {data.documents.map((d) => (
              <Card key={d.doc_id}>
                <CardHeader
                  title={<DocLink id={d.doc_id} title={d.title} />}
                  description={`Document vector: ${d.vector_size} distinct terms`}
                />
                <CardBody className="space-y-4">
                  {d.query_term_weights.length > 0 && (
                    <div>
                      <SectionTitle>Query terms in this document</SectionTitle>
                      <WeightTable rows={d.query_term_weights} numDocs={data.num_documents} caption={`Query term weights in document ${d.doc_id}`} />
                    </div>
                  )}
                  <div>
                    <SectionTitle>Highest-weighted terms</SectionTitle>
                    <WeightTable rows={d.top_terms} numDocs={data.num_documents} caption={`Top TF-IDF terms of document ${d.doc_id}`} />
                  </div>
                </CardBody>
              </Card>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
