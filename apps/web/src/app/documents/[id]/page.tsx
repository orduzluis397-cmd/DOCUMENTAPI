import { Suspense } from "react";

import { DocumentDetailView } from "./document-detail";

// El id solo se conoce en la petición: con Cache Components, el acceso al parámetro va dentro
// de Suspense y el resto de la página se prerenderiza como cascarón estático.
export default function DocumentPage() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Cargando…</p>}>
      <DocumentDetailView />
    </Suspense>
  );
}
