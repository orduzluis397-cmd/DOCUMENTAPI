import { cn } from "@/lib/utils";
import type { DocumentStatus } from "@/lib/api";
import { STATUS_LABEL } from "@/lib/format";

const STYLES: Record<DocumentStatus, string> = {
  queued: "bg-muted text-muted-foreground",
  processing: "bg-muted text-foreground",
  extracted: "bg-primary text-primary-foreground",
  needs_review: "bg-warning text-warning-foreground",
  failed: "bg-destructive/10 text-destructive",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const busy = status === "queued" || status === "processing";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        STYLES[status],
      )}
    >
      {busy && <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />}
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
