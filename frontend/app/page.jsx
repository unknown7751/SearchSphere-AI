import Link from "next/link";
import { BookOpen, FlaskConical, Globe, Upload } from "lucide-react";
import SearchBox from "@/components/search/SearchBox";
import { searchHref } from "@/lib/searchUrl";
import { APP_NAME, APP_TAGLINE } from "@/lib/constants";

const EXAMPLES = [
  { query: "machine learning", mode: "ranked", label: "Ranked" },
  { query: "neural networks", mode: "expanded", label: "With expansion" },
  { query: "network AND (security OR firewall)", mode: "boolean", label: "Boolean" },
  { query: "comput*r", mode: "wildcard", label: "Wildcard" },
];

const SHORTCUTS = [
  { href: "/workbench", icon: FlaskConical, title: "IR Workbench", text: "Step through preprocessing, the inverted index, TF-IDF, cosine similarity, Rocchio and evaluation." },
  { href: "/ingest", icon: Upload, title: "Add documents", text: "Upload TXT or PDF files and search them immediately." },
  { href: "/crawler", icon: Globe, title: "Web crawler", text: "Crawl a public site within strict safety limits and index the pages." },
  { href: "/docs", icon: BookOpen, title: "Documentation", text: "Architecture, algorithms and viva questions." },
];

export default function HomePage() {
  return (
    <div className="mx-auto max-w-3xl pt-6 sm:pt-12">
      <h1 className="text-3xl font-semibold tracking-tight text-navy-800 sm:text-4xl">{APP_NAME}</h1>
      <p className="mt-3 text-base text-ink-soft">{APP_TAGLINE}</p>

      <div className="mt-8 rounded-md border border-mute-line bg-white p-4 sm:p-5">
        <SearchBox autoFocus />
      </div>

      <section aria-labelledby="examples" className="mt-6">
        <h2 id="examples" className="text-xs font-semibold uppercase tracking-wide text-mute">
          Try an example
        </h2>
        <ul className="mt-2 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <li key={ex.query}>
              <Link
                href={searchHref(ex.query, ex.mode)}
                className="inline-flex items-center gap-2 rounded border border-mute-line bg-white px-3 py-1.5 text-sm hover:border-teal-600 hover:text-teal-700"
              >
                <span className="font-mono text-xs">{ex.query}</span>
                <span className="text-xs text-mute">{ex.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="tools" className="mt-10">
        <h2 id="tools" className="text-xs font-semibold uppercase tracking-wide text-mute">
          Laboratory tools
        </h2>
        <ul className="mt-2 grid gap-3 sm:grid-cols-2">
          {SHORTCUTS.map(({ href, icon: Icon, title, text }) => (
            <li key={href}>
              <Link href={href} className="block h-full rounded-md border border-mute-line bg-white p-4 hover:border-teal-600">
                <span className="flex items-center gap-2 font-medium text-navy-700">
                  <Icon className="h-4 w-4 text-teal-600" aria-hidden="true" />
                  {title}
                </span>
                <span className="mt-1 block text-sm text-mute">{text}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
