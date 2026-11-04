import type { DocumentStatus, JsonValue } from "@/lib/api";

export const STATUS_LABEL: Record<DocumentStatus, string> = {
  queued: "En cola",
  processing: "Procesando",
  extracted: "Extraído",
  needs_review: "Por revisar",
  failed: "Error",
};

export const ACCEPTED_TYPES = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.xml";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const dateFmt = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short" });

export function formatDate(iso: string): string {
  return dateFmt.format(new Date(iso));
}

export function displayValue(value: JsonValue): string {
  if (value === null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

/**
 * Convierte lo que escribió el usuario al tipo JSON del valor original: si el original era
 * número, se guarda número (acepta "1.190.000" y "1190000,50" al estilo colombiano).
 */
export function parseInput(raw: string, original: JsonValue): JsonValue {
  const text = raw.trim();
  if (typeof original === "number") {
    const normalized = text
      .replace(/\s/g, "")
      .replace(/\.(?=\d{3}(\D|$))/g, "")
      .replace(",", ".");
    const n = Number(normalized);
    if (text !== "" && Number.isFinite(n)) return n;
  }
  if (typeof original === "boolean") {
    if (/^(true|sí|si)$/i.test(text)) return true;
    if (/^(false|no)$/i.test(text)) return false;
  }
  if (original !== null && typeof original === "object") {
    try {
      return JSON.parse(text) as JsonValue;
    } catch {
      return text;
    }
  }
  return text;
}
