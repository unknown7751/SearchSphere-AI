"use client";

import { useEffect, useState } from "react";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import KeyValue from "@/components/ui/KeyValue";
import MetricCard from "@/components/ui/MetricCard";
import Pagination from "@/components/ui/Pagination";
import { ErrorState, Notice, TableSkeleton } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { useDebounce } from "@/hooks/useDebounce";
import { getInvertedIndex } from "@/lib/api";
import { formatNumber, formatScore } from "@/lib/formatters";
import { DocLink } from "./shared";

const PAGE_SIZE = 25;

export default function InvertedIndexPanel() {
  const [prefix, setPrefix] = useState("");
  const debouncedPrefix = useDebounce(prefix.trim().toLowerCase(), 350);
  const [page, setPage] = useState(1);
  const [termInput, setTermInput] = useState("");

  const vocab = useAsync(getInvertedIndex);
  const lookup = useAsync(getInvertedIndex);
  const { run: runVocab } = vocab;

  useEffect(() => {
    runVocab({ prefix: debouncedPrefix || undefined, page, pageSize: PAGE_SIZE });
  }, [debouncedPrefix, page, runVocab]);

  const lookupTerm = (term) => {
    setTermInput(term);
    if (term.trim()) lookup.run({ term: term.trim() });
  };

  const stats = vocab.data?.stats;

  return (
    <div className="space-y-6">
      <Notice>
        The index maps each stemmed term to a postings list of <code className="font-mono">(document, term frequency)</code> pairs. This index stores
        term frequencies only — it does not store token positions.
      </Notice>

      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Documents" value={formatNumber(stats.num_documents)} />
          <MetricCard label="Vocabulary" value={formatNumber(stats.vocabulary_size)} hint="distinct index terms" />
          <MetricCard label="Postings" value={formatNumber(stats.total_postings)} />
          <MetricCard label="Avg doc length" value={formatScore(stats.average_document_length, 1)} hint="index tokens" />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Vocabulary" description="Alphabetical index terms (stems) with document frequency. Loaded one page at a time." />
          <CardBody className="space-y-3">
            <TextField label="Filter by prefix" value={prefix} onChange={(e) => { setPrefix(e.target.value); setPage(1); }} placeholder="e.g. mach" mono />
          </CardBody>
          {vocab.error ? (
            <div className="p-4">
              <ErrorState error={vocab.error} onRetry={() => runVocab({ prefix: debouncedPrefix || undefined, page, pageSize: PAGE_SIZE })} />
            </div>
          ) : !vocab.data ? (
            <TableSkeleton rows={8} cols={3} />
          ) : vocab.data.terms.length === 0 ? (
            <p className="p-4 text-sm text-mute">No index terms start with “{debouncedPrefix}”.</p>
          ) : (
            <div className={vocab.loading ? "opacity-60" : ""}>
              <Table caption="Index vocabulary">
                <thead>
                  <tr>
                    <Th>Term</Th>
                    <Th align="right">DF</Th>
                    <Th>Postings</Th>
                  </tr>
                </thead>
                <tbody>
                  {vocab.data.terms.map((t) => (
                    <tr key={t.term}>
                      <Td mono>{t.term}</Td>
                      <Td align="right" mono>{t.document_frequency}</Td>
                      <Td>
                        <button type="button" onClick={() => lookupTerm(t.term)} className="text-sm text-teal-700 hover:underline" aria-label={`Show postings for ${t.term}`}>
                          Show postings
                        </button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
          <div className="border-t border-mute-line p-3">
            <p className="mb-2 text-xs text-mute" role="status">
              {vocab.data ? `${formatNumber(vocab.data.total_terms)} term(s)` : ""}
            </p>
            <Pagination page={page} totalPages={vocab.data ? Math.ceil(vocab.data.total_terms / PAGE_SIZE) : 0} onChange={setPage} disabled={vocab.loading} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Postings list" description="Look up any word; it is normalised (stemmed) exactly like a query term." />
          <CardBody className="space-y-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                lookupTerm(termInput);
              }}
              className="flex items-end gap-2"
            >
              <TextField label="Word" value={termInput} onChange={(e) => setTermInput(e.target.value)} className="flex-1" mono placeholder="learning" />
              <Button type="submit" variant="primary" loading={lookup.loading} disabled={!termInput.trim()}>
                Look up
              </Button>
            </form>
            {lookup.error && <ErrorState error={lookup.error} onRetry={() => lookupTerm(termInput)} />}
            {lookup.data && "postings" in lookup.data && (
              <div className="space-y-3">
                <KeyValue
                  items={[
                    { label: "You typed", value: <span className="font-mono">{lookup.data.query}</span> },
                    { label: "Index term", value: <span className="font-mono">{lookup.data.term}</span> },
                    { label: "Document frequency", value: <span className="font-mono">{lookup.data.document_frequency}</span> },
                  ]}
                />
                {lookup.data.postings.length === 0 ? (
                  <p className="text-sm text-mute">This term does not occur in any indexed document.</p>
                ) : (
                  <Table caption={`Postings for ${lookup.data.term}`}>
                    <thead>
                      <tr>
                        <Th align="right">Doc ID</Th>
                        <Th>Title</Th>
                        <Th align="right">TF</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {lookup.data.postings.map((p) => (
                        <tr key={p.doc_id}>
                          <Td align="right" mono>{p.doc_id}</Td>
                          <Td><DocLink id={p.doc_id} title={p.title} /></Td>
                          <Td align="right" mono>{p.tf}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
