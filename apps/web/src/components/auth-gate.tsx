"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { clearSession, useSession, type DevSession } from "@/lib/session";

/** Exige sesión (placeholder de desarrollo) y pinta la cabecera de la app. */
export function AuthGate({ children }: { children: (session: DevSession) => ReactNode }) {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session === null) router.replace("/login");
  }, [session, router]);

  if (!session) {
    return <p className="p-6 text-sm text-muted-foreground">Cargando sesión…</p>;
  }

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-4 px-4">
          <Link href="/documents" className="font-semibold tracking-tight">
            Contable IA
          </Link>
          <div className="flex items-center gap-3 text-sm">
            <span
              className="hidden font-mono text-xs text-muted-foreground sm:inline"
              title="Organización (sesión de desarrollo)"
            >
              org {session.organizationId.slice(0, 8)}…
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                clearSession();
                router.replace("/login");
              }}
            >
              Salir
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-6">
        {children(session)}
      </main>
    </div>
  );
}
