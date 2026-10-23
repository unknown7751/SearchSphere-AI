import { ExternalLink } from "lucide-react";
import { safeHttpUrl } from "@/lib/formatters";

/**
 * Renders an external link only for http(s) URLs. Anything else (javascript:, data:, file:, malformed)
 * is shown as inert text, so untrusted URLs from crawled content can never become executable links.
 */
export default function SafeLink({ href, children, className = "" }) {
  const safe = safeHttpUrl(href);
  const label = children ?? href;
  if (!safe) return <span className={`break-all text-mute ${className}`}>{label}</span>;
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={`inline-flex max-w-full items-center gap-1 break-all text-teal-700 underline-offset-2 hover:underline ${className}`}
    >
      <span className="min-w-0 break-all">{label}</span>
      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
