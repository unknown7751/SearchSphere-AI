import Link from "next/link";
import { Loader2 } from "lucide-react";

const VARIANTS = {
  primary: "bg-teal-600 text-white hover:bg-teal-700 border-teal-600 disabled:bg-teal-600/50 disabled:border-teal-600/50",
  secondary: "bg-white text-ink border-mute-line hover:bg-paper-dark disabled:text-mute-light",
  ghost: "bg-transparent text-ink-soft border-transparent hover:bg-paper-dark disabled:text-mute-light",
  danger: "bg-white text-red-700 border-red-300 hover:bg-red-50 disabled:text-red-300",
};
const SIZES = { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-base" };

export function buttonClasses({ variant = "secondary", size = "md", className = "" } = {}) {
  return `inline-flex items-center justify-center gap-2 rounded border font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`;
}

export default function Button({ variant, size, loading = false, disabled, className, children, type = "button", ...props }) {
  return (
    <button type={type} disabled={disabled || loading} className={buttonClasses({ variant, size, className })} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function ButtonLink({ variant, size, className, href, children, ...props }) {
  return (
    <Link href={href} className={buttonClasses({ variant, size, className })} {...props}>
      {children}
    </Link>
  );
}
