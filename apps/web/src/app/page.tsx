import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { CLERK_ENABLED } from "@/lib/auth-config";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Contable IA</h1>
      <p className="text-muted-foreground">
        Document AI contable para pymes colombianas: extracción, validación, consulta normativa y
        conciliación con aprobación humana.
      </p>
      <p className="text-sm text-muted-foreground">
        Esta es una demo técnica: los documentos se procesan en servicios gratuitos fuera de
        Colombia. No subas documentos con datos sensibles; puedes borrar lo que subas.
      </p>
      <div className="flex gap-2">
        <Link href="/documents" className={buttonVariants()}>
          Ir a documentos
        </Link>
        <Link
          href={CLERK_ENABLED ? "/sign-in" : "/login"}
          className={buttonVariants({ variant: "outline" })}
        >
          Iniciar sesión
        </Link>
        {CLERK_ENABLED && (
          <Link href="/sign-up" className={buttonVariants({ variant: "ghost" })}>
            Crear cuenta
          </Link>
        )}
      </div>
    </main>
  );
}
