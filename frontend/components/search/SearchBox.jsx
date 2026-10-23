"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import Button from "@/components/ui/Button";
import { inputClasses } from "@/components/ui/Field";
import { SEARCH_MODES } from "@/lib/constants";
import { searchHref } from "@/lib/searchUrl";

export default function SearchBox({ initialQuery = "", initialMode = "ranked", autoFocus = false, size = "lg" }) {
  const router = useRouter();
  const id = useId();
  const [query, setQuery] = useState(initialQuery);
  const [mode, setMode] = useState(SEARCH_MODES.some((m) => m.value === initialMode) ? initialMode : "ranked");
  const active = SEARCH_MODES.find((m) => m.value === mode) || SEARCH_MODES[0];

  const submit = (event) => {
    event.preventDefault();
    if (!query.trim()) return;
    router.push(searchHref(query, mode));
  };

  return (
    <form onSubmit={submit} role="search" aria-label="Search documents">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <label htmlFor={`${id}-q`} className="sr-only">
            Search query
          </label>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-mute-light" aria-hidden="true" />
          <input
            id={`${id}-q`}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={active.placeholder}
            maxLength={500}
            autoFocus={autoFocus}
            autoComplete="off"
            className={`${inputClasses} pl-10 ${size === "lg" ? "h-12 text-base" : "h-10"}`}
          />
        </div>
        <Button type="submit" variant="primary" size={size === "lg" ? "lg" : "md"} disabled={!query.trim()}>
          Search
        </Button>
      </div>

      <fieldset className="mt-3">
        <legend className="sr-only">Search mode</legend>
        <div className="flex flex-wrap gap-2">
          {SEARCH_MODES.map((m) => (
            <label
              key={m.value}
              className={`cursor-pointer rounded border px-3 py-1.5 text-sm transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-teal-600 ${
                mode === m.value ? "border-teal-600 bg-teal-50 text-teal-800" : "border-mute-line bg-white text-ink-soft hover:bg-paper-dark"
              }`}
            >
              <input
                type="radio"
                name={`${id}-mode`}
                value={m.value}
                checked={mode === m.value}
                onChange={() => setMode(m.value)}
                className="sr-only"
              />
              {m.label}
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-mute">{active.hint}</p>
      </fieldset>
    </form>
  );
}
