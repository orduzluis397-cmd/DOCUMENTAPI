"use client";

import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback } from "react";

import { AuthGate } from "@/components/auth-gate";
import { DocumentViewer } from "@/components/document-viewer";
import { FieldList } from "@/components/field-list";
import { StatusBadge } from "@/components/status-badge";
import { getDocument, type DocumentDetail, type ExtractedField } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useResource } from "@/lib/use-resource";

export function DocumentDetailView() {
  const { id } = useParams<{ id: string }>();
  return <AuthGate>{() => <Detail key={id} id={id} />}</AuthGate>;
}

const isBusy = (doc: DocumentDetail | null) =>
  doc?.status === "queued" || doc?.status === "processing";

function Detail({ id }: { id: string }) {
  const fetcher = useCallback(() => getDocument(id), [id]);
  const { data: doc, error, setData: setDoc } = useResource(fetcher, isBusy);
  const busy = isBusy(doc);

  function onFieldChange(updated: ExtractedField) {
    setDoc((prev) =>
      prev
        ? { ...prev, fields: prev.fields.map((f) => (f.id === updated.id ? updated : f)) }
        : prev,
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4">
      <Link
        href="/documents"
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" aria-hidden /> Documentos
      </Link>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {doc && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold tracking-tight">{doc.filename}</h1>
              <p className="text-xs text-muted-foreground">
                Subido {formatDate(doc.created_at)}
                {doc.doc_type && ` · ${doc.doc_type}`}
                {doc.extraction && ` · método ${doc.extraction.method}`}
              </p>
            </div>
            <StatusBadge status={doc.status} />
          </div>

          <div className="grid flex-1 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <section aria-label="Documento original" className="h-[70vh] lg:h-[calc(100vh-12rem)]">
              <DocumentViewer documentId={doc.id} filename={doc.filename} />
            </section>
            <section
              aria-label="Campos extraídos"
              className="lg:h-[calc(100vh-12rem)] lg:overflow-y-auto"
            >
              {doc.fields.length > 0 ? (
                <FieldList fields={doc.fields} onChange={onFieldChange} />
              ) : (
                <p className="rounded-xl border px-4 py-8 text-center text-sm text-muted-foreground">
                  {busy
                    ? "El documento está en proceso; los campos aparecerán aquí."
                    : doc.status === "failed"
                      ? (doc.error ?? "La extracción falló.")
                      : "Sin campos extraídos."}
                </p>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
