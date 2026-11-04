"use client";

import { useEffect, useState } from "react";

import { getDocumentFile } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "ready"; url: string; type: string; text?: string }
  | { kind: "error"; message: string };

/**
 * Visor del archivo original. Se descarga con las cabeceras de sesión (no se puede con un
 * `src` directo) y se muestra con el visor PDF nativo del navegador, como imagen o como XML.
 */
export function DocumentViewer({ documentId, filename }: { documentId: string; filename: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    getDocumentFile(documentId)
      .then(async (blob) => {
        if (cancelled) return;
        if (blob.type.includes("xml")) {
          setState({ kind: "ready", url: "", type: blob.type, text: await blob.text() });
          return;
        }
        url = URL.createObjectURL(blob);
        setState({ kind: "ready", url, type: blob.type });
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setState({
            kind: "error",
            message: e instanceof Error ? e.message : "No se pudo cargar el archivo.",
          });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [documentId]);

  if (state.kind === "loading") {
    return <ViewerFrame>Cargando documento…</ViewerFrame>;
  }
  if (state.kind === "error") {
    return <ViewerFrame>{state.message}</ViewerFrame>;
  }
  if (state.text !== undefined) {
    return (
      <pre className="h-full overflow-auto rounded-xl border bg-muted p-4 font-mono text-xs leading-relaxed">
        {state.text}
      </pre>
    );
  }
  if (state.type.startsWith("image/") && state.type !== "image/tiff") {
    return (
      <div className="h-full overflow-auto rounded-xl border bg-muted p-2">
        {/* eslint-disable-next-line @next/next/no-img-element -- blob local, sin optimizador */}
        <img src={state.url} alt={filename} className="mx-auto max-w-full" />
      </div>
    );
  }
  return (
    <iframe src={state.url} title={filename} className="h-full w-full rounded-xl border bg-muted" />
  );
}

function ViewerFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center rounded-xl border bg-muted p-6 text-sm text-muted-foreground">
      {children}
    </div>
  );
}
