"use client";

/**
 * Puente entre Clerk (hooks de React) y `lib/api.ts` (funciones sueltas): `ClerkTokenBridge`
 * registra aquí `getToken` de `useAuth()` y `api.ts` lo usa en cada petición.
 */
type TokenGetter = () => Promise<string | null>;

let getter: TokenGetter | null = null;

export function setTokenGetter(fn: TokenGetter | null) {
  getter = fn;
}

export async function getAuthToken(): Promise<string | null> {
  return getter ? getter() : null;
}
