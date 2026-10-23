import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <EmptyState title="Page not found" description="That page does not exist in SearchSphere AI.">
      <ButtonLink href="/" variant="primary">
        Back to search
      </ButtonLink>
    </EmptyState>
  );
}
