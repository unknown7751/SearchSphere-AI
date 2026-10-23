import { useId } from "react";

export const inputClasses =
  "block w-full rounded border border-mute-line bg-white px-3 text-sm text-ink placeholder:text-mute-light focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-teal-600 disabled:bg-paper-dark";

export function Field({ label, hint, error, children, className = "", htmlFor }) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-ink-soft">
        {label}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-mute">{hint}</p>}
      {error && (
        <p className="mt-1 text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextField({ label, hint, error, className = "", inputClassName = "", mono = false, ...props }) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} className={className} htmlFor={id}>
      <input
        id={id}
        aria-invalid={error ? "true" : undefined}
        className={`${inputClasses} h-10 ${mono ? "font-mono" : ""} ${inputClassName}`}
        {...props}
      />
    </Field>
  );
}

export function SelectField({ label, hint, className = "", children, ...props }) {
  const id = useId();
  return (
    <Field label={label} hint={hint} className={className} htmlFor={id}>
      <select id={id} className={`${inputClasses} h-10`} {...props}>
        {children}
      </select>
    </Field>
  );
}

export function TextAreaField({ label, hint, error, className = "", rows = 4, ...props }) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} className={className} htmlFor={id}>
      <textarea id={id} rows={rows} aria-invalid={error ? "true" : undefined} className={`${inputClasses} py-2`} {...props} />
    </Field>
  );
}
