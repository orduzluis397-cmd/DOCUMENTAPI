"use client";

import { Trash2Icon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { deleteDocument } from "@/lib/api";

/** Borra el documento (archivo y datos extraídos) tras confirmar. Queda constancia en auditoría. */
export function DeleteDocumentButton({
  id,
  filename,
  onDeleted,
  compact = false,
}: {
  id: string;
  filename: string;
  onDeleted: () => void;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    if (
      !window.confirm(
        `¿Borrar "${filename}"? Se eliminan el archivo y los datos extraídos. No se puede deshacer.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteDocument(id);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo borrar.");
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <Button
        variant="destructive"
        size={compact ? "icon-sm" : "sm"}
        disabled={busy}
        onClick={() => void remove()}
        aria-label={`Borrar ${filename}`}
        title="Borrar documento"
      >
        <Trash2Icon aria-hidden />
        {!compact && (busy ? "Borrando…" : "Borrar")}
      </Button>
      {error && (
        <span role="alert" className="text-xs text-destructive">
          {error}
        </span>
      )}
    </span>
  );
}
