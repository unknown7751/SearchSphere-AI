/** Responsive table primitives: the wrapper scrolls horizontally on small screens. */
export function Table({ children, caption, className = "" }) {
  return (
    <div className={`overflow-x-auto ${className}`} tabIndex={0} role="region" aria-label={caption}>
      <table className="w-full min-w-max border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}

export function Th({ children, align = "left", className = "" }) {
  return (
    <th
      scope="col"
      className={`whitespace-nowrap border-b border-mute-line bg-paper px-3 py-2 text-xs font-semibold uppercase tracking-wide text-mute ${
        align === "right" ? "text-right" : "text-left"
      } ${className}`}
    >
      {children}
    </th>
  );
}

export function Td({ children, align = "left", mono = false, className = "", ...props }) {
  return (
    <td
      className={`border-b border-mute-line/70 px-3 py-2 align-top ${align === "right" ? "text-right" : "text-left"} ${
        mono ? "font-mono tabular-nums" : ""
      } ${className}`}
      {...props}
    >
      {children}
    </td>
  );
}
