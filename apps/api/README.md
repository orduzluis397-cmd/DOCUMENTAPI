# contable-ia-api

API de Contable IA (FastAPI + Pydantic v2 + Celery). Gestionada con `uv` (Python 3.12).

```bash
uv sync
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app
```
