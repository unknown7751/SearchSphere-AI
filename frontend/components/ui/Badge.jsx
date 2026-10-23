const TONES = {
  neutral: "bg-paper-dark text-ink-soft border-mute-line",
  navy: "bg-navy-50 text-navy-700 border-navy-200",
  teal: "bg-teal-50 text-teal-700 border-teal-200",
  green: "bg-green-50 text-green-800 border-green-200",
  amber: "bg-amber-50 text-amber-800 border-amber-200",
  red: "bg-red-50 text-red-800 border-red-200",
};

export default function Badge({ tone = "neutral", className = "", children, ...props }) {
  return (
    <span
      className={`inline-flex max-w-full items-center rounded border [overflow-wrap:anywhere] px-1.5 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
      {...props}
    >
      {children}
    </span>
  );
}
