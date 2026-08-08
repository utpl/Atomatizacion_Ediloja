"""Catálogo académico de la UTPL: nivel → modalidad → facultad → carrera.

Origen: public/app.js de app-creacion-asignaturas (UTPL). Es un dato
institucional que cambia cada periodo, no código: vive en packages/canon/
como JSON y se lee, no se incrusta en una plantilla.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[3]
ARCHIVO = RAIZ / "packages" / "canon" / "oferta_academica.json"

NIVELES = [
    ("tecnologia", "Tecnología"),
    ("grado", "Grado"),
    ("posgrado", "Posgrado"),
    ("doctorado", "Doctorado"),
]


@lru_cache(maxsize=1)
def _datos() -> dict[str, Any]:
    return json.loads(ARCHIVO.read_text(encoding="utf-8"))


def modalidades(nivel: str) -> list[dict[str, str]]:
    return _datos()["modalidades_por_nivel"].get(nivel, [])


def facultades(nivel: str, modalidad: str) -> list[dict[str, str]]:
    ramas = _datos()["oferta_academica"].get(nivel, {})
    return [{"value": f["value"], "label": f["label"]} for f in ramas.get(modalidad, [])]


def carreras(nivel: str, modalidad: str, facultad: str) -> list[dict[str, str]]:
    ramas = _datos()["oferta_academica"].get(nivel, {})
    for f in ramas.get(modalidad, []):
        if f["value"] == facultad:
            return f["programs"]
    return []


def etiqueta(opciones: list[dict[str, str]], valor: str) -> str:
    """El modelo necesita el nombre legible, no el identificador.

    El prompt recibe "Facultad de Ciencias Económicas y Empresariales", no
    "facultad-ciencias-economicas-empresariales". Mandar el identificador
    degradaría el contexto sin que nadie lo notara.
    """
    for o in opciones:
        if o["value"] == valor:
            return o["label"]
    return valor
