"use client";

import Link from "next/link";
import { AuthGate } from "@/components/auth-gate";
import { StatusBadge } from "@/components/status-badge";
import { UploadZone } from "@/components/upload-zone";
import { listDocuments, type DocumentSummary } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import { useResource } from "@/lib/use-resource";

const POLL_MS = 3000;

export default function DocumentsPage() {
  return <AuthGate>{() => <DocumentsView />}</AuthGate>;
}

const isBusy = (docs: DocumentSummary[] | null) =>
  docs?.some((d) => d.status === "queued" || d.status === "processing") ?? false;

function DocumentsView() {
  // Mientras haya documentos en cola o procesando, se refresca el estado.
  const { data: docs, error, setData: setDocs } = useResource(listDocuments, isBusy, POLL_MS);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Documentos</h1>
        <p className="text-sm text-muted-foreground">
          Sube documentos, revisa lo extraído y corrige los campos dudosos.
        </p>
      </div>

      <UploadZone onUploaded={(added) => setDocs((prev) => [...added, ...(prev ?? [])])} />

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {docs === null ? (
        !error && <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : docs.length === 0 ? (
        <p className="rounded-xl border px-4 py-8 text-center text-sm text-muted-foreground">
          Aún no hay documentos. Sube el primero.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Archivo</th>
                <th className="px-4 py-2 font-medium">Tipo</th>
                <th className="px-4 py-2 font-medium">Estado</th>
                <th className="px-4 py-2 text-right font-medium">Tamaño</th>
                <th className="px-4 py-2 text-right font-medium">Subido</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="border-t hover:bg-muted/40">
                  <td className="max-w-xs truncate px-4 py-2.5">
                    <Link href={`/documents/${d.id}`} className="font-medium hover:underline">
                      {d.filename}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">{d.doc_type ?? "—"}</td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="px-4 py-2.5 text-right text-muted-foreground tabular-nums">
                    {formatBytes(d.size_bytes)}
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap text-muted-foreground tabular-nums">
                    {formatDate(d.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
