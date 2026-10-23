"use client";

import { useState } from "react";
import { CheckCircle2, Globe, Play, ShieldAlert, ShieldCheck } from "lucide-react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { ErrorState } from "@/components/ui/States";
import { startCrawler, validateCrawlUrl } from "@/lib/api";
import { CRAWL_LIMITS } from "@/lib/constants";

const SAFETY_RULES = [
  "HTTP / HTTPS only",
  "Same-host crawling",
  "robots.txt respected",
  "Private / internal destinations blocked",
  "Bounded: page, depth, size and time limits",
];

export function SafetyPanel() {
  return (
    <Card>
      <CardHeader title="Crawler safety design" icon={ShieldCheck} description="Enforced by the backend; the UI cannot switch these off." />
      <CardBody>
        <ul className="space-y-1.5 text-sm">
          {SAFETY_RULES.map((rule) => (
            <li key={rule} className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" aria-hidden="true" />
              {rule}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-mute">
          Hosts are resolved and every address must be public (SSRF protection); redirects are re-validated hop by hop; the crawler
          never sends credentials or cookies.
        </p>
      </CardBody>
    </Card>
  );
}

function ValidationResult({ result }) {
  const ok = result.allowed;
  const tone = ok ? "green" : result.status === "blocked_by_security" ? "amber" : "red";
  const label = ok ? "Valid" : result.status === "blocked_by_security" ? "Blocked" : "Invalid";
  const Icon = ok ? ShieldCheck : ShieldAlert;
  return (
    <div className="rounded border border-mute-line bg-paper px-3 py-2 text-sm" role="status">
      <div className="flex flex-wrap items-center gap-2">
        <Icon className={`h-4 w-4 ${ok ? "text-green-700" : "text-amber-700"}`} aria-hidden="true" />
        <Badge tone={tone}>{label}</Badge>
        {result.reason && <span className="font-mono text-xs text-mute">{result.reason}</span>}
      </div>
      {result.message && <p className="mt-1 text-ink-soft">{result.message}</p>}
      {ok && result.normalized_url && (
        <p className="mt-1 break-all text-xs text-mute">
          Normalised URL: <span className="font-mono">{result.normalized_url}</span>
        </p>
      )}
    </div>
  );
}

/** Seed URL + bounds. `onStarted(job)` receives the queued job returned by POST /api/crawler/start. */
export default function CrawlForm({ onStarted, disabled }) {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(10);
  const [maxDepth, setMaxDepth] = useState(2);
  const [validation, setValidation] = useState(null);
  const [validating, setValidating] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);

  const pages = Number(maxPages);
  const depth = Number(maxDepth);
  const pagesError = !Number.isInteger(pages) || pages < 1 || pages > CRAWL_LIMITS.maxPages ? `Enter a whole number from 1 to ${CRAWL_LIMITS.maxPages}.` : null;
  const depthError = !Number.isInteger(depth) || depth < 0 || depth > CRAWL_LIMITS.maxDepth ? `Enter a whole number from 0 to ${CRAWL_LIMITS.maxDepth}.` : null;
  const canSubmit = url.trim() && !pagesError && !depthError;

  const onUrlChange = (e) => {
    setUrl(e.target.value);
    setValidation(null);
    setError(null);
  };

  const validate = async () => {
    setValidating(true);
    setError(null);
    try {
      setValidation(await validateCrawlUrl(url.trim()));
    } catch (err) {
      setValidation(null);
      setError(err);
    } finally {
      setValidating(false);
    }
  };

  const start = async (event) => {
    event.preventDefault();
    if (!canSubmit) return;
    setStarting(true);
    setError(null);
    try {
      const job = await startCrawler({ url: url.trim(), maxPages: pages, maxDepth: depth });
      onStarted(job);
    } catch (err) {
      setError(err);
    } finally {
      setStarting(false);
    }
  };

  return (
    <Card>
      <CardHeader title="Start a crawl" icon={Globe} description="Crawled pages are extracted, indexed and immediately searchable." />
      <CardBody>
        <form onSubmit={start} className="space-y-4" noValidate>
          <TextField
            label="Seed URL"
            type="url"
            inputMode="url"
            value={url}
            onChange={onUrlChange}
            placeholder="https://example.com/"
            maxLength={2048}
            mono
            autoComplete="off"
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField
              label="Max pages"
              type="number"
              min={1}
              max={CRAWL_LIMITS.maxPages}
              value={maxPages}
              onChange={(e) => setMaxPages(e.target.value)}
              error={pagesError}
              hint={`1 to ${CRAWL_LIMITS.maxPages}`}
            />
            <TextField
              label="Max depth"
              type="number"
              min={0}
              max={CRAWL_LIMITS.maxDepth}
              value={maxDepth}
              onChange={(e) => setMaxDepth(e.target.value)}
              error={depthError}
              hint={`Link hops from the seed, 0 to ${CRAWL_LIMITS.maxDepth}`}
            />
          </div>

          {validation && <ValidationResult result={validation} />}
          {error && <ErrorState error={error} />}

          <div className="flex flex-wrap gap-2">
            <Button onClick={validate} loading={validating} disabled={!url.trim()}>
              Validate URL
            </Button>
            <Button type="submit" variant="primary" loading={starting} disabled={!canSubmit || disabled}>
              <Play className="h-4 w-4" aria-hidden="true" />
              Start crawl
            </Button>
          </div>
          {disabled && <p className="text-xs text-mute">A crawl is already queued or running. Only one crawl can be active at a time.</p>}
        </form>
      </CardBody>
    </Card>
  );
}
