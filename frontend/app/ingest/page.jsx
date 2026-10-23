import IngestPanel from "@/components/documents/IngestPanel";
import PageHeader from "@/components/ui/PageHeader";

export const metadata = { title: "Document ingestion" };

export default function IngestPage() {
  return (
    <>
      <PageHeader
        title="Document ingestion"
        description="Add your own TXT or PDF documents to the searchable library."
        breadcrumbs={[{ label: "Library" }]}
      />
      <IngestPanel />
    </>
  );
}
