import { ArrowDown } from "lucide-react";

function Box({ title, children, tone = "plain", className = "" }) {
  const tones = {
    plain: "border-mute-line bg-white",
    navy: "border-navy-700 bg-navy-800 text-white",
    teal: "border-teal-200 bg-teal-50",
  };
  return (
    <div className={`rounded border px-3 py-2 text-sm ${tones[tone]} ${className}`}>
      <p className={`font-semibold ${tone === "navy" ? "text-white" : "text-navy-800"}`}>{title}</p>
      {children && <p className={`mt-0.5 text-xs ${tone === "navy" ? "text-navy-100" : "text-mute"}`}>{children}</p>}
    </div>
  );
}

function Arrow() {
  return <ArrowDown className="mx-auto my-1 h-4 w-4 text-mute-light" aria-hidden="true" />;
}

/** CSS-only architecture diagram: user → Next.js → FastAPI (modules) → SQLite → index → retrieval. */
export default function ArchitectureDiagram() {
  return (
    <figure className="my-4 rounded-md border border-mute-line bg-paper p-4" aria-label="System architecture diagram">
      <div className="mx-auto max-w-2xl">
        <Box title="User" tone="plain">Browser</Box>
        <Arrow />
        <Box title="Next.js frontend" tone="navy">Collects input, calls the API, visualises responses. No IR logic.</Box>
        <Arrow />
        <Box title="FastAPI backend" tone="navy">/api/* · validation · structured errors</Box>
        <div className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Box title="Search" tone="teal">Boolean · wildcard · TF-IDF</Box>
          <Box title="IR Workbench" tone="teal">Intermediate calculations</Box>
          <Box title="Documents" tone="teal">List · detail · upload</Box>
          <Box title="Evaluation" tone="teal">P · R · F1 · AP · MAP</Box>
          <Box title="Crawler" tone="teal">SSRF-safe · robots.txt</Box>
        </div>
        <Arrow />
        <Box title="SQLite" tone="plain">documents · evaluation queries · crawl jobs and results</Box>
        <Arrow />
        <Box title="In-memory inverted index" tone="plain">Rebuilt from SQLite at start-up and kept in sync on every change</Box>
        <Arrow />
        <Box title="TF-IDF / retrieval" tone="plain">Postings merge · weights · cosine ranking · Rocchio</Box>
      </div>
      <figcaption className="mt-3 text-center text-xs text-mute">The backend is the source of truth for every score.</figcaption>
    </figure>
  );
}
