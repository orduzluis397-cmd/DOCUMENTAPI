# Contable IA

**English** · [Español](README.es.md)

> **Work in progress.** The development environment is ready; no product features, results or
> metrics exist yet. This README will be completed at launch (phase 5).

Contable IA is a Spanish-language accounting Document AI web app for Colombian small businesses
(pymes). It receives a company's accounting documents (DIAN electronic invoices, RUT tax
registrations, cuentas de cobro, contracts and bank statements), extracts and validates their data,
detects anomalies, answers tax questions with citations and reconciles invoices against bank
statements **with human approval**.

A **quality and governance layer** (evals, traces, aligned LLM judges, policies, audit trail, cost
tracking) is built in phase 1 and grows with every later phase.

## Guiding use case

Everything is designed and tested against one scenario. Laura, an independent accountant, keeps the
books of 8 small businesses. One of them, a hardware store, has about 130 purchases a month and
closing the month takes her 2 days. The planned flow:

1. Bulk upload of the month's files (electronic invoice ZIPs, photos of cuentas de cobro, a new RUT,
   a bank statement).
2. Cascading extraction: XML → deterministic parser; free text → own small model; failure → large
   API model; failure → human.
3. Validation: NIT check digit, totals, tax profile of new suppliers.
4. Alerts: duplicates and unusual amounts, explained with SHAP.
5. Human review: field corrections and dismissed alerts, all audited.
6. Tax questions answered by RAG with citations (or abstention).
7. Reconciliation of invoices against bank movements (exact, fuzzy, grouped, bank fees, GMF tax).
8. Approval according to policy: batch, individual or dual approval depending on confidence and amount.
9. Booking, audit trail, closing report and export to the accounting software.
10. Background quality: traces, cost of the closing, weekly corrections loop.

**Goal:** bring the 2-day closing down to half a day, with every number verifiable.

## Architecture and stack

| Layer | Components | Tools |
|-------|------------|-------|
| Interface | Web app; external MCP client | Next.js (App Router, TypeScript, Tailwind, shadcn/ui), Clerk or Auth.js |
| Service | API; workers; MCP server | FastAPI, Pydantic v2, Celery + Redis, official MCP SDK (FastMCP) |
| Core | Extraction; classic ML; RAG; agent | lxml, Docling/pypdfium2, Tesseract (`spa`), Instructor; scikit-learn, LightGBM, SHAP; pgvector + FTS + re-ranker; LangGraph |
| Models | Cascading router | Parser → own model (vLLM) → large API model → human |
| Data | Relational, vectors, audit, checkpoints, files, experiments | PostgreSQL 16/17 + pgvector, R2/S3 (MinIO locally), MLflow |
| Quality (cross-cutting) | Traces, evals, judges, policies, audit, cost | Langfuse (or Arize Phoenix), DeepEval + pytest, GitHub Actions |
| Deployment | | Vercel (web), Cloud Run or Fly.io (API, worker), Neon or Supabase (Postgres), R2/S3 |

Monorepo layout: `apps/api` (FastAPI, managed with uv), `apps/web` (Next.js), `services/mcp-server`,
`ml/`, `evals/`, `infra/`, `docs/`. Key decision:
[ADR 0001 · Monorepo and PostgreSQL as the single database](docs/adr/0001-monorepo-y-postgres-unica-base.md).

## Status

- [x] Setup: monorepo, local services (Docker Compose), backend and frontend skeletons, pre-commit,
      base CI, `.env.example`, ADR 0001
- [ ] Phase 0 · Data and baseline (anonymized corpus, golden set, extractor v0)
- [ ] Phase 1 · Evals first (traces, error taxonomy, aligned judges, CI gate)
- [ ] Phase 2 · Hybrid RAG and classic ML (tax questions, duplicates and anomalies)
- [ ] Phase 3 · Governed agent and MCP server (reconciliation with human approval)
- [ ] Phase 4 · Cost and own model (fine-tuning, vLLM, router)
- [ ] Phase 5 · Real users and launch

## Running locally

Requirements: Docker (Compose v2), [uv](https://docs.astral.sh/uv/), Python 3.12, Node LTS and pnpm.

```bash
# 1. Configuration (never commit .env)
cp .env.example .env

# 2. Local services: Postgres + pgvector, Redis, MinIO (with the initial bucket)
docker compose -f infra/docker-compose.yml up -d
#    Optional Phoenix for tracing:
#    docker compose -f infra/docker-compose.yml --profile observability up -d

# 3. API (http://localhost:8000/health)
cd apps/api && uv run uvicorn app.main:app --reload

# 4. Worker
cd apps/api && uv run celery -A app.workers worker -l info

# 5. Web
cd apps/web && pnpm install && pnpm dev

# 6. Database migrations
cd apps/api && uv run alembic upgrade head
```

Tests and code quality:

```bash
cd apps/api && uv run pytest
cd apps/web && pnpm lint
uv run --directory apps/api pre-commit install          # git hooks: Ruff, mypy, Prettier, ESLint, gitleaks
uv run --directory apps/api pre-commit run --all-files
```

## Privacy

Contable IA handles personal and tax data protected by Colombian law (Ley 1581 de 2012, Decreto
1377 de 2013). Only **anonymized** documents are used for development, evals and any external API.
Raw documents live in `data/`, which is git-ignored and **never** pushed; gitleaks runs in
pre-commit and CI to block secrets.

## License

[MIT](LICENSE) © 2026 orduzluis397-cmd
