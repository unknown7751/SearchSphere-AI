"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import Flow, { TokenList } from "@/components/ui/Flow";
import Formula from "@/components/ui/Formula";
import { ErrorState } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { getCosine } from "@/lib/api";
import { formatScore } from "@/lib/formatters";
import DocumentPicker from "./DocumentPicker";
import { DocLink, SectionTitle } from "./shared";

function CosineDocument({ doc, queryVector }) {
  const terms = Object.keys(doc.term_contributions);
  return (
    <Card>
      <CardHeader
        title={
          <span>
            <span className="mr-2 font-mono text-sm text-mute">#{doc.rank}</span>
            <DocLink id={doc.doc_id} title={doc.title} />
          </span>
        }
        description={`Document ${doc.doc_id}`}
      />
      <CardBody className="grid gap-5 xl:grid-cols-2">
        <div>
          <SectionTitle>Vectors on the shared terms</SectionTitle>
          {terms.length === 0 ? (
            <p className="text-sm text-mute">The query and this document share no terms, so the dot product is 0.</p>
          ) : (
            <Table caption="Query and document weights on shared terms, with each term's product">
              <thead>
                <tr>
                  <Th>Term</Th>
                  <Th align="right">q</Th>
                  <Th align="right">d</Th>
                  <Th align="right">q × d</Th>
                </tr>
              </thead>
              <tbody>
                {terms.map((t) => (
                  <tr key={t}>
                    <Td mono>{t}</Td>
                    <Td align="right" mono>{formatScore(queryVector[t])}</Td>
                    <Td align="right" mono>{formatScore(doc.document_vector_shared_terms[t])}</Td>
                    <Td align="right" mono>{formatScore(doc.term_contributions[t])}</Td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <Td colSpan={3} className="font-semibold">Dot product Σ q·d</Td>
                  <Td align="right" mono className="font-semibold">{formatScore(doc.dot_product)}</Td>
                </tr>
              </tfoot>
            </Table>
          )}
        </div>
        <Flow
          steps={[
            { label: "Query vector q + document vector d", value: `${terms.length} shared term(s)` },
            { label: "Dot product", value: `q·d = ${formatScore(doc.dot_product)}` },
            { label: "Vector norms", value: `‖q‖ = ${formatScore(doc.query_norm)}   ‖d‖ = ${formatScore(doc.document_norm)}` },
            { label: "Cosine similarity", value: `${formatScore(doc.dot_product)} / (${formatScore(doc.query_norm)} × ${formatScore(doc.document_norm)}) = ${formatScore(doc.cosine)}` },
            { label: "Score", value: <strong className="text-lg text-navy-800">{formatScore(doc.cosine)}</strong> },
          ]}
        />
      </CardBody>
    </Card>
  );
}

export default function CosinePanel() {
  const [query, setQuery] = useState("machine learning");
  const [docIds, setDocIds] = useState([]);
  const { data, error, loading, run } = useAsync(getCosine);

  const submit = (e) => {
    e.preventDefault();
    if (query.trim()) run({ query: query.trim(), documentIds: docIds, topK: 3 });
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Card>
          <CardHeader title="Cosine similarity" description="Without chosen documents, the top 3 ranked documents are explained." />
          <CardBody>
            <form onSubmit={submit} className="space-y-3">
              <TextField label="Query" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={500} />
              <DocumentPicker label="Compare specific documents (optional)" value={docIds} onChange={setDocIds} max={10} />
              <Button type="submit" variant="primary" loading={loading} disabled={!query.trim()}>
                Compute cosine
              </Button>
            </form>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Formula" />
          <CardBody className="space-y-3">
            <Formula caption="q and d are TF-IDF vectors; ‖·‖ is the Euclidean norm.">cos(q, d) = (q · d) / (‖q‖ ‖d‖)</Formula>
            {data && (
              <div className="space-y-1 text-sm">
                <p className="text-mute">Query index terms</p>
                <TokenList tokens={data.query_terms} tone="teal" />
                {data.unknown_terms.length > 0 && (
                  <p className="text-mute">
                    Not in index: <TokenList tokens={data.unknown_terms} />
                  </p>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {error && <ErrorState error={error} onRetry={() => run({ query: query.trim(), documentIds: docIds, topK: 3 })} />}
      {data && data.documents.length === 0 && <p className="rounded border border-dashed border-mute-line p-6 text-center text-sm text-mute">No document matched the query terms.</p>}
      {data?.documents.map((doc) => (
        <CosineDocument key={doc.doc_id} doc={doc} queryVector={data.query_vector} />
      ))}
    </div>
  );
}
