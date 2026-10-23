"use client";

import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { SelectField, TextField } from "@/components/ui/Field";
import Formula from "@/components/ui/Formula";
import MetricCard from "@/components/ui/MetricCard";
import { ErrorState, Notice, Spinner } from "@/components/ui/States";
import Tabs, { TabPanel } from "@/components/ui/Tabs";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { getEvaluationDataset, runEvaluation, runMapEvaluation } from "@/lib/api";
import { formatScore } from "@/lib/formatters";
import DocumentPicker from "./DocumentPicker";
import { DocLink, SectionTitle } from "./shared";

const MODES = [
  { value: "tfidf", label: "TF-IDF (ranked)" },
  { value: "expanded", label: "TF-IDF + query expansion" },
  { value: "rocchio", label: "Rocchio (pseudo-feedback)" },
];
const CUSTOM = "__custom__";

function ModeSelect({ value, onChange, allowBoolean }) {
  return (
    <SelectField label="Retrieval mode" value={value} onChange={(e) => onChange(e.target.value)}>
      {MODES.map((m) => (
        <option key={m.value} value={m.value}>
          {m.label}
        </option>
      ))}
      {allowBoolean && <option value="boolean">Boolean (query must use AND / OR / NOT)</option>}
    </SelectField>
  );
}

function SingleQuery({ dataset }) {
  const queries = dataset?.queries || [];
  const [selected, setSelected] = useState(queries[0]?.query ?? CUSTOM);
  const [custom, setCustom] = useState("");
  const [mode, setMode] = useState("tfidf");
  const [k, setK] = useState("10");
  const [relevantIds, setRelevantIds] = useState([]);
  const evaluation = useAsync(runEvaluation);

  const isCustom = selected === CUSTOM;
  const query = isCustom ? custom.trim() : selected;
  const topK = Number(k);
  const kOk = Number.isInteger(topK) && topK >= 1 && topK <= 100;
  const judgments = queries.find((q) => q.query === selected);
  const canRun = query && kOk && (!isCustom || relevantIds.length > 0 || queries.some((q) => q.query === query));

  // Boolean is only offered for custom queries (the stored queries are free text), so leaving custom resets it.
  const chooseQuery = (value) => {
    setSelected(value);
    if (value !== CUSTOM && mode === "boolean") setMode("tfidf");
  };

  const request = () => ({ query, mode, topK, relevantDocIds: isCustom ? relevantIds : undefined });
  const submit = (e) => {
    e.preventDefault();
    if (canRun) evaluation.run(request());
  };
  const data = evaluation.data;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Evaluate one query" description="Compare the ranked list with relevance judgments." />
        <CardBody>
          <form onSubmit={submit} className="space-y-3">
            <div className="grid gap-3 md:grid-cols-3">
              <SelectField label="Query" value={selected} onChange={(e) => chooseQuery(e.target.value)} className="md:col-span-1">
                {queries.map((q) => (
                  <option key={q.id} value={q.query}>
                    {q.query}
                  </option>
                ))}
                <option value={CUSTOM}>Custom query…</option>
              </SelectField>
              <ModeSelect value={mode} onChange={setMode} allowBoolean={isCustom} />
              <TextField label="Cut-off K" type="number" min={1} max={100} value={k} onChange={(e) => setK(e.target.value)} error={kOk ? null : "1 – 100"} />
            </div>
            {isCustom ? (
              <>
                <TextField label="Custom query" value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={500} />
                <DocumentPicker label="Relevant documents (your judgments)" value={relevantIds} onChange={setRelevantIds} max={50} hint="Required for a custom query: the backend needs to know which documents are relevant." />
              </>
            ) : (
              judgments && (
                <p className="text-sm text-mute">
                  {judgments.description} · relevant documents from the stored dataset: <span className="font-mono">{judgments.relevant_doc_ids.join(", ")}</span>
                </p>
              )
            )}
            <Button type="submit" variant="primary" loading={evaluation.loading} disabled={!canRun}>
              Run evaluation
            </Button>
          </form>
        </CardBody>
      </Card>

      {evaluation.error && <ErrorState error={evaluation.error} onRetry={() => evaluation.run(request())} />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <MetricCard label="Precision" value={formatScore(data.metrics.precision)} />
            <MetricCard label="Recall" value={formatScore(data.metrics.recall)} />
            <MetricCard label="F1" value={formatScore(data.metrics.f1)} />
            <MetricCard label={`Precision@${data.counts.k}`} value={formatScore(data.metrics.precision_at_k)} />
            <MetricCard label={`Recall@${data.counts.k}`} value={formatScore(data.metrics.recall_at_k)} />
            <MetricCard label="Average precision" value={formatScore(data.metrics.average_precision)} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Calculations" description={`${data.counts.relevant_retrieved} relevant retrieved of ${data.counts.retrieved} shown · ${data.counts.relevant_total} relevant in total`} />
              <CardBody className="space-y-2">
                {Object.entries(data.calculations).map(([name, text]) => (
                  <div key={name} className="rounded border border-mute-line bg-paper px-3 py-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{name.replaceAll("_", " ")}</p>
                    <p className="mt-0.5 break-words font-mono text-xs text-ink">{text}</p>
                  </div>
                ))}
                {data.missed_relevant_doc_ids.length > 0 && (
                  <p className="text-sm text-mute">
                    Relevant documents missed in the top {data.counts.k}: <span className="font-mono">{data.missed_relevant_doc_ids.join(", ")}</span>
                  </p>
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Average precision steps" description="Precision at each rank where a relevant document appears." />
              <Table caption="Average precision steps">
                <thead>
                  <tr>
                    <Th align="right">Rank</Th>
                    <Th align="right">Doc</Th>
                    <Th align="right">Relevant so far</Th>
                    <Th align="right">P@rank</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.average_precision_steps.length === 0 && (
                    <tr>
                      <Td colSpan={4} className="text-mute">No relevant document was retrieved, so AP = 0.</Td>
                    </tr>
                  )}
                  {data.average_precision_steps.map((s) => (
                    <tr key={s.rank}>
                      <Td align="right" mono>{s.rank}</Td>
                      <Td align="right" mono>{s.doc_id}</Td>
                      <Td align="right" mono>{s.relevant_so_far}</Td>
                      <Td align="right" mono>{formatScore(s.precision_at_rank)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          </div>

          <Card>
            <CardHeader title={`Top ${data.counts.k} ranked documents`} />
            <Table caption="Ranked documents with relevance and running precision and recall">
              <thead>
                <tr>
                  <Th align="right">Rank</Th>
                  <Th>Document</Th>
                  <Th>Relevant</Th>
                  <Th align="right">Relevant so far</Th>
                  <Th align="right">Precision@rank</Th>
                  <Th align="right">Recall@rank</Th>
                </tr>
              </thead>
              <tbody>
                {data.ranked_documents.map((r) => (
                  <tr key={r.doc_id} className={r.relevant ? "bg-teal-50/60" : ""}>
                    <Td align="right" mono>{r.rank}</Td>
                    <Td>
                      <span className="mr-2 font-mono text-xs text-mute">#{r.doc_id}</span>
                      <DocLink id={r.doc_id} title={r.title} />
                    </Td>
                    <Td>
                      {r.relevant ? (
                        <span className="inline-flex items-center gap-1 text-green-800">
                          <Check className="h-4 w-4" aria-hidden="true" /> relevant
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-mute">
                          <X className="h-4 w-4" aria-hidden="true" /> not relevant
                        </span>
                      )}
                    </Td>
                    <Td align="right" mono>{r.relevant_so_far}</Td>
                    <Td align="right" mono>{formatScore(r.precision_at_rank)}</Td>
                    <Td align="right" mono>{formatScore(r.recall_at_rank)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </>
      )}
    </div>
  );
}

function MapEvaluation() {
  const [mode, setMode] = useState("tfidf");
  const [k, setK] = useState("10");
  const evaluation = useAsync(runMapEvaluation);
  const topK = Number(k);
  const kOk = Number.isInteger(topK) && topK >= 1 && topK <= 100;
  const data = evaluation.data;

  const submit = (e) => {
    e.preventDefault();
    if (kOk) evaluation.run({ mode, topK });
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Mean Average Precision" description="Runs every judged query of the stored evaluation dataset." />
        <CardBody>
          <form onSubmit={submit} className="grid items-end gap-3 sm:grid-cols-[1fr_8rem_auto]">
            <ModeSelect value={mode} onChange={setMode} />
            <TextField label="Cut-off K" type="number" min={1} max={100} value={k} onChange={(e) => setK(e.target.value)} error={kOk ? null : "1 – 100"} />
            <Button type="submit" variant="primary" loading={evaluation.loading} disabled={!kOk}>
              Run MAP
            </Button>
          </form>
          <Formula className="mt-4" caption="AP(q) averages the precision at each rank holding a relevant document, divided by the number of relevant documents.">
            MAP = (1/Q) Σ<sub>q</sub> AP(q),  AP(q) = (1/|R<sub>q</sub>|) Σ<sub>k</sub> P(k) · rel(k)
          </Formula>
        </CardBody>
      </Card>

      {evaluation.error && <ErrorState error={evaluation.error} onRetry={() => evaluation.run({ mode, topK })} />}
      {evaluation.loading && !data && <Spinner label="Evaluating all queries" />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard label="MAP" value={formatScore(data.mean_average_precision)} hint={`${data.query_count} queries`} />
            <MetricCard label={`Mean P@${data.top_k}`} value={formatScore(data.mean_precision_at_k)} />
            <MetricCard label={`Mean R@${data.top_k}`} value={formatScore(data.mean_recall_at_k)} />
            <MetricCard label="Mode" value={<span className="text-lg">{data.mode}</span>} />
          </div>
          <Card>
            <CardHeader title="Average precision per query" />
            <Table caption="Per-query metrics">
              <thead>
                <tr>
                  <Th>Query</Th>
                  <Th align="right">AP</Th>
                  <Th align="right">P@{data.top_k}</Th>
                  <Th align="right">R@{data.top_k}</Th>
                  <Th align="right">Precision</Th>
                  <Th align="right">Recall</Th>
                  <Th align="right">F1</Th>
                </tr>
              </thead>
              <tbody>
                {data.per_query.map((q) => (
                  <tr key={q.query}>
                    <Td className="font-medium">{q.query}</Td>
                    <Td align="right" mono className="font-semibold">{formatScore(q.average_precision)}</Td>
                    <Td align="right" mono>{formatScore(q.precision_at_k)}</Td>
                    <Td align="right" mono>{formatScore(q.recall_at_k)}</Td>
                    <Td align="right" mono>{formatScore(q.precision)}</Td>
                    <Td align="right" mono>{formatScore(q.recall)}</Td>
                    <Td align="right" mono>{formatScore(q.f1)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="border-t border-mute-line p-4">
              <SectionTitle>MAP calculation</SectionTitle>
              <p className="break-words font-mono text-xs text-ink">MAP = {data.map_calculation}</p>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

export default function EvaluationPanel() {
  const [tab, setTab] = useState("single");
  const dataset = useAsync(getEvaluationDataset);
  const { run } = dataset;

  useEffect(() => {
    run();
  }, [run]);

  if (dataset.error) return <ErrorState error={dataset.error} onRetry={() => run()} />;
  if (!dataset.data) return <Spinner label="Loading evaluation dataset" />;
  if (dataset.data.query_count === 0)
    return <Notice tone="warn">No evaluation dataset is loaded. Run <code className="font-mono">python -m app.cli seed-evaluation</code> in the backend.</Notice>;

  const tabs = [
    { id: "single", label: "Single query" },
    { id: "map", label: "MAP over dataset" },
  ];
  return (
    <div>
      <Tabs tabs={tabs} value={tab} onChange={setTab} label="Evaluation views" idPrefix="eval" />
      <TabPanel id="single" active={tab === "single"} idPrefix="eval">
        <SingleQuery dataset={dataset.data} />
      </TabPanel>
      <TabPanel id="map" active={tab === "map"} idPrefix="eval">
        <MapEvaluation />
      </TabPanel>
    </div>
  );
}
