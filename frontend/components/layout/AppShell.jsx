"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { Menu, Search, X } from "lucide-react";
import { APP_NAME, NAV_ITEMS } from "@/lib/constants";
import BackendStatus from "./BackendStatus";

function isActive(item, pathname) {
  return item.match.some((m) => (m === "/" ? pathname === "/" : pathname === m || pathname.startsWith(`${m}/`)));
}

export default function AppShell({ children }) {
  const pathname = usePathname() || "/";
  // The menu is open only for the page it was opened on, so navigating closes it without an effect.
  const [openAt, setOpenAt] = useState(null);
  const open = openAt === pathname;
  const toggleRef = useRef(null);
  const setOpen = (updater) => setOpenAt((prev) => ((typeof updater === "function" ? updater(prev === pathname) : updater) ? pathname : null));

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header
        className="sticky top-0 z-40 border-b border-navy-900 bg-navy-800 text-white"
        onKeyDown={(event) => {
          if (event.key === "Escape" && open) {
            setOpenAt(null);
            toggleRef.current?.focus();
          }
        }}
      >
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
          <Link href="/" className="flex shrink-0 items-center gap-2 font-semibold tracking-tight">
            <span className="flex h-7 w-7 items-center justify-center rounded bg-teal-600" aria-hidden="true">
              <Search className="h-4 w-4" />
            </span>
            {APP_NAME}
          </Link>

          <nav aria-label="Primary" className="ml-4 hidden flex-1 items-center gap-1 lg:flex">
            {NAV_ITEMS.map((item) => {
              const active = isActive(item, pathname);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded px-3 py-1.5 text-sm transition-colors ${
                    active ? "bg-navy-600 text-white" : "text-navy-100 hover:bg-navy-700 hover:text-white"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <BackendStatus />
            <button
              ref={toggleRef}
              type="button"
              className="rounded p-2 text-navy-100 hover:bg-navy-700 lg:hidden"
              aria-expanded={open}
              aria-controls="mobile-nav"
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
              <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
            </button>
          </div>
        </div>

        {open && (
          <nav id="mobile-nav" aria-label="Primary mobile" className="border-t border-navy-700 bg-navy-800 px-4 py-2 lg:hidden">
            <ul className="grid gap-1">
              {NAV_ITEMS.map((item) => {
                const active = isActive(item, pathname);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={`block rounded px-3 py-2 text-sm ${active ? "bg-navy-600 text-white" : "text-navy-100 hover:bg-navy-700"}`}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 focus:outline-none">
        {children}
      </main>

      <footer className="border-t border-mute-line bg-paper-dark">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-3 text-xs text-mute">
          <span>{APP_NAME} · Information Retrieval laboratory · TF-IDF, cosine similarity, Rocchio, evaluation, bounded web crawler</span>
          <span>The backend is the source of truth for every score shown.</span>
        </div>
      </footer>
    </div>
  );
}
