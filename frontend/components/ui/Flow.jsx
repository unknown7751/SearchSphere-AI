import { ArrowDown } from "lucide-react";

/**
 * Vertical pipeline: each step is a labelled box, with an arrow between boxes.
 * steps: [{ label, value (node), note? }]
 */
export default function Flow({ steps, className = "" }) {
  return (
    <ol className={`space-y-1 ${className}`}>
      {steps.map((step, i) => (
        <li key={step.label}>
          <div className="rounded border border-mute-line bg-white px-3 py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-teal-700">{step.label}</span>
              {step.note && <span className="text-xs text-mute">{step.note}</span>}
            </div>
            <div className="mt-1 break-words font-mono text-sm text-ink">{step.value}</div>
          </div>
          {i < steps.length - 1 && <ArrowDown className="mx-auto my-0.5 h-4 w-4 text-mute-light" aria-hidden="true" />}
        </li>
      ))}
    </ol>
  );
}

/** Row of token chips (monospace). Empty list renders an em dash. */
export function TokenList({ tokens, tone = "neutral", emptyLabel = "—" }) {
  if (!tokens || tokens.length === 0) return <span className="text-mute">{emptyLabel}</span>;
  const toneClass =
    tone === "removed"
      ? "bg-red-50 text-red-800 border-red-200 line-through"
      : tone === "teal"
        ? "bg-teal-50 text-teal-800 border-teal-200"
        : "bg-paper-dark text-ink border-mute-line";
  return (
    <span className="flex flex-wrap gap-1">
      {tokens.map((t, i) => (
        <span key={`${t}-${i}`} className={`rounded border px-1.5 py-0.5 font-mono text-xs ${toneClass}`}>
          {t}
        </span>
      ))}
    </span>
  );
}
