"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextAreaField } from "@/components/ui/Field";
import Flow, { TokenList } from "@/components/ui/Flow";
import { ErrorState } from "@/components/ui/States";
import { Table, Td, Th } from "@/components/ui/Table";
import { useAsync } from "@/hooks/useAsync";
import { preprocessQuery } from "@/lib/api";
import { SectionTitle } from "./shared";

const SAMPLE = "The Running Dogs are chasing better computers in the networks";

export default function PreprocessingPanel() {
  const [text, setText] = useState(SAMPLE);
  const { data, error, loading, run } = useAsync(preprocessQuery);

  const submit = (e) => {
    e.preventDefault();
    if (text.trim()) run(text);
  };

  const aligned =
    data && data.tokens_without_stopwords.length === data.stemmed_tokens.length && data.stemmed_tokens.length === data.lemmatized_tokens.length;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <Card>
        <CardHeader title="Text preprocessing" description="The same pipeline that prepares documents and queries before indexing." />
        <CardBody>
          <form onSubmit={submit} className="space-y-3">
            <TextAreaField label="Text to analyse" value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={50000} />
            <Button type="submit" variant="primary" loading={loading} disabled={!text.trim()}>
              Run preprocessing
            </Button>
          </form>
        </CardBody>
      </Card>

      <div className="min-w-0 space-y-4">
        {error && <ErrorState error={error} onRetry={() => run(text)} />}
        {!data && !error && <p className="rounded border border-dashed border-mute-line p-6 text-center text-sm text-mute">Run the pipeline to see every intermediate stage.</p>}
        {data && (
          <Card>
            <CardHeader title="Pipeline stages" description={`Terms are stored in the index as: ${data.index_form}`} />
            <CardBody className="space-y-5">
              <Flow
                steps={[
                  { label: "Original text", value: data.original },
                  { label: "1 · Lowercasing and normalisation", value: data.normalized },
                  { label: "2 · Tokenisation", value: <TokenList tokens={data.tokens} />, note: `${data.tokens.length} tokens` },
                  {
                    label: "3 · Stop-word removal",
                    value: <TokenList tokens={data.tokens_without_stopwords} />,
                    note: data.stop_words_removed.length ? `removed: ${data.stop_words_removed.join(", ")}` : "nothing removed",
                  },
                  { label: "4 · Stemming (Porter)", value: <TokenList tokens={data.stemmed_tokens} tone="teal" /> },
                  { label: "5 · Lemmatisation (WordNet)", value: <TokenList tokens={data.lemmatized_tokens} tone="teal" /> },
                  { label: "Index terms used for search", value: <TokenList tokens={data.index_terms} tone="teal" />, note: `form: ${data.index_form}` },
                ]}
              />
              {aligned && data.stemmed_tokens.length > 0 && (
                <div>
                  <SectionTitle>Token by token</SectionTitle>
                  <Table caption="Each token through stemming and lemmatisation">
                    <thead>
                      <tr>
                        <Th>Token</Th>
                        <Th>Stem</Th>
                        <Th>Lemma</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.tokens_without_stopwords.map((token, i) => (
                        <tr key={`${token}-${i}`}>
                          <Td mono>{token}</Td>
                          <Td mono>{data.stemmed_tokens[i]}</Td>
                          <Td mono>{data.lemmatized_tokens[i]}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              )}
            </CardBody>
          </Card>
        )}
      </div>
    </div>
  );
}
