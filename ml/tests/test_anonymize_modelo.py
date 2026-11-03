"""Pruebas con Presidio + spaCy es_core_news_lg (lentas; marcadas `modelo`, fuera de la CI)."""

from __future__ import annotations

import pytest
from conftest import Originales, factura_pdf

import anonymize as an

pytestmark = [
    pytest.mark.modelo,
    pytest.mark.skipif(not an.modelo_disponible(), reason="falta es_core_news_lg"),
]


@pytest.fixture(scope="module")
def detector_ner() -> an.Detector:
    return an.Detector(usar_ner=True)


def test_ner_detecta_nombre_en_texto_libre(detector_ner: an.Detector) -> None:
    texto = "Recibí de Carlos Alberto Mejía Ríos la suma de 500000 pesos por honorarios."
    personas = [h.texto for h in detector_ner.detectar(texto) if h.entidad == an.PERSONA]
    assert any("Carlos" in p for p in personas)


def test_ner_conserva_regex(detector_ner: an.Detector) -> None:
    hallazgos = detector_ner.detectar("NIT 900.123.456-8, cel 3105551234")
    assert {h.entidad for h in hallazgos} >= {an.NIT, an.CELULAR}


def test_pdf_con_ner_sin_originales(detector_ner: an.Detector, originales: Originales) -> None:
    r = an.anonimizar_bytes(factura_pdf(), "pdf", detector_ner, an.Reemplazador(semilla=3))
    texto = an.texto_pdf(r.datos).casefold()
    assert [v for v in originales.sensibles() if v.casefold() in texto] == []
