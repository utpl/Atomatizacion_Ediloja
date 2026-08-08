"""Convierte el texto libre de `contents` en unidades estructuradas.

Por qué una llamada aparte al modelo y no un análisis por reglas: el docente
escribe "Unidad 1", "UNIDAD I", "Primera unidad" o nada de eso. Una expresión
regular acierta con el formato que se probó y falla callada con el resto, y el
fallo aparece ocho llamadas después, cuando la autoevaluación acaba en la
semana equivocada.

Se llama UNA vez por guía, antes de las ocho de contenido. Es barata: solo ve
los contenidos y el número de semanas, no la bibliografía.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

INSTRUCCIONES = """
Eres un asistente que estructura la planificación de una asignatura.

Recibes el listado de unidades, temas y subtemas tal como lo escribió el
docente, y el número total de semanas. Devuelves el reparto por semanas.

REGLAS:

1. No inventes unidades ni renombres las que hay. Usa los títulos del docente.
2. Reparte TODAS las semanas: la última unidad termina en la última semana.
3. Las unidades van en orden y no se solapan.
4. Si el docente ya indicó qué semanas cubre cada unidad, respétalo.
5. Si no lo indicó, reparte de forma equilibrada.

Devuelve exclusivamente un objeto JSON, sin texto alrededor y sin vallas de
código:

{"unidades": [{"numero": 1, "titulo": "…", "semana_inicio": 1, "semana_fin": 4}]}
""".strip()


class ErrorDeUnidades(RuntimeError):
    pass


def _entrada(contenidos: str, total_semanas: int) -> str:
    return (
        f"Número total de semanas: {total_semanas}\n\n"
        f"UNIDADES Y CONTENIDOS PLANIFICADOS:\n{contenidos}"
    )


def _limpiar(texto: str) -> dict[str, Any]:
    """El modelo a veces envuelve el JSON en vallas pese a pedírselo."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t)


def _validar(crudas: list[dict], total_semanas: int) -> list[dict[str, Any]]:
    if not crudas:
        raise ErrorDeUnidades("El modelo no devolvió ninguna unidad.")

    unidades = []
    for i, u in enumerate(crudas, start=1):
        inicio = int(u.get("semana_inicio", 0))
        fin = int(u.get("semana_fin", 0))
        titulo = str(u.get("titulo", "")).strip()

        if not titulo:
            raise ErrorDeUnidades(f"La unidad {i} no tiene título.")
        if not 1 <= inicio <= fin <= total_semanas:
            raise ErrorDeUnidades(
                f"La unidad {i} ('{titulo}') abarca de la semana {inicio} a la {fin}, "
                f"fuera del rango 1–{total_semanas}."
            )
        unidades.append(
            {"id": f"u{i}", "numero": i, "titulo": titulo,
             "semana_inicio": inicio, "semana_fin": fin}
        )

    # Cobertura completa y sin huecos: si falla, la autoevaluación acabaría
    # en la semana equivocada y nadie lo notaría hasta revisar la guía.
    cubiertas = {s for u in unidades for s in range(u["semana_inicio"], u["semana_fin"] + 1)}
    faltan = set(range(1, total_semanas + 1)) - cubiertas
    if faltan:
        raise ErrorDeUnidades(f"Semanas sin unidad asignada: {sorted(faltan)}")

    return unidades


def extraer_unidades(
    contenidos: str,
    total_semanas: int,
    llamador: Callable[[str, str], Any],
    intentos: int = 3,
) -> list[dict[str, Any]]:
    errores: list[str] = []
    for _ in range(intentos):
        try:
            respuesta = llamador(INSTRUCCIONES, _entrada(contenidos, total_semanas))
            datos = _limpiar(respuesta.texto)
            return _validar(datos.get("unidades", []), total_semanas)
        except (json.JSONDecodeError, ErrorDeUnidades, KeyError, ValueError) as exc:
            errores.append(str(exc))
    raise ErrorDeUnidades(
        f"No se pudieron extraer las unidades tras {intentos} intentos. "
        f"Últimos errores: {' | '.join(errores[-2:])}"
    )


def plan_desde_unidades(unidades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """El plan que consume generar_guia: qué unidad toca cada semana.

    `cierra_unidad` marca la última semana de cada unidad, y de ahí sale
    dónde va la autoevaluación de diez preguntas (regla institucional 10).
    """
    plan = []
    for u in unidades:
        for semana in range(u["semana_inicio"], u["semana_fin"] + 1):
            plan.append({
                "semana": semana,
                "unidad": u["numero"],
                "cierra_unidad": semana == u["semana_fin"],
            })
    return sorted(plan, key=lambda p: p["semana"])
