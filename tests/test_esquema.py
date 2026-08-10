"""Prueba de contrato: los fixtures deben validar contra el esquema.

Es la prueba más barata y más útil del repositorio. Si alguien cambia
`curso.schema.json` sin actualizar los fixtures —o al revés— esto se cae solo,
antes de que el frontend se entere por su cuenta de que el contrato cambió.

    pytest tests/test_esquema.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.py.esquema.validador import validar

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = sorted((RAIZ / "datos_ejemplo" / "fixtures").glob("*.json"))

# Fixtures que dan rojo A PROPÓSITO: son parciales o traen errores de muestra.
# Se listan aquí para que el rojo esperado no se confunda con una regresión.
ROJO_ESPERADO = {
    "01_minimo.json",
    "03_sin_autoevaluaciones.json",
    "04_con_alertas.json",
    "05_catalogo_bloques.json",
    # Curso viejo migrado de Canvas: trae 5 semanas y el esquema solo admite
    # 8 o 16, asi que 'semanas_incompletas' salta a proposito. Es el aviso de
    # que la migracion deja la guia a medias y hay que completarla antes de
    # publicar; ponerla en verde ocultaria justo lo que hay que ver.
    "07_migrado.json",
}


def test_hay_fixtures():
    """Si esta prueba falla, las demás pasan vacías y no comprueban nada."""
    assert FIXTURES, "No hay fixtures en datos_ejemplo/fixtures/"


@pytest.mark.parametrize("ruta", FIXTURES, ids=lambda r: r.name)
def test_el_fixture_es_json_valido(ruta: Path):
    json.loads(ruta.read_text(encoding="utf-8"))


@pytest.mark.parametrize("ruta", FIXTURES, ids=lambda r: r.name)
def test_el_fixture_pasa_la_capa_estructural(ruta: Path):
    """Ningún fixture puede fallar el JSON Schema.

    Un fixture puede incumplir reglas de negocio (para eso están), pero si
    incumple el esquema es que está mal escrito: el sistema lo rechazaría.
    """
    resultado = validar(json.loads(ruta.read_text(encoding="utf-8")))
    de_esquema = [a for a in resultado.alertas if a.codigo == "esquema"]
    assert not de_esquema, (
        f"{ruta.name} no cumple el esquema:\n"
        + "\n".join(f"  - {a.ruta}: {a.mensaje}" for a in de_esquema[:5])
    )


@pytest.mark.parametrize("ruta", FIXTURES, ids=lambda r: r.name)
def test_el_semaforo_es_el_esperado(ruta: Path):
    resultado = validar(json.loads(ruta.read_text(encoding="utf-8")))
    if ruta.name in ROJO_ESPERADO:
        assert resultado.semaforo == "rojo", (
            f"{ruta.name} debería dar rojo y dio {resultado.semaforo}. "
            "Si se arregló a propósito, quítalo de ROJO_ESPERADO."
        )
    else:
        assert resultado.semaforo != "rojo", (
            f"{ruta.name} da rojo y no debería:\n"
            + "\n".join(f"  - {a.codigo}: {a.mensaje}" for a in resultado.errores[:5])
        )
