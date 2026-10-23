"use client";

import { useEffect } from "react";
import { runSearch } from "@/lib/searchModel";
import { useAsync } from "./useAsync";

/** Runs the search whenever the URL-derived (query, mode, page) change. An empty query stays idle. */
export function useSearch({ query, mode, page }) {
  const search = useAsync(runSearch);
  const { run, reset } = search;

  useEffect(() => {
    if (!query) {
      reset();
      return;
    }
    run({ query, mode, page });
  }, [query, mode, page, run, reset]);

  return { ...search, retry: () => run({ query, mode, page }) };
}
