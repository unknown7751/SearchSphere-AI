"use client";

import { useEffect, useState } from "react";
import { getCorpusOverview } from "@/lib/api";

/**
 * Distinct document categories (sorted), derived from a bounded walk over the document list (the backend has no
 * category endpoint). Covers the first 500 documents, the same bound the analytics page uses.
 */
export function useDocumentCategories() {
  const [categories, setCategories] = useState([]);
  useEffect(() => {
    const controller = new AbortController();
    getCorpusOverview({ maxPages: 5 }, { signal: controller.signal })
      .then((overview) => setCategories([...new Set(overview.items.map((d) => d.category))].sort()))
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return categories;
}
