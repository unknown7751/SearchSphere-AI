import { Suspense } from "react";
import DocumentsPageClient from "@/components/documents/DocumentsPageClient";
import { TableSkeleton } from "@/components/ui/States";

export const metadata = { title: "Document explorer" };

export default function DocumentsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={6} />}>
      <DocumentsPageClient />
    </Suspense>
  );
}
