"use client";

import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { acceptConsent, getConsent } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useResource } from "@/lib/use-resource";

/**
 * Antes de la primera carga: el usuario lee y acepta la autorización de uso de documentos
 * (Ley 1581 de 2012). La API guarda la aceptación (fecha y versión del texto) y la exige en
 * cada carga; esto solo evita mostrar la zona de carga sin aceptación.
 */
export function ConsentGate({ children }: { children: ReactNode }) {
  const { data: consent, error, setData } = useResource(getConsent);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [acceptError, setAcceptError] = useState<string | null>(null);

  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    );
  }
  if (!consent) return <p className="text-sm text-muted-foreground">Cargando autorización…</p>;

  if (consent.accepted) {
    return (
      <div className="flex flex-col gap-2">
        {children}
        <p className="text-xs text-muted-foreground">
          Aceptaste la autorización de uso de documentos
          {consent.accepted_at && ` el ${formatDate(consent.accepted_at)}`} (versión{" "}
          <span className="font-mono">{consent.version}</span>).
        </p>
      </div>
    );
  }

  async function accept() {
    if (!consent) return;
    setBusy(true);
    setAcceptError(null);
    try {
      setData(await acceptConsent(consent.version));
    } catch (e) {
      setAcceptError(e instanceof Error ? e.message : "No se pudo guardar la aceptación.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="consent-title" className="flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="consent-title" className="text-base font-semibold">
          Autorización para el uso de documentos
        </h2>
        {consent.is_draft && (
          <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900 dark:text-amber-100">
            BORRADOR · pendiente de revisión legal
          </span>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        Antes de subir tu primer documento debes leer y aceptar esta autorización. Puedes borrar tus
        documentos cuando quieras desde la lista o el detalle.
      </p>
      <div
        tabIndex={0}
        aria-label="Texto de la autorización"
        className="max-h-80 overflow-y-auto rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap"
      >
        {consent.text}
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
        />
        <span>
          Leí la autorización y la acepto. Entiendo que esta es una demo técnica y que no debo subir
          documentos sensibles.
        </span>
      </label>
      <div className="flex items-center gap-3">
        <Button disabled={!checked || busy} onClick={() => void accept()}>
          {busy ? "Guardando…" : "Aceptar y continuar"}
        </Button>
        <span className="text-xs text-muted-foreground">
          Versión <span className="font-mono">{consent.version}</span>
        </span>
      </div>
      {acceptError && (
        <p role="alert" className="text-sm text-destructive">
          {acceptError}
        </p>
      )}
    </section>
  );
}
