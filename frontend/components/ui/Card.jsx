export function Card({ as: Tag = "section", className = "", children, ...props }) {
  return (
    <Tag className={`rounded-md border border-mute-line bg-white ${className}`} {...props}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, description, actions, icon: Icon, className = "" }) {
  return (
    <div className={`flex flex-wrap items-start justify-between gap-3 border-b border-mute-line px-4 py-3 ${className}`}>
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-base font-semibold text-navy-800">
          {Icon && <Icon className="h-4 w-4 shrink-0 text-teal-600" aria-hidden="true" />}
          {title}
        </h2>
        {description && <p className="mt-0.5 text-sm text-mute">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ className = "", children }) {
  return <div className={`p-4 ${className}`}>{children}</div>;
}
