"use client";

import { useState } from "react";
import { Minus, Plus, Search } from "lucide-react";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import Formula from "@/components/ui/Formula";
import { ErrorState, Notice, ResultsSkeleton } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import ResultCard from "@/components/search/ResultCard";
import { useAsync } from "@/hooks/useAsync";
import { rocchioSearch, runRocchio } from "@/lib/api";
import { formatScore } from "@/lib/formatters";
import DocumentPicker from "./DocumentPicker";
import { DocLink, RankingTable, SectionTitle, VectorTable } from "./shared";

const PSEUDO_DOCS = 3;

function parseWeight(text) {
  const n = Number(text);
  return text.trim() !== "" && Number.isFinite(n) && n >= 0 && n <= 10 ? n : null;
}

function Operator({ children }) {
  return (
    <div className="flex items-center justify-center text-2xl font-light text-mute-light" aria-hidden="true">
      {children}
    </div>
  );
}

export default function RocchioPanel() {
  const [query, setQuery] = useState("machine learning");
  const [relevant, setRelevant] = useState([30, 31]);
  const [nonRelevant, setNonRelevant] = useState([2]);
  const [alpha, setAlpha] = useState("1");
  const [beta, setBeta] = useState("0.75");
  const [gamma, setGamma] = useState("0.15");
  const [pseudo, setPseudo] = useState(false);

  const analysis = useAsync(runRocchio);
  const search = useAsync(rocchioSearch);

  const a = parseWeight(alpha);
  const b = parseWeight(beta);
  const g = parseWeight(gamma);
  const weightsOk = a !== null && b !== null && g !== null;
  const hasFeedback = relevant.length > 0 || nonRelevant.length > 0 || pseudo;

  const params = () => ({
    query: query.trim(),
    relevantDocIds: relevant,
    nonRelevantDocIds: nonRelevant,
    alpha: a,
    beta: b,
    gamma: g,
    pseudoFeedbackDocs: pseudo && relevant.length === 0 ? PSEUDO_DOCS : 0,
  });

  const submit = (e) => {
    e.preventDefault();
    if (!query.trim() || !weightsOk || !hasFeedback) return;
    search.reset();
    analysis.run({ ...params(), topK: 8, vectorTerms: 10 });
  };

  const data = analysis.data;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader title="Rocchio relevance feedback" description="Move the query vector toward relevant documents and away from non-relevant ones." />
          <CardBody>
            <form onSubmit={submit} className="space-y-4">
              <TextField label="Original query" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={500} />
              <div className="grid gap-4 xl:grid-cols-2">
                <DocumentPicker label="Relevant documents (Dr)" value={relevant} onChange={setRelevant} max={20} />
                <DocumentPicker label="Non-relevant documents (Dnr)" value={nonRelevant} onChange={setNonRelevant} max={20} />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <TextField label="α (original)" inputMode="decimal" value={alpha} onChange={(e) => setAlpha(e.target.value)} error={a === null ? "0 – 10" : null} mono />
                <TextField label="β (relevant)" inputMode="decimal" value={beta} onChange={(e) => setBeta(e.target.value)} error={b === null ? "0 – 10" : null} mono />
                <TextField label="γ (non-relevant)" inputMode="decimal" value={gamma} onChange={(e) => setGamma(e.target.value)} error={g === null ? "0 – 10" : null} mono />
              </div>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={pseudo} onChange={(e) => setPseudo(e.target.checked)} className="mt-1" />
                <span>
                  Pseudo-feedback: if no relevant documents are chosen, treat the top {PSEUDO_DOCS} baseline results as relevant.
                </span>
              </label>
              {!hasFeedback && <p className="text-sm text-amber-800">Choose at least one relevant or non-relevant document, or enable pseudo-feedback.</p>}
              <Button type="submit" variant="primary" loading={analysis.loading} disabled={!query.trim() || !weightsOk || !hasFeedback}>
                Compute modified query
              </Button>
            </form>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Formula" />
          <CardBody className="space-y-3">
            <Formula caption="q₀ original vector; Dᵣ relevant set; Dₙᵣ non-relevant set. Negative weights are clipped to zero.">
              q<sub>m</sub> = α·q₀ + (β / |Dᵣ|) Σ<sub>d∈Dᵣ</sub> d − (γ / |Dₙᵣ|) Σ<sub>d∈Dₙᵣ</sub> d
            </Formula>
            <p className="text-sm text-mute">
              Defaults α = 1, β = 0.75, γ = 0.15. Vectors are L2-normalised before combining, so a long document does not dominate the centroid.
            </p>
          </CardBody>
        </Card>
      </div>

      {analysis.error && <ErrorState error={analysis.error} onRetry={() => analysis.run({ ...params(), topK: 8, vectorTerms: 10 })} />}

      {data && (
        <>
          {data.input.pseudo_feedback && (
            <Notice tone="warn">
              Pseudo-feedback: the top baseline documents ({data.input.relevant_doc_ids.join(", ")}) were assumed relevant. No human judgments were used.
            </Notice>
          )}

          <Card>
            <CardHeader title="Vector arithmetic" description="Each vector shows its largest components; the backend produced every number." />
            <CardBody className="space-y-5">
              <div className="grid items-start gap-3 xl:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]">
                <div className="min-w-0">
                  <SectionTitle>Original query q₀</SectionTitle>
                  <VectorTable vector={data.original_query_vector} caption="Original query vector" />
                </div>
                <Operator><Plus className="h-6 w-6" /></Operator>
                <div className="min-w-0">
                  <SectionTitle>Relevant contribution</SectionTitle>
                  <p className="mb-1 text-xs text-mute">β × centroid of {data.feedback_documents.relevant.length} doc(s)</p>
                  <VectorTable vector={data.relevant_contribution} caption="Relevant contribution" />
                </div>
                <Operator><Minus className="h-6 w-6" /></Operator>
                <div className="min-w-0">
                  <SectionTitle>Non-relevant contribution</SectionTitle>
                  <p className="mb-1 text-xs text-mute">γ × centroid of {data.feedback_documents.non_relevant.length} doc(s)</p>
                  <VectorTable vector={data.non_relevant_contribution} caption="Non-relevant contribution" />
                </div>
                <Operator>=</Operator>
                <div className="min-w-0">
                  <SectionTitle>Modified query q<sub>m</sub></SectionTitle>
                  <VectorTable vector={data.updated_query_vector} caption="Modified query vector" />
                </div>
              </div>

              <div>
                <SectionTitle>Per-term calculation</SectionTitle>
                <Table caption="Per-term Rocchio calculation">
                  <thead>
                    <tr>
                      <Th>Term</Th>
                      <Th align="right">q₀</Th>
                      <Th align="right">α·q₀</Th>
                      <Th align="right">+ relevant</Th>
                      <Th align="right">− non-relevant</Th>
                      <Th align="right">Before clipping</Th>
                      <Th align="right">q<sub>m</sub></Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.term_calculations.map((t) => (
                      <tr key={t.term}>
                        <Td><span className="font-medium">{t.word}</span> <span className="font-mono text-xs text-mute">({t.term})</span></Td>
                        <Td align="right" mono>{formatScore(t.original)}</Td>
                        <Td align="right" mono>{formatScore(t.alpha_x_original)}</Td>
                        <Td align="right" mono className="text-green-800">{formatScore(t.relevant_contribution)}</Td>
                        <Td align="right" mono className="text-red-800">{formatScore(t.non_relevant_contribution)}</Td>
                        <Td align="right" mono>{formatScore(t.before_clipping)}</Td>
                        <Td align="right" mono className="font-semibold">{formatScore(t.updated)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                {data.clipped_terms.length > 0 && (
                  <p className="mt-2 text-xs text-mute">
                    {data.clipped_terms.length} term(s) went negative and were clipped to 0: {data.clipped_terms.slice(0, 12).join(", ")}
                    {data.clipped_terms.length > 12 ? "…" : ""}
                  </p>
                )}
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <SectionTitle>Top positive terms</SectionTitle>
                  <Table caption="Highest-weighted terms of the modified query">
                    <thead>
                      <tr>
                        <Th>Term</Th>
                        <Th align="right">Weight</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.top_positive_terms.map((t) => (
                        <tr key={t.term}>
                          <Td>{t.word}</Td>
                          <Td align="right" mono className="text-green-800">{formatScore(t.weight)}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
                <div>
                  <SectionTitle>Top negative terms (penalised)</SectionTitle>
                  <Table caption="Terms most penalised by non-relevant documents">
                    <thead>
                      <tr>
                        <Th>Term</Th>
                        <Th align="right">Penalty</Th>
                        <Th align="right">Result</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.top_negative_terms.length === 0 && (
                        <tr>
                          <Td colSpan={3} className="text-mute">No non-relevant documents were given.</Td>
                        </tr>
                      )}
                      {data.top_negative_terms.map((t) => (
                        <tr key={t.term}>
                          <Td>{t.word}</Td>
                          <Td align="right" mono className="text-red-800">−{formatScore(t.penalty)}</Td>
                          <Td align="right" mono>{formatScore(t.resulting_weight)}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </div>
            </CardBody>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Ranking before" description="Original query" />
              <CardBody>
                <RankingTable rows={data.ranking_before} caption="Ranking before Rocchio" />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Ranking after" description="Modified query" />
              <CardBody>
                <RankingTable rows={data.ranking} caption="Ranking after Rocchio" showChange />
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Search with the modified query"
              description="Runs POST /api/search/rocchio with the same feedback and parameters."
              actions={
                <Button variant="primary" size="sm" loading={search.loading} onClick={() => search.run({ ...params(), pageSize: 10 })}>
                  <Search className="h-4 w-4" aria-hidden="true" />
                  Run search with modified query
                </Button>
              }
            />
            <CardBody className="space-y-3">
              {search.error && <ErrorState error={search.error} onRetry={() => search.run({ ...params(), pageSize: 10 })} />}
              {search.loading && !search.data && <ResultsSkeleton rows={3} />}
              {search.data && (
                <>
                  <p className="text-sm text-mute" role="status">
                    {search.data.total_results} result(s) · feedback documents: {data.feedback_documents.relevant.map((d) => `#${d.doc_id}`).join(", ") || "none"}
                  </p>
                  <ol className="space-y-3">
                    {search.data.results.map((r) => (
                      <li key={r.doc_id}>
                        <ResultCard result={r} as="h3" />
                      </li>
                    ))}
                  </ol>
                </>
              )}
              {!search.data && !search.loading && !search.error && <p className="text-sm text-mute">Press the button to see the final ranked results.</p>}
            </CardBody>
          </Card>

          <p className="text-xs text-mute">
            Documents judged:{" "}
            {[...data.feedback_documents.relevant.map((d) => ({ ...d, kind: "relevant" })), ...data.feedback_documents.non_relevant.map((d) => ({ ...d, kind: "non-relevant" }))].map((d, i) => (
              <span key={`${d.kind}-${d.doc_id}`}>
                {i > 0 && " · "}
                <DocLink id={d.doc_id} title={d.title} /> ({d.kind})
              </span>
            ))}
          </p>
        </>
      )}
    </div>
  );
}
