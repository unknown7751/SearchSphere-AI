"use client";

import { useEffect } from "react";
import { runSearch } from "@/lib/searchModel";
import { useAsync } from "./useAsync";

/** Tags the view with the request it answers, so callers can tell a stale view from the current one. */
async function runTaggedSearch(args, opts) {
  const view = await runSearch(args, opts);
  return { ...view, request: { query: args.query, mode: args.mode } };
}

/** Runs the search whenever the URL-derived (query, mode, page) change. An empty query stays idle. */
export function useSearch({ query, mode, page }) {
  const search = useAsync(runTaggedSearch);
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
