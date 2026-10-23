import { Suspense } from "react";
import SearchPageClient from "@/components/search/SearchPageClient";
import { ResultsSkeleton } from "@/components/ui/States";

export const metadata = { title: "Search results" };

export default function SearchPage() {
  return (
    <Suspense fallback={<ResultsSkeleton />}>
      <SearchPageClient />
    </Suspense>
  );
}
