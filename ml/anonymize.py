"""Anonimizador de documentos contables de Contable IA (INSTRUCCIONES.md §8.1).

Detecta datos personales con Presidio (+ spaCy ``es_core_news_lg`` para nombres) y reconocedores
regex colombianos (NIT de persona jurídica y natural, cédula, celular, teléfono fijo, cuentas
bancarias, correos, direcciones y CUFE) y los reemplaza por valores falsos **con el mismo formato**
(un NIT falso lleva DV válido), consistentes dentro de un documento (un ZIP de factura es un solo
documento: el XML y el PDF comparten los reemplazos).

- XML (UBL 2.1 / ``AttachedDocument``): ``lxml``; identificaciones por ``schemeName``, nombres,
  contactos y direcciones por estructura; texto libre por regex; XML embebido en CDATA, recursivo;
  firma digital (certificado X.509) neutralizada.
- PDF: PyMuPDF (``add_redact_annot`` + ``apply_redactions``) con el texto falso encima; también la
  capa de texto oculta (OCR). Se eliminan imágenes (pueden traer el QR con el CUFE), metadatos,
  anotaciones, adjuntos y JavaScript. Tras guardar se vuelve a extraer el texto y, si queda algún
  original, **no se escribe la salida** (falla cerrada).
- Tabla de correspondencias original → falso cifrada con Fernet (clave en ``CONTABLE_IA_ANON_KEY``)
  y escrita solo bajo un directorio ``data/``.

PyMuPDF es AGPL-3.0: vive solo en este proyecto ``ml/`` de ejecución local (CR-003); nunca en
``apps/`` ni en imágenes desplegadas.

Uso (las rutas relativas se resuelven desde ``ml/``)::

    uv run --directory ml python anonymize.py --generar-clave
    uv run --directory ml python anonymize.py ../data/raw/f001.zip ../data/anonimizados/f001.zip
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import random
import re
import secrets
import string
import sys
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pymupdf
from cryptography.fernet import Fernet, InvalidToken
from faker import Faker
from lxml import etree
from presidio_analyzer import EntityRecognizer, RecognizerResult

ENV_CLAVE = "CONTABLE_IA_ANON_KEY"
MODELO_SPACY = "es_core_news_lg"

# --------------------------------------------------------------------------------------------
# Entidades
# --------------------------------------------------------------------------------------------

NIT = "CO_NIT"
CEDULA = "CO_CEDULA"
CELULAR = "CO_CELULAR"
TELEFONO = "CO_TELEFONO_FIJO"
CUENTA = "CO_CUENTA_BANCARIA"
CORREO = "EMAIL_ADDRESS"
DIRECCION = "CO_DIRECCION"
CUFE = "CO_CUFE"
PERSONA = "PERSON"
ORGANIZACION = "ORGANIZATION"
RAZON_SOCIAL = "CO_RAZON_SOCIAL"  # regex: nombre seguido de S.A.S., LTDA, S.A.

ENTIDADES_ID = frozenset({NIT, CEDULA})
ENTIDADES_NOMBRE = frozenset({PERSONA, ORGANIZACION, RAZON_SOCIAL})
ENTIDADES_REGEX = (NIT, CEDULA, CELULAR, TELEFONO, CUENTA, CORREO, DIRECCION, CUFE, RAZON_SOCIAL)

# Tipos de documento de identificación de la DIAN (atributo schemeName en UBL): 11 registro civil,
# 12 tarjeta de identidad, 13 cédula, 21 tarjeta de extranjería, 22 cédula de extranjería, 31 NIT,
# 41 pasaporte, 42 documento extranjero, 47 PEP, 48 PPT, 50 NIT de otro país, 91 NUIP.
SCHEMES_ID = frozenset({"11", "12", "13", "21", "22", "31", "41", "42", "47", "48", "50", "91"})


class ErrorAnonimizacion(Exception):
    """El documento no se pudo anonimizar de forma segura; no se escribe salida."""


# --------------------------------------------------------------------------------------------
# DV del NIT (algoritmo DIAN, INSTRUCCIONES.md §8.2). Duplicado a propósito de
# apps/api/app/schemas/validators.py: ml/ es un proyecto independiente.
# --------------------------------------------------------------------------------------------

PESOS_DV = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def calcular_dv(nit: str) -> int:
    """DV del NIT: dígitos de derecha a izquierda por los pesos DIAN, suma módulo 11."""
    digitos = re.sub(r"\D", "", nit)
    if not digitos or len(digitos) > len(PESOS_DV):
        raise ValueError(f"NIT inválido para calcular DV: {len(digitos)} dígitos")
    suma = sum(int(d) * p for d, p in zip(reversed(digitos), PESOS_DV, strict=False))
    residuo = suma % 11
    return residuo if residuo in (0, 1) else 11 - residuo


# --------------------------------------------------------------------------------------------
# Reconocedores regex (Presidio)
# --------------------------------------------------------------------------------------------

# Número de identificación: con puntos de miles (1.020.304.050, 79.123.456, 900.123.456) o sin
# ellos, de 5 a 10 dígitos (cédulas antiguas cortas hasta NIT/cédulas de 10). Cubre el NIT de
# persona natural, que es su cédula (longitud variable) — hallazgo del glosario.
_NUM_ID = r"(?:\d{1,3}(?:\.\d{3}){1,3}|\d{5,10})"
_DV = r"\s?-\s?\d"
_KW_NIT = r"NIT|N\.\s?I\.\s?T\.?|Nit(?:Fac|Adq)|R\.?U\.?T\.?"
_KW_CC = (
    r"C\.\s?C\.?|CC|c[eé]dula(?:\s+de\s+(?:ciudadan[ií]a|extranjer[ií]a))?|C\.\s?E\.?|"
    r"T\.\s?I\.?|DocAdq|identificaci[oó]n|documento\s+de\s+identidad"
)
_TRAS_KW = r"(?![A-Za-zÁÉÍÓÚáéíóú])[\s:.#°º]*(?:No\.?|N[°º]\.?|n[uú]mero)?[\s:.#°º]*"


@dataclass(frozen=True)
class Patron:
    entidad: str
    regex: re.Pattern[str]
    score: float
    grupo: str | None = None


PATRONES: tuple[Patron, ...] = (
    # NIT con DV explícito (jurídica o natural): 900.123.456-7, 79123456-1, 1.020.304.050-3
    Patron(NIT, re.compile(rf"(?<![\d.]){_NUM_ID}{_DV}(?![\d])"), 0.85),
    # NIT con palabra clave, con o sin DV: "NIT: 900123456", "NIT 1020304050-3"
    Patron(
        NIT,
        re.compile(
            rf"(?<![A-Za-z])(?:{_KW_NIT}){_TRAS_KW}(?P<v>{_NUM_ID}(?:{_DV})?)(?!\d)", re.IGNORECASE
        ),
        0.9,
        "v",
    ),
    # Cédula y otros documentos con palabra clave (6-10 dígitos según §8.1, 5 por cédulas viejas)
    Patron(
        CEDULA,
        re.compile(
            rf"(?<![A-Za-z])(?:{_KW_CC}){_TRAS_KW}(?P<v>{_NUM_ID}(?:{_DV})?)(?!\d)", re.IGNORECASE
        ),
        0.9,
        "v",
    ),
    # Celular: (+57) 3xx xxx xxxx
    Patron(
        CELULAR, re.compile(r"(?<![\d+])(?:\+?57[\s-]?)?3\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)"), 0.8
    ),
    # Fijo con indicativo nacional 60X (marcación desde 2021): 604 444 5555
    Patron(
        TELEFONO,
        re.compile(r"(?<![\d+])(?:\+?57[\s-]?)?\(?60\d\)?[\s-]?\d{3}[\s-]?\d{4}(?!\d)"),
        0.7,
    ),
    # Cuenta bancaria con palabra clave
    Patron(
        CUENTA,
        re.compile(
            r"(?<![A-Za-z])(?:cuenta|cta\.?)(?:\s+(?:de\s+)?(?:ahorros?|corriente))?"
            r"(?:\s+(?:No\.?|N[°º]\.?|n[uú]mero))?[\s:.#°º]*(?P<v>\d[\d\s-]{4,22}\d)(?!\d)",
            re.IGNORECASE,
        ),
        0.85,
        "v",
    ),
    Patron(
        CORREO,
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
        0.95,
    ),
    # Dirección colombiana: Calle 10 # 43-21, Cra. 45 No. 12-34 Apto 501, Av 80 N° 65-223
    Patron(
        DIRECCION,
        re.compile(
            r"(?<![A-Za-z])(?:calle|cl|cll|carrera|cra|kra|kr|cr|avenida|av|ak|ac|diagonal|dg|"
            r"transversal|tv|tr|circular|cq|autopista)\.?\s*\d{1,3}\s?[A-Za-z]?(?:\s?bis)?"
            r"\s*(?:#|No\.?|N[°º]\.?|n[uú]mero)?\s*\d{1,3}\s?[A-Za-z]?\s*-\s*\d{1,3}"
            r"(?:\s*(?:apto|apartamento|of|oficina|local|int|interior|torre|casa|bloque)"
            r"\.?\s*\d{1,5}[A-Za-z]?)*",
            re.IGNORECASE,
        ),
        0.8,
    ),
    # Razón social con forma societaria: "FERRETERIA EL TORNILLO S.A.S.", "Pérez y Cía LTDA"
    Patron(
        RAZON_SOCIAL,
        re.compile(
            r"(?<![\w.])(?:[A-ZÁÉÍÓÚÑ0-9][\wÁÉÍÓÚÑáéíóúñ&.'-]*[ \t]+){1,8}"
            r"(?:S\.?[ ]?A\.?[ ]?S\.?|SAS|LTDA\.?|Ltda\.?|S\.[ ]?A\.?|E\.[ ]?U\.?)(?![\w])"
        ),
        0.75,
    ),
    # CUFE/CUDE: SHA-384 en hexadecimal (permite consultar la factura y sus partes en la DIAN).
    # En la representación gráfica suele partirse en varias líneas: se aceptan tramos de 16 a 96
    # caracteres hex con al menos una letra y un dígito.
    Patron(
        CUFE,
        re.compile(
            r"(?<![0-9A-Za-z])(?=[0-9A-Fa-f]*[A-Fa-f])(?=[0-9A-Fa-f]*\d)[0-9A-Fa-f]{16,96}"
            r"(?![0-9A-Za-z])"
        ),
        0.95,
    ),
)


class ReconocedorRegexCO(EntityRecognizer):
    """Reconocedor Presidio con los patrones colombianos; usa un grupo nombrado como span."""

    def __init__(self, patrones: Sequence[Patron] = PATRONES) -> None:
        self.patrones = tuple(patrones)
        super().__init__(
            supported_entities=sorted({p.entidad for p in self.patrones}),
            name="ReconocedorRegexCO",
            supported_language="es",
        )

    def load(self) -> None:
        """Sin modelo que cargar."""

    def analyze(
        self, text: str, entities: list[str] | None, nlp_artifacts: Any = None
    ) -> list[RecognizerResult]:
        resultados: list[RecognizerResult] = []
        for patron in self.patrones:
            if entities and patron.entidad not in entities:
                continue
            for m in patron.regex.finditer(text):
                ini, fin = m.span(patron.grupo) if patron.grupo else m.span()
                if 0 <= ini < fin:
                    resultados.append(RecognizerResult(patron.entidad, ini, fin, patron.score))
        return resultados


# --------------------------------------------------------------------------------------------
# Detección
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Hallazgo:
    entidad: str
    inicio: int
    fin: int
    texto: str


def _prioridad(entidad: str) -> int:
    return 1 if entidad in (PERSONA, ORGANIZACION) else 2


def resolver_solapamientos(hallazgos: Iterable[Hallazgo]) -> list[Hallazgo]:
    """Deja hallazgos sin solaparse: primero regex sobre NER, luego el más largo."""
    elegidos: list[Hallazgo] = []
    candidatos = sorted(hallazgos, key=lambda h: (-_prioridad(h.entidad), -(h.fin - h.inicio)))
    for h in candidatos:
        if all(h.fin <= e.inicio or h.inicio >= e.fin for e in elegidos):
            elegidos.append(h)
    return sorted(elegidos, key=lambda h: h.inicio)


class Detector:
    """Regex colombianas siempre; NER de spaCy vía Presidio si ``usar_ner``."""

    def __init__(self, usar_ner: bool = True, entidades_ner: Sequence[str] = (PERSONA,)) -> None:
        self.regex = ReconocedorRegexCO()
        self.entidades_ner = tuple(entidades_ner)
        self._analyzer: Any = None
        if usar_ner:
            self._analyzer = _crear_analyzer(self.regex)

    @property
    def usa_ner(self) -> bool:
        return self._analyzer is not None

    def detectar(self, texto: str) -> list[Hallazgo]:
        if not texto.strip():
            return []
        if self._analyzer is not None:
            resultados = self._analyzer.analyze(
                text=texto,
                language="es",
                entities=[*ENTIDADES_REGEX, *self.entidades_ner],
                score_threshold=0.5,
            )
        else:
            resultados = self.regex.analyze(texto, list(ENTIDADES_REGEX))
        hallazgos = [
            Hallazgo(r.entity_type, r.start, r.end, texto[r.start : r.end])
            for r in resultados
            if texto[r.start : r.end].strip()
        ]
        return resolver_solapamientos(hallazgos)


def modelo_disponible() -> bool:
    import importlib.util

    return importlib.util.find_spec(MODELO_SPACY) is not None


def _crear_analyzer(reconocedor_regex: ReconocedorRegexCO) -> Any:
    if not modelo_disponible():
        raise ErrorAnonimizacion(
            f"Falta el modelo spaCy {MODELO_SPACY}. Instálalo con "
            "`uv sync --directory ml --group modelo` o usa --solo-regex (no detecta nombres "
            "en texto libre)."
        )
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import SpacyRecognizer

    configuracion = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "es", "model_name": MODELO_SPACY}],
        "ner_model_configuration": {
            "model_to_presidio_entity_mapping": {
                "PER": PERSONA,
                "PERSON": PERSONA,
                "ORG": ORGANIZACION,
                "LOC": "LOCATION",
                "MISC": "MISC",
            },
            "labels_to_ignore": ["MISC"],
        },
    }
    motor_nlp = NlpEngineProvider(nlp_configuration=configuracion).create_engine()
    registro = RecognizerRegistry(supported_languages=["es"])
    registro.add_recognizer(reconocedor_regex)
    registro.add_recognizer(
        SpacyRecognizer(supported_language="es", supported_entities=[PERSONA, ORGANIZACION])
    )
    return AnalyzerEngine(registry=registro, nlp_engine=motor_nlp, supported_languages=["es"])


# --------------------------------------------------------------------------------------------
# Reemplazos con el mismo formato, consistentes por documento
# --------------------------------------------------------------------------------------------

_SUFIJO_SOCIEDAD = re.compile(
    r"\s*(?:S\.?\s?A\.?\s?S\.?|LTDA\.?|S\.?\s?A\.?|E\.?\s?U\.?|S\.?\s?C\.?\s?A\.?|& CIA\.?)\s*$",
    re.IGNORECASE,
)
_ID_CON_DV = re.compile(r"(?P<cuerpo>[\d.]+?)(?P<sep>\s?-\s?)(?P<dv>\d)")


def _normalizar_nombre(texto: str) -> str:
    return " ".join(texto.casefold().split())


def _llenar_plantilla(plantilla: str, digitos: str) -> str:
    """Pone ``digitos`` en las posiciones de dígito de ``plantilla`` (conserva separadores)."""
    it = iter(digitos)
    return "".join(next(it) if c.isdigit() else c for c in plantilla)


@dataclass
class Par:
    entidad: str
    original: str
    falso: str


@dataclass
class Reemplazador:
    """Genera valores falsos con el mismo formato y los recuerda para todo el documento."""

    semilla: int | None = None
    pares: list[Par] = field(default_factory=list)

    def __post_init__(self) -> None:
        semilla = self.semilla if self.semilla is not None else secrets.randbits(64)
        self._rng = random.Random(semilla)  # noqa: S311 - no criptográfico a propósito
        self._faker = Faker("es_CO")
        self._faker.seed_instance(self._rng.randrange(2**32))
        self._ids: dict[str, str] = {}  # cuerpo original (solo dígitos) -> cuerpo falso
        self._otros: dict[tuple[str, str], str] = {}
        self._falsos_id: set[str] = set()
        self._falsos: set[tuple[str, str]] = set()
        self._conocidos: dict[str, str] = {}  # texto original -> entidad (para propagar)

    # -- utilidades
    def _digitos(self, n: int, primero: str | None = None) -> str:
        inicio = primero if primero is not None else str(self._rng.randint(1, 9))
        return inicio + "".join(self._rng.choice(string.digits) for _ in range(n - 1))

    def _registrar(self, entidad: str, original: str, falso: str) -> str:
        self.pares.append(Par(entidad, original, falso))
        if len(original.strip()) >= 4:
            self._conocidos.setdefault(original.strip(), entidad)
        return falso

    # -- identificación (NIT y cédula comparten tabla: el NIT de persona natural es su cédula)
    def cuerpo_id_falso(self, cuerpo: str) -> str:
        if cuerpo in self._falsos_id:
            return cuerpo
        if cuerpo not in self._ids:
            while True:
                # Conserva solo el primer dígito de un NIT de 9 (8/9 = persona jurídica).
                primero = cuerpo[0] if len(cuerpo) == 9 and cuerpo[0] in "89" else None
                falso = self._digitos(len(cuerpo), primero)
                if falso != cuerpo and falso not in self._falsos_id:
                    break
            self._ids[cuerpo] = falso
            self._falsos_id.add(falso)
        return self._ids[cuerpo]

    def id_falso(self, original: str, entidad: str = NIT) -> str:
        texto = original.strip()
        m = _ID_CON_DV.fullmatch(texto)
        plantilla = m.group("cuerpo") if m else texto
        cuerpo = re.sub(r"\D", "", plantilla)
        if not cuerpo:
            return self._alfanumerico_falso(entidad, texto)
        falso_cuerpo = self.cuerpo_id_falso(cuerpo)
        if cuerpo != falso_cuerpo and len(cuerpo) >= 6:
            # El cuerpo sin puntos ni DV también se busca en el resto del documento.
            self._conocidos.setdefault(cuerpo, entidad)
        falso = _llenar_plantilla(plantilla, falso_cuerpo)
        if m:
            falso += m.group("sep") + str(calcular_dv(falso_cuerpo))
        if falso == texto:  # ya era un falso de este documento
            return texto
        return self._registrar(entidad, texto, falso)

    def _alfanumerico_falso(self, entidad: str, original: str) -> str:
        clave = (entidad, original.casefold())
        if clave not in self._otros:
            falso = "".join(
                self._rng.choice(string.digits)
                if c.isdigit()
                else self._rng.choice(string.ascii_uppercase)
                if c.isalpha()
                else c
                for c in original
            )
            self._otros[clave] = falso
            self._registrar(entidad, original, falso)
        return self._otros[clave]

    # -- genérico con memoria
    def _memorizado(self, entidad: str, clave: str, original: str, generar: Any) -> str:
        if (entidad, clave) in self._falsos:
            return original
        k = (entidad, clave)
        if k not in self._otros:
            falso = str(generar())
            self._otros[k] = falso
            self._falsos.add((entidad, self._clave(entidad, falso)))
            self._registrar(entidad, original, falso)
        return self._otros[k]

    @staticmethod
    def _clave(entidad: str, texto: str) -> str:
        if entidad in (CELULAR, TELEFONO, CUENTA):
            return re.sub(r"\D", "", texto)
        if entidad in ENTIDADES_NOMBRE or entidad == DIRECCION:
            return _normalizar_nombre(texto)
        return texto.strip().casefold()

    def _telefono(self, original: str, conservar: int) -> str:
        m = re.match(r"(\+?57[\s-]?)?(.*)", original, re.DOTALL)
        assert m is not None  # noqa: S101 - el patrón siempre coincide
        prefijo, resto = m.group(1) or "", m.group(2)
        digitos = re.sub(r"\D", "", resto)
        nuevos = digitos[:conservar] + "".join(
            self._rng.choice(string.digits) for _ in range(len(digitos) - conservar)
        )
        return prefijo + _llenar_plantilla(resto, nuevos)

    def _nombre(self, original: str) -> str:
        texto = original.strip()
        sufijo = _SUFIJO_SOCIEDAD.search(texto)
        if sufijo:
            base = (
                self._faker.last_name()
                + " "
                + self._rng.choice(
                    ["Comercial", "Distribuciones", "Servicios", "Inversiones", "Soluciones"]
                )
            )
            falso = base + texto[sufijo.start() :]
        else:
            n = max(1, len(texto.split()))
            partes = (
                [self._faker.first_name()]
                if n == 1
                else [self._faker.first_name(), self._faker.last_name()]
                if n == 2
                else [self._faker.first_name(), self._faker.last_name(), self._faker.last_name()]
                if n == 3
                else [
                    self._faker.first_name(),
                    self._faker.first_name(),
                    self._faker.last_name(),
                    self._faker.last_name(),
                ]
            )
            falso = " ".join(partes)
        if texto.isupper():
            falso = falso.upper()
        return falso

    def _correo(self) -> str:
        usuario = re.sub(r"[^a-z0-9._]", "", self._faker.user_name().lower()) or "usuario"
        return f"{usuario}{self._rng.randint(1, 999)}@example.com"

    def _hex(self, original: str) -> str:
        falso = "".join(self._rng.choice("0123456789abcdef") for _ in original)
        return falso.upper() if original.isupper() else falso

    def _hex_falso(self, original: str) -> str:
        """Un tramo de un CUFE ya visto (PDF partido en líneas) toma el tramo de su falso."""
        tramo = original.casefold()
        for (entidad, clave), falso in self._otros.items():
            if entidad == CUFE and tramo in clave and len(clave) == len(falso):
                inicio = clave.index(tramo)
                parte = falso[inicio : inicio + len(tramo)]
                return parte.upper() if original.isupper() else parte
        return self._hex(original)

    def _digitos_plantilla(self, original: str) -> str:
        digitos = re.sub(r"\D", "", original)
        return _llenar_plantilla(original, self._digitos(len(digitos)) if digitos else "")

    def falso(self, entidad: str, original: str) -> str:
        """Valor falso del mismo formato; el mismo original da siempre el mismo falso."""
        if entidad in ENTIDADES_ID:
            return self.id_falso(original, entidad)
        clave = self._clave(entidad, original)
        if entidad == CELULAR:
            return self._memorizado(entidad, clave, original, lambda: self._telefono(original, 1))
        if entidad == TELEFONO:
            return self._memorizado(entidad, clave, original, lambda: self._telefono(original, 3))
        if entidad == CORREO:
            return self._memorizado(entidad, clave, original, self._correo)
        if entidad == CUFE:
            return self._memorizado(entidad, clave, original, lambda: self._hex_falso(original))
        if entidad in ENTIDADES_NOMBRE:
            # Personas y organizaciones comparten tabla (el mismo nombre en XML y PDF).
            return self._memorizado(PERSONA, clave, original, lambda: self._nombre(original))
        return self._memorizado(entidad, clave, original, lambda: self._digitos_plantilla(original))

    def buscar_conocidos(self, texto: str) -> list[Hallazgo]:
        """Ocurrencias de originales ya vistos (p. ej. nombres del XML en el PDF del ZIP)."""
        hallazgos: list[Hallazgo] = []
        for original, entidad in self._conocidos.items():
            if original.isdigit():
                patron = rf"(?<!\d){re.escape(original)}(?!\d)"
            else:
                patron = rf"(?<!\w){re.escape(original)}(?!\w)"
            for m in re.finditer(patron, texto, re.IGNORECASE):
                hallazgos.append(Hallazgo(entidad, m.start(), m.end(), m.group()))
        return hallazgos

    def originales(self) -> set[str]:
        return {p.original for p in self.pares} | set(self._conocidos)


def hallazgos_en(texto: str, detector: Detector, rep: Reemplazador) -> list[Hallazgo]:
    """Detecta, registra los falsos y suma las ocurrencias de originales ya conocidos.

    Registrar antes de propagar permite encontrar, p. ej., el NIT sin puntos ni DV en la capa
    oculta cuando en la visible aparece como ``900.123.456-8``.
    """
    detectados = detector.detectar(texto)
    for h in detectados:
        rep.falso(h.entidad, h.texto)
    return resolver_solapamientos([*detectados, *rep.buscar_conocidos(texto)])


def reemplazar_en_texto(texto: str, detector: Detector, rep: Reemplazador) -> str:
    hallazgos = hallazgos_en(texto, detector, rep)
    partes: list[str] = []
    cursor = 0
    for h in hallazgos:
        partes.append(texto[cursor : h.inicio])
        partes.append(rep.falso(h.entidad, h.texto))
        cursor = h.fin
    partes.append(texto[cursor:])
    return "".join(partes)


# --------------------------------------------------------------------------------------------
# XML
# --------------------------------------------------------------------------------------------

_TAGS_NOMBRE = frozenset({"RegistrationName", "FirstName", "FamilyName", "MiddleName"})
_PADRES_NAME = frozenset({"PartyName", "Contact", "Person"})
_TAGS_CONTACTO = {"Telephone": TELEFONO, "Telefax": TELEFONO, "ElectronicMail": CORREO}
_TAGS_FIRMA_B64 = frozenset({"X509Certificate", "SignatureValue"})
_TAGS_FIRMA_TEXTO = frozenset({"X509SubjectName", "X509IssuerName"})


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _telefono_entidad(texto: str) -> str:
    return CELULAR if re.sub(r"\D", "", texto).lstrip("57").startswith("3") else TELEFONO


def anonimizar_xml(datos: bytes, detector: Detector, rep: Reemplazador) -> bytes:
    """Anonimiza un XML (UBL 2.1 o AttachedDocument). Ver docstring del módulo."""
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, strip_cdata=False, remove_blank_text=False
    )
    try:
        raiz = etree.fromstring(datos, parser)
    except etree.XMLSyntaxError as exc:
        raise ErrorAnonimizacion(f"XML inválido: {exc}") from exc
    _anonimizar_arbol(raiz, detector, rep)
    arbol = raiz.getroottree()
    codificacion = arbol.docinfo.encoding or "UTF-8"
    return cast(bytes, etree.tostring(arbol, xml_declaration=True, encoding=codificacion))


def _anonimizar_arbol(raiz: etree._Element, detector: Detector, rep: Reemplazador) -> None:
    hechos: set[etree._Element] = set()
    elementos = list(raiz.iter())
    # 1) Pasada estructural: lo que se sabe por la etiqueta, para alimentar la propagación.
    for el in elementos:
        local = _local(el)
        texto = (el.text or "").strip()
        if not local or not texto:
            continue
        padre = el.getparent()
        if el.get("schemeName") in SCHEMES_ID:
            entidad = NIT if el.get("schemeName") in ("31", "50") else CEDULA
            falso = rep.falso(entidad, texto)
            el.text = falso
            cuerpo = re.sub(r"\D", "", falso)
            if el.get("schemeID") is not None and el.get("schemeName") == "31" and cuerpo:
                el.set("schemeID", str(calcular_dv(cuerpo)))
            hechos.add(el)
        elif local in _TAGS_NOMBRE or (
            local == "Name" and padre is not None and _local(padre) in _PADRES_NAME
        ):
            el.text = rep.falso(PERSONA, texto)
            hechos.add(el)
        elif local in _TAGS_CONTACTO:
            entidad = _TAGS_CONTACTO[local]
            if entidad == TELEFONO:
                entidad = _telefono_entidad(texto)
            el.text = rep.falso(entidad, texto)
            hechos.add(el)
        elif local == "Line" and padre is not None and _local(padre) == "AddressLine":
            el.text = rep.falso(DIRECCION, texto)
            hechos.add(el)
        elif local in _TAGS_FIRMA_B64:
            # El certificado X.509 trae nombre y NIT del firmante: se reemplaza por bytes al azar.
            el.text = base64.b64encode(secrets.token_bytes(max(3, len(texto) * 3 // 4))).decode()
            hechos.add(el)
        elif local in _TAGS_FIRMA_TEXTO:
            el.text = "CN=Anonimizado,O=Anonimizado,C=CO"
            hechos.add(el)
    # 2) Texto libre, colas, atributos y comentarios; XML embebido (CDATA), recursivo.
    for el in elementos:
        if el not in hechos and el.text:
            embebido = _xml_embebido(el.text)
            if embebido is not None:
                _anonimizar_arbol(embebido, detector, rep)
                interno = bytes(
                    etree.tostring(embebido.getroottree(), xml_declaration=True, encoding="UTF-8")
                )
                el.text = etree.CDATA(interno.decode("utf-8"))
            else:
                el.text = reemplazar_en_texto(el.text, detector, rep)
        if el.tail:
            el.tail = reemplazar_en_texto(el.tail, detector, rep)
        if isinstance(el.tag, str):
            for nombre, valor in el.attrib.items():
                nuevo = reemplazar_en_texto(str(valor), detector, rep)
                if nuevo != valor:
                    el.set(nombre, nuevo)


def _xml_embebido(texto: str) -> etree._Element | None:
    t = texto.strip()
    if not t.startswith("<"):
        return None
    parser = etree.XMLParser(resolve_entities=False, no_network=True, strip_cdata=False)
    try:
        return etree.fromstring(t.encode("utf-8"), parser)
    except (etree.XMLSyntaxError, ValueError):
        return None


# --------------------------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------------------------


@dataclass
class ResultadoPdf:
    datos: bytes
    avisos: list[str]


def _tamano_fuente(texto: str, rect: pymupdf.Rect) -> float:
    def ancho(t: float) -> float:
        return float(pymupdf.get_text_length(texto, fontname="helv", fontsize=t))

    tamano = max(4.0, float(rect.height) * 0.8)
    while tamano > 4.0 and ancho(tamano) > rect.width:
        tamano -= 0.5
    return tamano


def _rects_de(pagina: pymupdf.Page, texto: str) -> list[pymupdf.Rect]:
    rects = list(pagina.search_for(texto))
    if not rects and "\n" in texto:
        for parte in texto.splitlines():
            if parte.strip():
                rects.extend(pagina.search_for(parte.strip()))
    return rects


def texto_pdf(datos: bytes) -> str:
    """Todo el texto extraíble (incluida la capa oculta) más los metadatos."""
    with pymupdf.open(stream=datos, filetype="pdf") as doc:
        partes = [str(doc[i].get_text("text")) for i in range(doc.page_count)]
        partes.extend(str(v) for v in (doc.metadata or {}).values() if v)
        partes.append(doc.get_xml_metadata() or "")
    return "\n".join(partes)


def anonimizar_pdf(
    datos: bytes, detector: Detector, rep: Reemplazador, conservar_imagenes: bool = False
) -> ResultadoPdf:
    avisos: list[str] = []
    try:
        doc = pymupdf.open(stream=datos, filetype="pdf")
    except Exception as exc:  # PyMuPDF lanza varios tipos
        raise ErrorAnonimizacion(f"PDF ilegible: {exc}") from exc
    with doc:
        if doc.needs_pass:
            raise ErrorAnonimizacion("PDF cifrado: descífralo localmente antes de anonimizar")
        for indice in range(doc.page_count):
            num = indice + 1
            pagina = doc[indice]
            for anotacion in list(pagina.annots() or []):
                pagina.delete_annot(anotacion)
            texto = pagina.get_text("text")
            if len(texto.strip()) < 20:
                avisos.append(
                    f"página {num}: sin capa de texto útil; requiere OCR o anonimización manual"
                )
            hallazgos = hallazgos_en(texto, detector, rep)
            textos = sorted({h.texto: h for h in hallazgos}.values(), key=lambda h: -len(h.texto))
            cubiertos: list[pymupdf.Rect] = []
            for h in textos:
                falso = rep.falso(h.entidad, h.texto)
                for rect in _rects_de(pagina, h.texto):
                    if any(c.contains(rect) for c in cubiertos):
                        continue
                    cubiertos.append(rect)
                    pagina.add_redact_annot(
                        rect,
                        text=falso,
                        fontname="helv",
                        fontsize=_tamano_fuente(falso, rect),
                        fill=(1, 1, 1),
                        text_color=(0, 0, 0),
                        cross_out=False,
                    )
            pagina.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_PIXELS, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE
            )
            imagenes = pagina.get_images(full=True)
            if imagenes and not conservar_imagenes:
                for img in imagenes:
                    pagina.delete_image(img[0])
                avisos.append(
                    f"página {num}: {len(imagenes)} imagen(es) eliminada(s) (QR, logos, firmas)"
                )
            elif imagenes:
                avisos.append(
                    f"página {num}: {len(imagenes)} imagen(es) conservada(s) SIN anonimizar"
                )
        doc.scrub(
            attached_files=True,
            clean_pages=True,
            embedded_files=True,
            hidden_text=False,  # la capa oculta ya se redactó; borrarla perdería el OCR
            javascript=True,
            metadata=True,
            redactions=False,
            remove_links=True,
            reset_fields=True,
            reset_responses=True,
            thumbnails=True,
            xml_metadata=True,
        )
        salida = doc.tobytes(garbage=4, deflate=True, clean=True)
    return ResultadoPdf(salida, avisos)


# --------------------------------------------------------------------------------------------
# Verificación (falla cerrada)
# --------------------------------------------------------------------------------------------


def fugas(texto_salida: str, originales: Iterable[str]) -> list[str]:
    """Originales que siguen en el texto de salida (exactos o sin puntos/espacios)."""
    compacto = re.sub(r"[.\s]", "", texto_salida).casefold()
    plano = " ".join(texto_salida.split()).casefold()
    encontrados = []
    for original in originales:
        o = " ".join(original.split()).casefold()
        if len(o) < 4:
            continue
        o_compacto = re.sub(r"[.\s]", "", o)
        if o in plano or (o_compacto.isdigit() and len(o_compacto) >= 6 and o_compacto in compacto):
            encontrados.append(original)
    return encontrados


def _verificar(texto_salida: str, rep: Reemplazador, nombre: str) -> None:
    restantes = fugas(texto_salida, rep.originales())
    if restantes:
        tipos = sorted({p.entidad for p in rep.pares if p.original in restantes})
        raise ErrorAnonimizacion(
            f"{nombre}: quedan {len(restantes)} valor(es) originales tras anonimizar "
            f"(tipos: {', '.join(tipos)}); no se escribe la salida"
        )


# --------------------------------------------------------------------------------------------
# Documento completo (XML, PDF o ZIP)
# --------------------------------------------------------------------------------------------


@dataclass
class Resultado:
    datos: bytes
    rep: Reemplazador
    avisos: list[str]
    miembros: dict[str, str] = field(default_factory=dict)  # nombre original -> nombre nuevo


def anonimizar_bytes(
    datos: bytes,
    tipo: str,
    detector: Detector,
    rep: Reemplazador | None = None,
    conservar_imagenes: bool = False,
) -> Resultado:
    """Anonimiza ``datos`` (``xml``, ``pdf`` o ``zip``) y verifica que no queden originales."""
    rep = rep if rep is not None else Reemplazador()
    tipo = tipo.lower().lstrip(".")
    if tipo == "xml":
        salida = anonimizar_xml(datos, detector, rep)
        _verificar(salida.decode("utf-8", errors="replace"), rep, "XML")
        return Resultado(salida, rep, [])
    if tipo == "pdf":
        pdf = anonimizar_pdf(datos, detector, rep, conservar_imagenes)
        _verificar(texto_pdf(pdf.datos), rep, "PDF")
        return Resultado(pdf.datos, rep, pdf.avisos)
    if tipo == "zip":
        return _anonimizar_zip(datos, detector, rep, conservar_imagenes)
    raise ErrorAnonimizacion(f"Tipo no soportado: {tipo!r} (usa .xml, .pdf o .zip)")


def _anonimizar_zip(
    datos: bytes, detector: Detector, rep: Reemplazador, conservar_imagenes: bool
) -> Resultado:
    avisos: list[str] = []
    miembros: dict[str, str] = {}
    salidas: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(datos)) as zin:
        infos = [i for i in zin.infolist() if not i.is_dir()]
        # XML primero: sus nombres e identificaciones se propagan al PDF.
        infos.sort(key=lambda i: (Path(i.filename).suffix.lower() != ".xml", i.filename))
        for n, info in enumerate(infos, start=1):
            ext = Path(info.filename).suffix.lower().lstrip(".")
            if ext not in ("xml", "pdf"):
                avisos.append(f"miembro {n} (.{ext or '?'}) omitido: tipo no soportado")
                continue
            # Los nombres de archivo de la DIAN llevan el NIT: se renombran.
            nuevo = f"{n:02d}_documento.{ext}"
            r = anonimizar_bytes(zin.read(info), ext, detector, rep, conservar_imagenes)
            avisos.extend(f"{nuevo}: {a}" for a in r.avisos)
            salidas.append((nuevo, r.datos))
            miembros[info.filename] = nuevo
    # Verificación cruzada: ningún original de ningún miembro en ningún miembro.
    for nombre, contenido in salidas:
        texto = (
            texto_pdf(contenido)
            if nombre.endswith(".pdf")
            else contenido.decode("utf-8", "replace")
        )
        _verificar(texto, rep, nombre)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for nombre, contenido in salidas:
            zout.writestr(nombre, contenido)
    return Resultado(buffer.getvalue(), rep, avisos, miembros)


# --------------------------------------------------------------------------------------------
# Tabla de correspondencias cifrada (solo bajo data/)
# --------------------------------------------------------------------------------------------


def exigir_bajo_data(ruta: Path) -> Path:
    resuelta = ruta.resolve()
    if "data" not in resuelta.parent.parts:
        raise ErrorAnonimizacion(
            f"La tabla de correspondencias solo se escribe bajo un directorio data/: {ruta}"
        )
    return resuelta


def _fernet(clave: str | None) -> Fernet:
    if not clave:
        raise ErrorAnonimizacion(
            f"Falta la variable de entorno {ENV_CLAVE} (genera una con --generar-clave) "
            "o usa --sin-tabla"
        )
    try:
        return Fernet(clave.encode())
    except ValueError as exc:
        raise ErrorAnonimizacion(f"{ENV_CLAVE} no es una clave Fernet válida") from exc


def escribir_tabla(ruta: Path, resultado: Resultado, fuente: str, clave: str | None) -> Path:
    destino = exigir_bajo_data(ruta)
    contenido = {
        "version": 1,
        "fuente": fuente,
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "miembros": resultado.miembros,
        "pares": [
            {"entidad": p.entidad, "original": p.original, "falso": p.falso}
            for p in resultado.rep.pares
        ],
    }
    token = _fernet(clave).encrypt(json.dumps(contenido, ensure_ascii=False).encode("utf-8"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(token)
    return destino


def leer_tabla(ruta: Path, clave: str | None) -> dict[str, Any]:
    try:
        datos: dict[str, Any] = json.loads(_fernet(clave).decrypt(ruta.read_bytes()))
    except InvalidToken as exc:
        raise ErrorAnonimizacion("Clave incorrecta o tabla dañada") from exc
    return datos


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anonymize.py",
        description="Anonimiza un XML, PDF o ZIP de factura (Contable IA, §8.1).",
    )
    p.add_argument("entrada", nargs="?", type=Path, help="archivo .xml, .pdf o .zip")
    p.add_argument("salida", nargs="?", type=Path, help="archivo de salida (mismo tipo)")
    p.add_argument(
        "--tabla",
        type=Path,
        help="ruta de la tabla cifrada (bajo data/); por defecto <salida>.mapping.enc",
    )
    p.add_argument("--sin-tabla", action="store_true", help="no escribir tabla de correspondencias")
    p.add_argument(
        "--solo-regex",
        action="store_true",
        help="sin NER de spaCy (no detecta nombres en texto libre; solo pruebas)",
    )
    p.add_argument(
        "--ner",
        default=PERSONA,
        help=f"entidades NER separadas por coma: {PERSONA},{ORGANIZACION} (defecto {PERSONA})",
    )
    p.add_argument("--conservar-imagenes", action="store_true", help="no eliminar imágenes del PDF")
    p.add_argument("--semilla", type=int, help="semilla de los valores falsos (reproducible)")
    p.add_argument(
        "--generar-clave", action="store_true", help=f"imprime una clave para {ENV_CLAVE}"
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.generar_clave:
        print(Fernet.generate_key().decode())
        return 0
    if args.entrada is None or args.salida is None:
        _parser().error("faltan <entrada> y <salida>")
    entrada: Path = args.entrada
    salida: Path = args.salida
    try:
        if entrada.resolve() == salida.resolve():
            raise ErrorAnonimizacion("La salida no puede sobrescribir la entrada")
        tabla: Path | None = None
        clave = os.environ.get(ENV_CLAVE)
        if not args.sin_tabla:
            tabla = exigir_bajo_data(args.tabla or salida.with_name(salida.name + ".mapping.enc"))
            _fernet(clave)  # falla antes de procesar si no hay clave
        entidades_ner = [e.strip() for e in args.ner.split(",") if e.strip()]
        detector = Detector(usar_ner=not args.solo_regex, entidades_ner=entidades_ner)
        resultado = anonimizar_bytes(
            entrada.read_bytes(),
            entrada.suffix,
            detector,
            Reemplazador(args.semilla),
            args.conservar_imagenes,
        )
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_bytes(resultado.datos)
        if tabla is not None:
            escribir_tabla(tabla, resultado, entrada.name, clave)
    except (ErrorAnonimizacion, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    # Resumen sin valores originales (nunca se imprimen datos personales).
    conteo: dict[str, int] = {}
    for par in resultado.rep.pares:
        conteo[par.entidad] = conteo.get(par.entidad, 0) + 1
    print(f"OK {salida} · reemplazos: {json.dumps(conteo, sort_keys=True)}")
    if not detector.usa_ner:
        print("AVISO: sin NER; los nombres en texto libre no se detectaron", file=sys.stderr)
    for aviso in resultado.avisos:
        print(f"AVISO: {aviso}", file=sys.stderr)
    print("Pendiente: revisión manual del 100 % del documento anonimizado (§8.1).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
