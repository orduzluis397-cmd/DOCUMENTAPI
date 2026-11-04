"use client";

import { OrganizationList, OrganizationSwitcher, UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useLayoutEffect, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { CLERK_ENABLED } from "@/lib/auth-config";
import { setTokenGetter } from "@/lib/auth-token";
import { clearSession, useSession } from "@/lib/session";

type Render = () => ReactNode;

/**
 * Exige sesión y pinta la cabecera de la app.
 * - Clerk: sesión iniciada Y organización activa; sin organización no se muestra la app (no se
 *   puede subir nada) y se ofrece elegir o crear una.
 * - Desarrollo: sesión de `/login` con los IDs del seed.
 */
export function AuthGate({ children }: { children: Render }) {
  return CLERK_ENABLED ? <ClerkGate>{children}</ClerkGate> : <DevGate>{children}</DevGate>;
}

function Shell({ right, children }: { right: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-4 px-4">
          <Link href="/documents" className="font-semibold tracking-tight">
            Contable IA
          </Link>
          <div className="flex items-center gap-3 text-sm">{right}</div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-6">{children}</main>
    </div>
  );
}

const Loading = ({ text }: { text: string }) => (
  <p className="p-6 text-sm text-muted-foreground">{text}</p>
);

function ClerkGate({ children }: { children: Render }) {
  const { isLoaded, isSignedIn, orgId, getToken } = useAuth();
  const router = useRouter();

  // El puente del token debe estar listo ANTES de que los hijos pidan datos a la API: los
  // efectos de layout (este) corren antes que los efectos normales de los hijos (las cargas).
  useLayoutEffect(() => {
    if (!isSignedIn) return;
    setTokenGetter(() => getToken());
    return () => setTokenGetter(null);
  }, [isSignedIn, getToken]);

  useEffect(() => {
    if (isLoaded && !isSignedIn) router.replace("/sign-in");
  }, [isLoaded, isSignedIn, router]);

  if (!isLoaded || !isSignedIn) return <Loading text="Cargando sesión…" />;

  return (
    <Shell
      right={
        <>
          <OrganizationSwitcher
            hidePersonal
            afterSelectOrganizationUrl="/documents"
            afterCreateOrganizationUrl="/documents"
          />
          <UserButton />
        </>
      }
    >
      {orgId ? (
        // Al cambiar de organización se vuelve a montar todo (y se vuelven a pedir los datos).
        <Fragment key={orgId}>{children()}</Fragment>
      ) : (
        <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-10 text-center">
          <h1 className="text-xl font-semibold tracking-tight">Elige una organización</h1>
          <p className="text-sm text-muted-foreground">
            Los documentos pertenecen a una organización (tu empresa o la de tu cliente). Elige una
            o crea una nueva para poder subir documentos.
          </p>
          <OrganizationList
            hidePersonal
            afterSelectOrganizationUrl="/documents"
            afterCreateOrganizationUrl="/documents"
          />
        </div>
      )}
    </Shell>
  );
}

function DevGate({ children }: { children: Render }) {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session === null) router.replace("/login");
  }, [session, router]);

  if (!session) return <Loading text="Cargando sesión…" />;

  return (
    <Shell
      right={
        <>
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
        </>
      }
    >
      {children()}
    </Shell>
  );
}
