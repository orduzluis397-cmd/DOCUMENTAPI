"""Datos de desarrollo local (nunca en producción).

    uv run python -m app.db.seed                       # organización + usuario demo
    uv run python -m app.db.seed --demo-fields <doc>   # extracción ficticia para probar la UI

Usa el rol de la app (`DATABASE_URL`) con contexto de organización, igual que la API: así el
seed también ejercita las políticas de RLS. Los IDs son fijos para que la web los recuerde.
"""

import argparse
import uuid

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Document, ExtractedField, Extraction, Organization, User
from app.db.session import tenant_session

DEMO_ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000101")

# Campos ficticios (no son datos reales de nadie) para probar resaltado y edición en la web.
DEMO_FIELDS: list[tuple[str, object, bool, float]] = [
    ("emisor.nit", "900123456-7", False, 0.98),
    ("emisor.razon_social", "Comercializadora Ejemplo S.A.S.", False, 0.95),
    ("factura.numero", "FE-1001", False, 0.99),
    ("factura.fecha_emision", "2026-10-15", False, 0.97),
    ("totales.subtotal", 1000000, False, 0.93),
    ("totales.iva", 190000, True, 0.41),
    ("totales.total", 1190000, True, 0.55),
]


def seed_demo() -> None:
    with tenant_session(DEMO_ORG_ID) as s:
        if s.get(Organization, DEMO_ORG_ID) is None:
            s.add(Organization(id=DEMO_ORG_ID, name="Pyme Demo S.A.S."))
            s.flush()
        if s.get(User, DEMO_USER_ID) is None:
            s.add(
                User(
                    id=DEMO_USER_ID,
                    organization_id=DEMO_ORG_ID,
                    email="demo@contable-ia.local",
                    full_name="Usuario Demo",
                    role="admin",
                )
            )
        s.commit()
    print(f"organization_id={DEMO_ORG_ID}\nuser_id={DEMO_USER_ID}")


def seed_demo_fields(document_id: uuid.UUID) -> None:
    with tenant_session(DEMO_ORG_ID) as s:
        doc = s.get(Document, document_id)
        if doc is None:
            raise SystemExit(f"Documento {document_id} no existe en la organización demo")
        existing = s.scalar(select(Extraction.id).where(Extraction.document_id == doc.id))
        if existing is not None:
            raise SystemExit("El documento ya tiene una extracción")
        ext = Extraction(
            organization_id=DEMO_ORG_ID,
            document_id=doc.id,
            doc_type="factura",
            method="pdf_text",
            prompt_version="demo",
        )
        s.add(ext)
        s.flush()
        for name, value, doubtful, conf in DEMO_FIELDS:
            s.add(
                ExtractedField(
                    organization_id=DEMO_ORG_ID,
                    extraction_id=ext.id,
                    name=name,
                    value=value,
                    is_doubtful=doubtful,
                    confidence=conf,
                    page=1,
                )
            )
        doc.status = "needs_review"
        doc.doc_type = "factura"
        s.commit()
    print(f"extracción demo creada para {document_id}")


def main() -> None:
    if get_settings().app_env not in {"local", "test"}:
        raise SystemExit("El seed solo corre con APP_ENV=local|test")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-fields", type=uuid.UUID, metavar="DOCUMENT_ID")
    args = parser.parse_args()
    if args.demo_fields:
        seed_demo_fields(args.demo_fields)
    else:
        seed_demo()


if __name__ == "__main__":
    main()
