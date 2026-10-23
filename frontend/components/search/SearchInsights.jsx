import Badge from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TokenList } from "@/components/ui/Flow";
import { Table, Td, Th } from "@/components/ui/Table";
import { formatScore } from "@/lib/formatters";

/** How the backend turned the typed query into index terms (ranked, expanded and Rocchio modes). */
export function QueryAnalysis({ analysis }) {
  if (!analysis) return null;
  return (
    <div className="rounded border border-mute-line bg-white px-3 py-2 text-sm">
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-[max-content_1fr]">
        <dt className="text-mute">Tokens</dt>
        <dd><TokenList tokens={analysis.tokens} /></dd>
        {analysis.stop_words_removed.length > 0 && (
          <>
            <dt className="text-mute">Stop words removed</dt>
            <dd><TokenList tokens={analysis.stop_words_removed} tone="removed" /></dd>
          </>
        )}
        <dt className="text-mute">Index terms (stemmed)</dt>
        <dd><TokenList tokens={analysis.index_terms} tone="teal" /></dd>
        {analysis.unknown_terms.length > 0 && (
          <>
            <dt className="text-mute">Not in index</dt>
            <dd><TokenList tokens={analysis.unknown_terms} /></dd>
          </>
        )}
      </dl>
    </div>
  );
}

export function BooleanInsight({ data }) {
  return (
    <Card>
      <CardHeader title="Boolean evaluation" description="The backend parsed the query and evaluated it on postings lists." />
      <CardBody className="space-y-3">
        <p className="text-sm">
          <span className="text-mute">Parsed expression: </span>
          <code className="break-all rounded bg-paper-dark px-1.5 py-0.5 font-mono text-xs">{data.parsedExpression}</code>
        </p>
        {data.unknownTerms.length > 0 && (
          <p className="text-sm text-mute">
            Terms with no postings: <TokenList tokens={data.unknownTerms} />
          </p>
        )}
        <Table caption="Boolean evaluation steps">
          <thead>
            <tr>
              <Th>Step</Th>
              <Th>Operation</Th>
              <Th>Description</Th>
              <Th align="right">Result size</Th>
            </tr>
          </thead>
          <tbody>
            {data.steps.map((s) => (
              <tr key={s.step}>
                <Td mono>{s.step}</Td>
                <Td><Badge tone={s.operation === "LOOKUP" ? "neutral" : "teal"}>{s.operation}</Badge></Td>
                <Td className="font-mono text-xs">{s.description}</Td>
                <Td align="right" mono>{s.result_size}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </CardBody>
    </Card>
  );
}

export function WildcardInsight({ data }) {
  return (
    <Card>
      <CardHeader
        title="Dictionary expansion"
        description={`${data.kind} lookup — ${data.strategy}`}
        actions={<Badge tone="teal">{data.totalMatches} matching terms</Badge>}
      />
      <CardBody>
        <Table caption="Dictionary terms matching the pattern">
          <thead>
            <tr>
              <Th>Term</Th>
              <Th>Index term</Th>
              <Th align="right">Documents</Th>
            </tr>
          </thead>
          <tbody>
            {data.matchedTerms.map((m) => (
              <tr key={m.term}>
                <Td mono>{m.term}</Td>
                <Td mono>{m.index_term}</Td>
                <Td align="right" mono>{m.document_count}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {data.truncated && (
          <p className="mt-2 text-xs text-mute">Only the most frequent matches were expanded (backend expansion limit).</p>
        )}
      </CardBody>
    </Card>
  );
}

export function ExpansionInsight({ expansion }) {
  const added = expansion.expanded_terms.filter((t) => t.selected);
  return (
    <Card>
      <CardHeader
        title="Corpus-based query expansion"
        description="Terms were mined from the top-ranked documents of this corpus; no external model is involved."
      />
      <CardBody className="space-y-2 text-sm">
        <p>
          <span className="text-mute">Expanded query: </span>
          <strong>{expansion.final_expanded_query}</strong>
        </p>
        {added.length > 0 ? (
          <Table caption="Expansion terms added to the query">
            <thead>
              <tr>
                <Th>Added term</Th>
                <Th align="right">Score</Th>
                <Th align="right">Supporting docs</Th>
                <Th align="right">DF</Th>
              </tr>
            </thead>
            <tbody>
              {added.map((t) => (
                <tr key={t.term}>
                  <Td>{t.display}</Td>
                  <Td align="right" mono>{formatScore(t.score)}</Td>
                  <Td align="right" mono>{t.support}</Td>
                  <Td align="right" mono>{t.document_frequency}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="text-mute">{expansion.message || "No expansion terms qualified for this query."}</p>
        )}
      </CardBody>
    </Card>
  );
}

export function RocchioInsight({ rocchio }) {
  return (
    <Card>
      <CardHeader
        title="Pseudo-relevance feedback (Rocchio)"
        description={`The top results ${rocchio.relevant_documents.length ? `(documents ${rocchio.relevant_documents.join(", ")})` : ""} were assumed relevant to build a modified query vector.`}
        actions={<Badge>{`α ${rocchio.alpha} · β ${rocchio.beta} · γ ${rocchio.gamma}`}</Badge>}
      />
      <CardBody className="text-sm">
        <p className="text-mute">Strongest terms in the modified query</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {rocchio.top_positive_terms.map((t) => (
            <span key={t.term} className="rounded border border-teal-200 bg-teal-50 px-1.5 py-0.5 font-mono text-xs text-teal-800">
              {t.word} {formatScore(t.weight, 3)}
            </span>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}
