# syntax=docker/dockerfile:1.7
# =============================================================================================
# Contable IA · imagen de la API + worker Celery para la demo (Render free, 512 MB, CR-005).
# Contexto de build: la RAÍZ del repositorio (render.yaml: dockerContext: .).
#
#   docker build -f infra/deploy/Dockerfile -t contable-ia-api .
#
# Etapa 1 (builder): instala las dependencias de apps/api con uv (sin las de desarrollo).
# Etapa 2 (runtime): Python slim + Tesseract con español, usuario sin privilegios, sin uv ni
# compiladores. Un solo contenedor corre uvicorn y el worker (infra/deploy/start.sh) porque los
# background workers de Render no son gratis.
# =============================================================================================

ARG PYTHON_VERSION=3.12

FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
# tesseract-ocr-spa: OCR en español (app/extraction/ocr.py). tini: init mínimo que reenvía
# señales a start.sh y recoge procesos huérfanos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    CONSENT_DOCUMENT_PATH=/app/legal/autorizacion-uso-documentos.md \
    PORT=8000

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=root:root apps/api/app ./app
COPY --chown=root:root apps/api/alembic ./alembic
COPY --chown=root:root apps/api/alembic.ini ./alembic.ini
# Texto de la autorización de uso de datos que se muestra antes de la primera carga.
COPY --chown=root:root docs/legal/autorizacion-uso-documentos.md ./legal/autorizacion-uso-documentos.md
COPY --chown=root:root --chmod=0755 infra/deploy/start.sh /usr/local/bin/start.sh

# El código queda de root y solo lectura para el usuario de la app.
USER app:app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start.sh"]
