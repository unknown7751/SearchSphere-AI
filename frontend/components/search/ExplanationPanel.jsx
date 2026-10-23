import { Table, Td, Th } from "@/components/ui/Table";
import { formatScore } from "@/lib/formatters";

/**
 * Compact "Why this result?" view built only from the backend's `explanation` object
 * (POST /api/search with explain=true): per-term TF / DF / IDF / TF-IDF and the cosine arithmetic.
 */
export default function ExplanationPanel({ explanation, score }) {
  const { matching_terms: terms = [], dot_product: dot, query_norm: qn, document_norm: dn } = explanation;
  return (
    <div className="space-y-3">
      <Table caption="Matching query terms and their TF-IDF evidence">
        <thead>
          <tr>
            <Th>Term</Th>
            <Th align="right">TF</Th>
            <Th align="right">DF</Th>
            <Th align="right">IDF</Th>
            <Th align="right">TF-IDF (doc)</Th>
            <Th align="right">Query weight</Th>
            <Th align="right">Contribution</Th>
          </tr>
        </thead>
        <tbody>
          {terms.map((t) => (
            <tr key={t.term}>
              <Td>
                <span className="font-medium">{t.word}</span>
                {t.word !== t.term && <span className="ml-1 font-mono text-xs text-mute">({t.term})</span>}
              </Td>
              <Td align="right" mono>{t.tf}</Td>
              <Td align="right" mono>{t.df}</Td>
              <Td align="right" mono>{formatScore(t.idf, 3)}</Td>
              <Td align="right" mono>{formatScore(t.tfidf, 3)}</Td>
              <Td align="right" mono>{formatScore(t.query_weight, 3)}</Td>
              <Td align="right" mono>{formatScore(t.contribution, 3)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="rounded border border-mute-line bg-paper px-3 py-2 font-mono text-xs text-ink-soft">
        cosine = dot(q,d) / (‖q‖ × ‖d‖) = {formatScore(dot, 3)} / ({formatScore(qn, 3)} × {formatScore(dn, 3)}) ={" "}
        <strong className="text-navy-800">{formatScore(score)}</strong>
      </p>
    </div>
  );
}
