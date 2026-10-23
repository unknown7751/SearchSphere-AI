export default function MetricCard({ label, value, hint, className = "" }) {
  return (
    <div className={`rounded-md border border-mute-line bg-white px-4 py-3 ${className}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-mute">{label}</p>
      <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-navy-800">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-mute">{hint}</p>}
    </div>
  );
}
