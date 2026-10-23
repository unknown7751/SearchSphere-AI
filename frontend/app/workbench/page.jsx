import { Suspense } from "react";
import { Spinner } from "@/components/ui/States";
import WorkbenchPageClient from "@/components/workbench/WorkbenchPageClient";

export const metadata = { title: "IR Workbench" };

export default function WorkbenchPage() {
  return (
    <Suspense fallback={<Spinner label="Loading workbench" />}>
      <WorkbenchPageClient />
    </Suspense>
  );
}
