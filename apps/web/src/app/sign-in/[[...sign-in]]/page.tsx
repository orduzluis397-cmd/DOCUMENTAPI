import { SignIn } from "@clerk/nextjs";
import Link from "next/link";
import { Suspense } from "react";

import { CLERK_ENABLED } from "@/lib/auth-config";

export default function SignInPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-4 px-6 py-12">
      {CLERK_ENABLED ? (
        <Suspense fallback={<p className="text-sm text-muted-foreground">Cargando…</p>}>
          <SignIn signUpUrl="/sign-up" fallbackRedirectUrl="/documents" />
        </Suspense>
      ) : (
        <p className="text-sm text-muted-foreground">
          Clerk no está configurado (falta NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY). En desarrollo usa el{" "}
          <Link href="/login" className="underline">
            acceso de desarrollo
          </Link>
          .
        </p>
      )}
    </main>
  );
}
