import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Contable IA</h1>
      <p className="text-muted-foreground">
        Document AI contable para pymes colombianas: extracción, validación, consulta normativa y
        conciliación con aprobación humana.
      </p>
      <div>
        <Button disabled>Cargar documentos (próximamente)</Button>
      </div>
    </main>
  );
}
