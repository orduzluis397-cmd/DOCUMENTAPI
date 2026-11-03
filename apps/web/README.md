# contable-ia-web

Interfaz web de Contable IA: Next.js (App Router, TypeScript estricto), Tailwind CSS v4 y shadcn/ui.

```bash
pnpm install
pnpm dev          # http://localhost:3000 (API en NEXT_PUBLIC_API_URL, por defecto :8000)
pnpm lint         # ESLint
pnpm typecheck    # tsc --noEmit
pnpm format:check # Prettier
pnpm build
```

## Páginas

- `/login`: **placeholder** de desarrollo. Guarda en `localStorage` los IDs de organización y
  usuario (por defecto, los del seed `uv run python -m app.db.seed`) que la API acepta como
  cabeceras `X-Organization-Id` / `X-User-Id` solo en local. PENDIENTE: Clerk o Auth.js.
- `/documents`: carga múltiple (arrastrar o seleccionar) y lista con estado (se refresca sola
  mientras hay documentos en cola o procesando).
- `/documents/[id]`: documento original a la izquierda (visor PDF del navegador, imagen o XML) y
  campos extraídos a la derecha; los dudosos van primero, resaltados, y todos son editables
  (cada corrección escribe `audit_events` en la API).

Agregar componentes de shadcn/ui: `pnpm dlx shadcn@latest add <componente>`.
