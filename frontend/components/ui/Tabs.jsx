"use client";

import { useRef, useState } from "react";

/** Accessible tab list (roving focus with arrow keys / Home / End). Panels are rendered by the caller. */
export default function Tabs({ tabs, value, onChange, label, idPrefix = "tab" }) {
  const refs = useRef({});

  const onKeyDown = (event, index) => {
    let next = null;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  };

  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-mute-line">
      {tabs.map((tab, index) => {
        const selected = tab.id === value;
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            role="tab"
            type="button"
            id={`${idPrefix}-${tab.id}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => onKeyDown(e, index)}
            className={`-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-600 ${
              selected ? "border-teal-600 text-teal-700" : "border-transparent text-mute hover:text-ink"
            }`}
          >
            {Icon && <Icon className="h-4 w-4" aria-hidden="true" />}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * A panel is mounted the first time its tab is opened and then only hidden, so what the user typed and
 * computed in a tab survives switching to another tab and back (and unvisited tabs cost no requests).
 */
export function TabPanel({ id, active, idPrefix = "tab", children }) {
  const [visited, setVisited] = useState(active);
  if (active && !visited) setVisited(true);
  if (!visited) return null;
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-${id}`}
      hidden={!active}
      tabIndex={0}
      className="pt-4 focus-visible:outline-none"
    >
      {children}
    </div>
  );
}
