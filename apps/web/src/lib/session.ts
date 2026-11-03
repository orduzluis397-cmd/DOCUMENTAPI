"use client";

/**
 * Sesión de DESARROLLO (placeholder de login).
 *
 * PENDIENTE: reemplazar por Clerk o Auth.js. Mientras tanto la "sesión" son los IDs de
 * usuario y organización guardados en localStorage, que la API acepta como cabeceras
 * `X-User-Id` / `X-Organization-Id` solo en APP_ENV=local|test (apps/api/app/auth.py).
 */
import { useSyncExternalStore } from "react";

export type DevSession = { userId: string; organizationId: string };

const KEY = "contable-ia.dev-session";
const listeners = new Set<() => void>();

// IDs del seed de desarrollo (apps/api/app/db/seed.py).
export const DEMO_SESSION: DevSession = {
  organizationId: "00000000-0000-4000-8000-000000000001",
  userId: "00000000-0000-4000-8000-000000000101",
};

let cachedRaw: string | null | undefined;
let cachedSession: DevSession | null = null;

function read(): DevSession | null {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    raw = null;
  }
  // Misma referencia mientras no cambie el valor (requisito de useSyncExternalStore).
  if (raw === cachedRaw) return cachedSession;
  cachedRaw = raw;
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    cachedSession =
      parsed &&
      typeof parsed === "object" &&
      "userId" in parsed &&
      "organizationId" in parsed &&
      typeof parsed.userId === "string" &&
      typeof parsed.organizationId === "string"
        ? { userId: parsed.userId, organizationId: parsed.organizationId }
        : null;
  } catch {
    cachedSession = null;
  }
  return cachedSession;
}

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function getSession(): DevSession | null {
  return typeof window === "undefined" ? null : read();
}

export function saveSession(session: DevSession) {
  window.localStorage.setItem(KEY, JSON.stringify(session));
  emit();
}

export function clearSession() {
  window.localStorage.removeItem(KEY);
  emit();
}

/** `undefined` mientras no se ha leído en el cliente; `null` si no hay sesión. */
export function useSession(): DevSession | null | undefined {
  return useSyncExternalStore(subscribe, read, () => undefined);
}
