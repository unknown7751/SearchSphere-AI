/** A formula block in serif type with an optional caption. Content is plain text, never HTML. */
export default function Formula({ children, caption, className = "" }) {
  return (
    <figure className={`rounded border border-mute-line bg-paper px-4 py-3 ${className}`}>
      <div className="overflow-x-auto font-serif text-base italic text-navy-800">{children}</div>
      {caption && <figcaption className="mt-1 text-xs not-italic text-mute">{caption}</figcaption>}
    </figure>
  );
}
