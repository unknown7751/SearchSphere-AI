/** Builds the shareable search URL: /search?q=...&mode=... (page is reset to 1 on a new search). */
export function searchHref(query, mode) {
  const params = new URLSearchParams({ q: query.trim() });
  if (mode && mode !== "ranked") params.set("mode", mode);
  return `/search?${params.toString()}`;
}
