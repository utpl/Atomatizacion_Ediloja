"""Pruebas del validador del curso.json."""

import json
from pathlib import Path

import pytest

from libs.py.esquema.validador import validar

RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "datos_ejemplo" / "fixtures"


def _cargar(nombre: str) -> dict:
    return json.loads((FIX / nombre).read_text(encoding="utf-8"))


def test_completo_es_verde():
    """Una guía completa y correcta no tiene alertas."""
    res = validar(_cargar("02_completo.json"))
    assert res.semaforo == "verde"
    assert res.alertas == []


def test_sin_autoevaluacion_es_rojo():
    """Una semana que cierra unidad sin autoevaluación es un error."""
    res = validar(_cargar("03_sin_autoevaluaciones.json"))
    assert res.semaforo == "rojo"
    codigos = {a.codigo for a in res.errores}
    assert "falta_autoevaluacion" in codigos


def test_cita_huerfana_es_error():
    """Una cita que apunta a una referencia inexistente es un error."""
    res = validar(_cargar("04_con_alertas.json"))
    codigos = {a.codigo for a in res.errores}
    assert "cita_sin_referencia" in codigos


def test_imagen_sin_alt_es_aviso():
    """Una figura de contenido sin texto alternativo es un aviso, no un error."""
    res = validar(_cargar("04_con_alertas.json"))
    codigos_aviso = {a.codigo for a in res.avisos}
    assert "falta_texto_alternativo" in codigos_aviso


@pytest.mark.parametrize(
    "nombre",
    ["02_completo.json", "03_sin_autoevaluaciones.json", "04_con_alertas.json"],
)
def test_como_dict_tiene_forma_esperada(nombre):
    """El resultado serializado tiene semáforo y lista de alertas."""
    d = validar(_cargar(nombre)).como_dict()
    assert d["semaforo"] in ("verde", "amarillo", "rojo")
    assert isinstance(d["alertas"], list)
