import { TriangleAlertIcon } from "lucide-react";

/** Aviso fijo en todas las páginas de la demo pública (CR-005). */
export function DemoBanner() {
  return (
    <div
      role="note"
      className="flex items-center justify-center gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-sm font-medium text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
    >
      <TriangleAlertIcon className="size-4 shrink-0" aria-hidden />
      <span>Demo técnica — no subas documentos sensibles.</span>
    </div>
  );
}
