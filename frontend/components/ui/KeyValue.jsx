export default function KeyValue({ items, className = "" }) {
  return (
    <dl className={`grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5 text-sm ${className}`}>
      {items
        .filter((item) => item && item.value !== undefined && item.value !== null && item.value !== "")
        .map((item) => (
          <div key={item.label} className="contents">
            <dt className="text-mute">{item.label}</dt>
            <dd className="min-w-0 break-words text-ink">{item.value}</dd>
          </div>
        ))}
    </dl>
  );
}
