"use client";

import { useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { TokenList } from "@/components/ui/Flow";
import { ErrorState } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { booleanSearch, getIncidenceMatrix } from "@/lib/api";
import { BOOLEAN_EXAMPLES } from "@/lib/constants";
import { DocLink, SectionTitle } from "./shared";

/** Recursive view of the backend's parsed expression tree (`ast`). */
function AstNode({ node }) {
  if (!node) return null;
  if (node.type === "TERM") {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-mute-line bg-white px-1.5 py-0.5 font-mono text-xs">
        {node.value}
        {node.index_terms?.length > 0 && <span className="text-teal-700">→ {node.index_terms.join(" ")}</span>}
      </span>
    );
  }
  const children = node.type === "NOT" ? [node.child] : [node.left, node.right];
  return (
    <div className="rounded border border-teal-200 bg-teal-50/50 p-2">
      <Badge tone="teal">{node.type}</Badge>
      <div className="mt-2 flex flex-wrap items-start gap-2 border-l-2 border-teal-200 pl-3">
        {children.map((child, i) => (
          <AstNode key={i} node={child} />
        ))}
      </div>
    </div>
  );
}

async function runBoolean(query, opts) {
  const result = await booleanSearch({ query, pageSize: 50 }, opts);
  // Incidence matrix for the query's own terms over (up to 15 of) the matching documents. Backend computes it.
  let matrix = null;
  const terms = Object.keys(result.index_terms);
  if (terms.length > 0 && result.matching_doc_ids.length > 0) {
    try {
      matrix = await getIncidenceMatrix({ terms, documentIds: result.matching_doc_ids.slice(0, 15) }, opts);
    } catch {
      matrix = null; // the matrix is a bonus view; the Boolean result is still valid
    }
  }
  return { result, matrix };
}

export default function BooleanPanel() {
  const [query, setQuery] = useState(BOOLEAN_EXAMPLES[0]);
  const { data, error, loading, run } = useAsync(runBoolean);

  const submit = (e) => {
    e.preventDefault();
    if (query.trim()) run(query.trim());
  };
  const result = data?.result;
  const matrix = data?.matrix;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Boolean retrieval" description="Operators AND, OR, NOT and parentheses are evaluated by the backend over postings lists." />
        <CardBody>
          <form onSubmit={submit} className="space-y-3">
            <TextField label="Boolean query" value={query} onChange={(e) => setQuery(e.target.value)} mono maxLength={500} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" variant="primary" loading={loading} disabled={!query.trim()}>
                Run Boolean query
              </Button>
              <span className="text-xs text-mute">Examples:</span>
              {BOOLEAN_EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => setQuery(ex)} className="rounded border border-mute-line bg-white px-2 py-0.5 font-mono text-xs hover:border-teal-600">
                  {ex}
                </button>
              ))}
            </div>
          </form>
        </CardBody>
      </Card>

      {error && <ErrorState error={error} onRetry={() => run(query.trim())} />}

      {result && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Parsed query" actions={<Badge tone="teal">{result.total_results} matches</Badge>} />
            <CardBody className="space-y-3">
              <p className="break-all rounded bg-paper-dark px-2 py-1 font-mono text-sm">{result.parsed_expression}</p>
              <AstNode node={result.ast} />
              {result.unknown_terms.length > 0 && (
                <p className="text-sm text-mute">
                  No postings for: <TokenList tokens={result.unknown_terms} />
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Evaluation steps" description="Postings lookups, then set operations." />
            <Table caption="Boolean evaluation steps">
              <thead>
                <tr>
                  <Th>#</Th>
                  <Th>Operation</Th>
                  <Th>Description</Th>
                  <Th align="right">Size</Th>
                </tr>
              </thead>
              <tbody>
                {result.steps.map((s) => (
                  <tr key={s.step}>
                    <Td mono>{s.step}</Td>
                    <Td><Badge tone={s.operation === "LOOKUP" ? "neutral" : "teal"}>{s.operation}</Badge></Td>
                    <Td className="font-mono text-xs">{s.description}</Td>
                    <Td align="right" mono>{s.result_size}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>

          {matrix && matrix.rows.length > 0 && (
            <Card className="lg:col-span-2">
              <CardHeader
                title="Term–document incidence matrix"
                description={`1 = the document contains the term. Columns: ${matrix.documents.length} matching document(s).`}
              />
              <Table caption="Binary incidence matrix">
                <thead>
                  <tr>
                    <Th>Term</Th>
                    <Th align="right">DF</Th>
                    {matrix.documents.map((d) => (
                      <Th key={d.doc_id} align="right">
                        <span title={d.title}>#{d.doc_id}</span>
                      </Th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.rows.map((row) => (
                    <tr key={row.term}>
                      <Td mono>{row.term}</Td>
                      <Td align="right" mono>{row.document_frequency}</Td>
                      {row.row.map((cell, i) => (
                        <Td key={i} align="right" mono className={cell ? "bg-teal-50 font-semibold text-teal-800" : "text-mute"}>
                          {cell}
                        </Td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          )}

          <Card className="lg:col-span-2">
            <CardHeader title="Matching documents" description={result.total_results > result.results.length ? `Showing the first ${result.results.length} of ${result.total_results}` : undefined} />
            <CardBody>
              {result.results.length === 0 ? (
                <p className="text-sm text-mute">No documents matched your query.</p>
              ) : (
                <>
                  <SectionTitle>Documents</SectionTitle>
                  <ul className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                    {result.results.map((d) => (
                      <li key={d.doc_id} className="truncate">
                        <span className="mr-2 font-mono text-xs text-mute">#{d.doc_id}</span>
                        <DocLink id={d.doc_id} title={d.title} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
