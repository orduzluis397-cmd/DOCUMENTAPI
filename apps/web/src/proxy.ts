import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

import { CLERK_ENABLED } from "@/lib/auth-config";

// Next.js 16: "proxy" es el antiguo middleware. Con Clerk activo, las rutas de la app exigen
// sesión (redirige a /sign-in). La autorización real la hace la API con el token.
const isProtected = createRouteMatcher(["/documents(.*)"]);

const withClerk = clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) await auth.protect();
});

export default CLERK_ENABLED ? withClerk : () => NextResponse.next();

export const config = {
  matcher: [
    // Todo menos los archivos internos de Next y los estáticos.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
