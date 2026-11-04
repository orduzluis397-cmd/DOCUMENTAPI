"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { CLERK_ENABLED } from "@/lib/auth-config";
import { DEMO_SESSION, saveSession } from "@/lib/session";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Acceso de DESARROLLO (sin Clerk). Solo guarda los IDs que la API acepta en local con
 * AUTH_PROVIDER=stub; no hay contraseña ni token. Con Clerk configurado redirige a /sign-in.
 */
export default function LoginPage() {
  const router = useRouter();
  useEffect(() => {
    if (CLERK_ENABLED) router.replace("/sign-in");
  }, [router]);
  if (CLERK_ENABLED) return null;
  return <DevLogin />;
}

function DevLogin() {
  const router = useRouter();
  const [organizationId, setOrganizationId] = useState(DEMO_SESSION.organizationId);
  const [userId, setUserId] = useState(DEMO_SESSION.userId);
  const valid = UUID_RE.test(organizationId.trim()) && UUID_RE.test(userId.trim());

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-6 px-6 py-16">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Contable IA</h1>
        <p className="text-sm text-muted-foreground">
          Acceso de desarrollo (sin Clerk). En la demo se entra con Clerk.
        </p>
      </div>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid) return;
          saveSession({ organizationId: organizationId.trim(), userId: userId.trim() });
          router.replace("/documents");
        }}
      >
        <Field label="ID de organización" value={organizationId} onChange={setOrganizationId} />
        <Field label="ID de usuario" value={userId} onChange={setUserId} />
        <Button type="submit" size="lg" disabled={!valid}>
          Entrar
        </Button>
        <p className="text-xs text-muted-foreground">
          Los valores por defecto son los del seed local:{" "}
          <code className="font-mono">uv run python -m app.db.seed</code>
        </p>
      </form>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="h-9 rounded-md border border-input bg-background px-2.5 font-mono text-xs font-normal outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      />
    </label>
  );
}
