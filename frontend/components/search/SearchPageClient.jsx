"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import { useSearch } from "@/hooks/useSearch";
import { isValidMode } from "@/lib/searchModel";
import SearchBox from "./SearchBox";
import SearchResults from "./SearchResults";

/** URL is the source of truth: /search?q=machine+learning&mode=ranked&page=2 */
export default function SearchPageClient() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const query = (params.get("q") || "").trim();
  const rawMode = params.get("mode") || "ranked";
  const mode = isValidMode(rawMode) ? rawMode : "ranked";
  const page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);

  const state = useSearch({ query, mode, page });

  const setPage = useCallback(
    (next) => {
      const sp = new URLSearchParams(params.toString());
      sp.set("page", String(next));
      router.push(`${pathname}?${sp.toString()}`);
      window.scrollTo({ top: 0 });
    },
    [params, pathname, router],
  );

  return (
    <>
      <PageHeader title="Search results" breadcrumbs={[{ label: "Search", href: "/" }, { label: "Results" }]} />
      <div className="mb-6">
        {/* key forces the box to adopt a new query/mode when the URL changes (e.g. back button) */}
        <SearchBox key={`${query}|${mode}`} initialQuery={query} initialMode={mode} size="md" />
      </div>
      <SearchResults key={`${query}|${mode}`} query={query} mode={mode} state={state} onPageChange={setPage} onRetry={state.retry} />
    </>
  );
}
