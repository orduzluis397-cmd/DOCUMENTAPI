"use client";

import { UploadIcon } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import { uploadDocuments, type DocumentSummary } from "@/lib/api";
import { ACCEPTED_TYPES } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Carga múltiple: arrastrar y soltar o seleccionar. La API valida tipo real y tamaño. */
export function UploadZone({ onUploaded }: { onUploaded: (docs: DocumentSummary[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(list: FileList | null) {
    const files = list ? Array.from(list) : [];
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      onUploaded(await uploadDocuments(files));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron subir los archivos.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    void send(e.dataTransfer.files);
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-ring bg-muted" : "border-border",
        )}
      >
        <UploadIcon className="size-6 text-muted-foreground" aria-hidden />
        <div className="text-sm">
          <p className="font-medium">Arrastra facturas, RUT, extractos o cuentas de cobro</p>
          <p className="text-muted-foreground">
            PDF, imagen (PNG, JPEG, TIFF) o XML DIAN · hasta 20 MB c/u
          </p>
        </div>
        <Button size="sm" disabled={busy} onClick={() => inputRef.current?.click()}>
          {busy ? "Subiendo…" : "Seleccionar archivos"}
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_TYPES}
          className="sr-only"
          aria-label="Seleccionar archivos"
          onChange={(e) => void send(e.target.files)}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
