"use client";

import { getSession } from "@/lib/session";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type DocumentStatus = "queued" | "processing" | "extracted" | "needs_review" | "failed";

export type DocumentSummary = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  doc_type: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type ExtractedField = {
  id: string;
  extraction_id: string;
  name: string;
  value: JsonValue;
  corrected_value: JsonValue;
  is_doubtful: boolean;
  confidence: number | null;
  page: number | null;
  corrected_by: string | null;
  corrected_at: string | null;
};

export type Extraction = {
  id: string;
  doc_type: string | null;
  method: string;
  model: string | null;
  prompt_version: string | null;
  created_at: string;
};

export type DocumentDetail = DocumentSummary & {
  extraction: Extraction | null;
  fields: ExtractedField[];
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function authHeaders(): Record<string, string> {
  const session = getSession();
  if (!session) throw new ApiError(401, "No hay sesión. Inicia sesión de nuevo.");
  return { "X-User-Id": session.userId, "X-Organization-Id": session.organizationId };
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...init.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `No se pudo conectar con la API (${API_URL}).`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // cuerpo no JSON: se queda statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

export async function listDocuments(): Promise<DocumentSummary[]> {
  return (await request("/documents")).json();
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return (await request(`/documents/${encodeURIComponent(id)}`)).json();
}

export async function getDocumentFile(id: string): Promise<Blob> {
  return (await request(`/documents/${encodeURIComponent(id)}/file`)).blob();
}

export async function uploadDocuments(files: File[]): Promise<DocumentSummary[]> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  return (await request("/documents", { method: "POST", body: form })).json();
}

export async function correctField(id: string, value: JsonValue): Promise<ExtractedField> {
  const res = await request(`/fields/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ corrected_value: value }),
  });
  return res.json();
}
