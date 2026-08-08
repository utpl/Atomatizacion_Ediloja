"""Arma la entrada concreta de cada llamada al modelo.

`prompt.py` dice *cómo* escribir. Este módulo dice *qué* escribir en esta
llamada concreta: qué semana, de qué unidad, con qué bibliografía, y qué se
dijo en la semana anterior.

Está separado porque la entrada cambia en cada una de las ocho llamadas
mientras que las instrucciones son siempre las mismas. Mezclarlos obligaría a
reconstruir el prompt entero cada vez y haría imposible cachearlo.
"""

from __future__ import annotations

import json
from typing import Any

# Cuántos caracteres de la semana previa se le pasan como contexto. Suficiente
# para que enlace el discurso, poco para que no se dispare el coste.
LIMITE_RESUMEN = 1200


def resumen_de_pagina(pagina: dict[str, Any] | None) -> str:
    """Resume una página ya generada, para dársela como contexto a la siguiente.

    No le pasamos el JSON entero de la semana previa: son miles de tokens por
    llamada, se multiplican por ocho, y el modelo solo necesita saber de qué se
    habló para no repetirse ni contradecirse.
    """
    if not pagina:
        return "(No hay semana previa: esta es la primera.)"

    partes: list[str] = [f"Título: {pagina.get('titulo', '(sin título)')}"]
    for bloque in pagina.get("bloques", []):
        tipo = bloque.get("tipo")
        if tipo == "encabezado":
            partes.append(f"- Sección: {bloque.get('texto', '')}")
        elif tipo == "parrafo":
            texto = str(bloque.get("texto", ""))
            partes.append(f"  {texto[:200]}")

    resumen = "\n".join(partes)
    if len(resumen) > LIMITE_RESUMEN:
        resumen = resumen[:LIMITE_RESUMEN] + " […]"
    return resumen


def entrada_de_semana(
    *,
    datos_curso: dict[str, Any],
    semana: int,
    unidad_id: str | None = None,
    tema: str | None = None,
    bibliografia: list[str] | None = None,
    pagina_previa: dict[str, Any] | None = None,
    cierra_unidad: bool = False,
    error_previo: str | None = None,
) -> str:
    """Construye el mensaje de usuario para generar una semana concreta.

    `error_previo` es lo que convierte el reintento en algo útil: si la primera
    salida no validó, se le devuelve al modelo el error concreto en vez de
    pedirle lo mismo otra vez y esperar suerte.
    """
    lineas: list[str] = [
        "## Curso",
        f"Asignatura: {datos_curso.get('asignatura', '(sin asignatura)')}",
        f"Código: {datos_curso.get('codigo_banner', '(sin código)')}",
        f"Periodo: {datos_curso.get('periodo', '(sin periodo)')}",
        f"Total de semanas: {datos_curso.get('total_semanas', '?')}",
        "",
        "## Qué generar ahora",
        f"Semana: {semana}",
    ]

    if unidad_id is not None:
        lineas.append(f"Unidad: {unidad_id}")
    if tema:
        lineas.append(f"Tema: {tema}")

    if bibliografia:
        lineas += [
            "",
            "## Bibliografía disponible",
            "Cita únicamente estas obras. No añadas ninguna otra.",
            *(f"- {obra}" for obra in bibliografia),
        ]

    if cierra_unidad:
        lineas += [
            "",
            "## Aviso",
            (
                "Esta semana **cierra unidad**. Debe incluir un bloque de tipo "
                "`autoevaluacion` al final."
            ),
        ]

    lineas += ["", "## Contexto de la semana anterior", resumen_de_pagina(pagina_previa)]

    if error_previo:
        lineas += [
            "",
            "## Corrección necesaria",
            "Tu respuesta anterior no fue válida. Error concreto:",
            error_previo,
            "Corrígelo y devuelve el JSON completo de nuevo.",
        ]

    return "\n".join(lineas)


def entrada_como_json(datos: dict[str, Any]) -> str:
    """Serializa datos auxiliares de forma estable (para tests y trazas)."""
    return json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True)
