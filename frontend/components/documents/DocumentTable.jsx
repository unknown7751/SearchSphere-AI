import Badge from "@/components/ui/Badge";
import { Table, Td, Th } from "@/components/ui/Table";
import { formatDate, formatNumber, sourceTypeMeta } from "@/lib/formatters";

export default function DocumentTable({ documents, selectedId, onSelect }) {
  return (
    <Table caption="Indexed documents">
      <thead>
        <tr>
          <Th align="right">ID</Th>
          <Th>Title</Th>
          <Th>Source</Th>
          <Th>Category</Th>
          <Th>Created</Th>
          <Th align="right">Words</Th>
        </tr>
      </thead>
      <tbody>
        {documents.map((doc) => {
          const source = sourceTypeMeta(doc.source_type);
          const selected = doc.id === selectedId;
          return (
            <tr key={doc.id} className={selected ? "bg-teal-50" : "hover:bg-paper"}>
              <Td align="right" mono>{doc.id}</Td>
              <Td className="max-w-xs">
                <button
                  type="button"
                  onClick={() => onSelect(doc.id)}
                  aria-current={selected ? "true" : undefined}
                  className="text-left font-medium text-navy-700 hover:text-teal-700 hover:underline"
                >
                  {doc.title}
                </button>
              </Td>
              <Td><Badge tone={source.tone}>{source.label}</Badge></Td>
              <Td className="whitespace-nowrap text-ink-soft">{doc.category}</Td>
              <Td className="whitespace-nowrap text-ink-soft">{formatDate(doc.ingested_at)}</Td>
              <Td align="right" mono>{formatNumber(doc.word_count)}</Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
