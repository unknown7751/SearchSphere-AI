import { ChevronLeft, ChevronRight } from "lucide-react";
import Button from "./Button";

export default function Pagination({ page, totalPages, onChange, disabled = false, className = "" }) {
  if (!totalPages || totalPages <= 1) return null;
  return (
    <nav aria-label="Pagination" className={`flex items-center justify-between gap-3 ${className}`}>
      <Button size="sm" disabled={disabled || page <= 1} onClick={() => onChange(page - 1)}>
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        Previous
      </Button>
      <span className="text-sm text-mute" aria-live="polite">
        Page {page} of {totalPages}
      </span>
      <Button size="sm" disabled={disabled || page >= totalPages} onClick={() => onChange(page + 1)}>
        Next
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </nav>
  );
}
