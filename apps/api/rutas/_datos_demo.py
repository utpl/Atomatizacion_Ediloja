"""Carga del curso.json de ejemplo para las vistas.

Temporal: mientras el editor no consume la API real, las vistas leen un
fixture del disco. Cuando llegue el momento, esta función se sustituye por
una llamada a GET /api/guias/{id}/version-actual y las plantillas no se
enteran: siguen recibiendo el mismo diccionario.
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

# ⚠️ Ajusta el nombre al fixture que tengas de verdad.
FIXTURE = RAIZ / "datos_ejemplo" / "fixtures" / "06_real.json"


def cargar_curso() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def indexar(curso: dict) -> dict:
    """Convierte las listas del curso en diccionarios buscables.

    Una cita guarda 'referencia_id': "ref1", pero las referencias viven en
    una LISTA. Buscarlas recorriendo la lista en cada cita obligaría a
    repetir esa lógica en cada plantilla. Se indexa una vez, aquí.
    """
    return {
        "recursos": {r["ref"]: r for r in curso.get("recursos", [])},
        "refs": {r["id"]: r for r in curso.get("finales", {}).get("referencias", [])},
    }
