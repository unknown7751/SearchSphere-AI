"use client";

import { useId, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import Button from "@/components/ui/Button";
import { inputClasses } from "@/components/ui/Field";
import { ErrorState } from "@/components/ui/States";
import { searchDocuments } from "@/lib/api";
import { parseIdList } from "@/lib/formatters";

/**
 * Choose documents by searching the corpus (ranked search) or by typing IDs.
 * `value` is an array of document IDs; titles of documents added via search are remembered for display.
 */
export default function DocumentPicker({ label, value, onChange, max = 20, hint }) {
  const id = useId();
  const [titles, setTitles] = useState({});
  const [query, setQuery] = useState("");
  const [idText, setIdText] = useState("");
  const [idError, setIdError] = useState(null);
  const [hits, setHits] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);

  const add = (docId, title) => {
    if (value.includes(docId) || value.length >= max) return;
    if (title) setTitles((t) => ({ ...t, [docId]: title }));
    onChange([...value, docId]);
  };
  const remove = (docId) => onChange(value.filter((v) => v !== docId));

  const find = async (event) => {
    event.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const res = await searchDocuments({ query: query.trim(), pageSize: 8 });
      setHits(res.results);
    } catch (err) {
      setError(err);
    } finally {
      setSearching(false);
    }
  };

  const addIds = (event) => {
    event.preventDefault();
    const { ids, error: parseError } = parseIdList(idText);
    setIdError(parseError);
    if (parseError) return;
    const merged = [...value];
    for (const n of ids) if (!merged.includes(n) && merged.length < max) merged.push(n);
    onChange(merged);
    setIdText("");
  };

  return (
    <fieldset className="rounded border border-mute-line p-3">
      <legend className="px-1 text-sm font-medium text-ink-soft">{label}</legend>
      {hint && <p className="mb-2 text-xs text-mute">{hint}</p>}

      <div className="mb-2 flex flex-wrap gap-1.5" aria-live="polite">
        {value.length === 0 && <span className="text-sm text-mute">None selected</span>}
        {value.map((docId) => (
          <span key={docId} className="inline-flex max-w-full items-center gap-1 rounded border border-teal-200 bg-teal-50 py-0.5 pl-2 pr-1 text-xs text-teal-800">
            <span className="font-mono">#{docId}</span>
            {titles[docId] && <span className="truncate">{titles[docId]}</span>}
            <button type="button" onClick={() => remove(docId)} className="rounded p-0.5 hover:bg-teal-100" aria-label={`Remove document ${docId}`}>
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </span>
        ))}
      </div>

      <form onSubmit={find} className="flex gap-2">
        <label htmlFor={`${id}-q`} className="sr-only">
          Search documents to add to {label}
        </label>
        <input
          id={`${id}-q`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search documents to add…"
          className={`${inputClasses} h-9`}
        />
        <Button type="submit" size="sm" loading={searching} disabled={!query.trim()}>
          <Search className="h-4 w-4" aria-hidden="true" />
          Find
        </Button>
      </form>

      {error && <ErrorState className="mt-2" error={error} />}
      {hits && (
        <ul className="mt-2 max-h-48 divide-y divide-mute-line overflow-auto rounded border border-mute-line text-sm">
          {hits.length === 0 && <li className="px-3 py-2 text-mute">No matches.</li>}
          {hits.map((h) => (
            <li key={h.doc_id} className="flex items-center justify-between gap-2 px-3 py-1.5">
              <span className="min-w-0 truncate">
                <span className="mr-2 font-mono text-xs text-mute">#{h.doc_id}</span>
                {h.title}
              </span>
              <Button size="sm" variant="ghost" disabled={value.includes(h.doc_id) || value.length >= max} onClick={() => add(h.doc_id, h.title)}>
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                {value.includes(h.doc_id) ? "Added" : "Add"}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={addIds} className="mt-2 flex gap-2">
        <label htmlFor={`${id}-ids`} className="sr-only">
          Document IDs to add
        </label>
        <input
          id={`${id}-ids`}
          value={idText}
          onChange={(e) => setIdText(e.target.value)}
          placeholder="…or type IDs, e.g. 30, 31"
          aria-invalid={idError ? "true" : undefined}
          className={`${inputClasses} h-9 font-mono`}
        />
        <Button type="submit" size="sm" disabled={!idText.trim()}>
          Add IDs
        </Button>
      </form>
      {idError && (
        <p className="mt-1 text-xs text-red-700" role="alert">
          {idError}
        </p>
      )}
    </fieldset>
  );
}
