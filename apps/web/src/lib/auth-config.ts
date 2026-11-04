/**
 * Modo de autenticación de la web.
 *
 * - Con `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (demo en Vercel): Clerk con Organizations; la web
 *   manda `Authorization: Bearer <token de sesión>` a la API.
 * - Sin ella (desarrollo local): sesión de desarrollo con los IDs del seed (`/login`), que la
 *   API solo acepta con `AUTH_PROVIDER=stub` en `APP_ENV=local|test`.
 */
export const CLERK_ENABLED = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
