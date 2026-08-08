"""Aplica operaciones de edición sobre un `curso.json`.

**Este módulo no sabe que existe una base de datos.** Entra un dict, salen un
dict modificado y la lista de lo que cambió. Nada de sesiones, ni de SQLAlchemy,
ni de FastAPI.

Esa separación no es purismo: es lo que permite probar toda la lógica difícil
—localizar bloques anidados, validar el anidamiento, renumerar figuras— sin
levantar Postgres. La ruta HTTP que va encima acaba siendo veinte líneas de
pegamento.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from libs.py.agente import ensamblado
from libs.py.agente.prompt import ETIQUETAS_INLINE, FOCALIZADORES, TIPOS_DE_BLOQUE

CONTENEDORES = ensamblado.CONTENEDORES


class ErrorDeEdicion(ValueError):
    """La operación no se puede aplicar. Se traduce a 422 en la API."""


# ---------------------------------------------------------------------------
# Comprobaciones sobre un bloque suelto
#
# El agente comprueba páginas enteras recién generadas; aquí se comprueba un
# bloque suelto que acaba de tocar el docente. Misma lista blanca, distinta
# granularidad: por eso son dos funciones y no una. Las listas se importan de
# `prompt.py` para que no puedan desincronizarse.
# ---------------------------------------------------------------------------

_ETIQUETA = re.compile(r"<\s*/?\s*([a-zA-Z0-9]+)")


def _etiquetas_prohibidas(valor: Any) -> set[str]:
    if not isinstance(valor, str):
        return set()
    return {e.lower() for e in _ETIQUETA.findall(valor)} - set(ETIQUETAS_INLINE)


def comprobar_bloque(bloque: dict[str, Any], *, anidado: bool = False) -> None:
    """Lanza `ErrorDeEdicion` si el bloque no cumple las reglas del esquema."""
    if not isinstance(bloque, dict):
        raise ErrorDeEdicion("El bloque debe ser un objeto.")

    tipo = bloque.get("tipo")
    if tipo not in TIPOS_DE_BLOQUE:
        raise ErrorDeEdicion(
            f"Tipo de bloque no permitido: {tipo!r}. "
            f"Permitidos: {', '.join(TIPOS_DE_BLOQUE)}."
        )

    if tipo == "focalizador":
        variante = bloque.get("focalizador")
        if variante is not None and variante not in FOCALIZADORES:
            raise ErrorDeEdicion(
                f"Focalizador con valor no permitido: {variante!r}. "
                f"Permitidos: {', '.join(FOCALIZADORES)}."
            )

    for clave, valor in bloque.items():
        if clave == "bloques":
            continue
        sobran = _etiquetas_prohibidas(valor)
        if sobran:
            raise ErrorDeEdicion(
                f"Etiquetas HTML no permitidas en '{clave}': {', '.join(sorted(sobran))}. "
                f"Solo se admiten: {', '.join(ETIQUETAS_INLINE)}."
            )

    hijos = bloque.get("bloques")
    if isinstance(hijos, list):
        if tipo not in CONTENEDORES:
            raise ErrorDeEdicion(
                f"Un bloque de tipo {tipo!r} no puede contener otros bloques."
            )
        if anidado:
            raise ErrorDeEdicion(
                "Anidamiento de más de un nivel: un bloque dentro de una caja o "
                "un focalizador no puede contener a su vez otros bloques."
            )
        for hijo in hijos:
            comprobar_bloque(hijo, anidado=True)


# ---------------------------------------------------------------------------
# Localización
# ---------------------------------------------------------------------------


def _paginas(curso: dict[str, Any]) -> list[dict[str, Any]]:
    """Las páginas viven en estructura.paginas. Delegado en ensamblado."""
    return ensamblado.paginas_de(curso)


def buscar_pagina(curso: dict[str, Any], pagina_id: str) -> dict[str, Any]:
    for pagina in _paginas(curso):
        if pagina.get("id") == pagina_id:
            return pagina
    raise ErrorDeEdicion(f"No existe la página {pagina_id!r}.")


def localizar_bloque(
    curso: dict[str, Any], bloque_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Devuelve (página, lista que lo contiene, índice dentro de esa lista).

    Devolver la **lista contenedora** y no solo el bloque es lo que permite
    borrar y mover sin volver a buscar, y hace que dé igual si el bloque está
    suelto en la página o dentro de una caja.
    """
    for pagina in _paginas(curso):
        bloques = pagina.get("bloques", [])
        for i, bloque in enumerate(bloques):
            if bloque.get("id") == bloque_id:
                return pagina, bloques, i
            hijos = ensamblado.hijos_de(bloque)
            if hijos is not None:
                for j, hijo in enumerate(hijos):
                    if hijo.get("id") == bloque_id:
                        return pagina, hijos, j
    raise ErrorDeEdicion(f"No existe el bloque {bloque_id!r}.")


def _lista_destino(
    curso: dict[str, Any], pagina_id: str, dentro_de: str | None
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    """Resuelve dónde hay que insertar. El bool dice si el destino está anidado."""
    pagina = buscar_pagina(curso, pagina_id)
    if dentro_de is None:
        return pagina, pagina.setdefault("bloques", []), False

    for bloque in pagina.get("bloques", []):
        if bloque.get("id") == dentro_de:
            if bloque.get("tipo") not in CONTENEDORES:
                raise ErrorDeEdicion(
                    f"El bloque {dentro_de!r} es de tipo {bloque.get('tipo')!r} y no "
                    f"puede contener otros bloques. Solo pueden: "
                    f"{', '.join(CONTENEDORES)}."
                )
            hijos = bloque.setdefault("bloques", [])
            if not isinstance(hijos, list):
                raise ErrorDeEdicion(
                    f"El bloque {dentro_de!r} tiene 'contenido' que no es una lista."
                )
            return pagina, hijos, True

    raise ErrorDeEdicion(
        f"No existe el contenedor {dentro_de!r} en la página {pagina_id!r}."
    )


# ---------------------------------------------------------------------------
# Origen: quién tocó cada bloque
# ---------------------------------------------------------------------------


def _marcar_editado(bloque: dict[str, Any]) -> None:
    """Un bloque de la IA que edita el docente pasa a ser 'mixto'.

    Esto es lo que hace medible cuánto reescribe el docente lo que generó la IA.
    Sin ese dato no hay forma de saber si el agente está mejorando.
    """
    origen = bloque.get("origen")
    if origen == "agente":
        bloque["origen"] = "mixto"
    elif origen is None:
        bloque["origen"] = "docente"


# ---------------------------------------------------------------------------
# Las ocho operaciones
# ---------------------------------------------------------------------------


def _op_actualizar_bloque(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    _, lista, i = localizar_bloque(curso, op.bloque_id)
    antes = copy.deepcopy(lista[i])

    if "id" in op.campos and op.campos["id"] != op.bloque_id:
        raise ErrorDeEdicion("El id de un bloque no se puede cambiar.")

    candidato = copy.deepcopy(lista[i])
    candidato.update(op.campos)
    _, _, esta_anidado = _situacion(curso, op.bloque_id)
    comprobar_bloque(candidato, anidado=esta_anidado)
    _marcar_editado(candidato)

    lista[i] = candidato
    return {
        "operacion": "actualizar_bloque",
        "bloque_id": op.bloque_id,
        "antes": antes,
        "despues": copy.deepcopy(candidato),
    }


def _situacion(curso: dict[str, Any], bloque_id: str) -> tuple[dict, list, bool]:
    """Como localizar_bloque, pero dice además si el bloque está anidado."""
    for pagina in _paginas(curso):
        for bloque in pagina.get("bloques", []):
            if bloque.get("id") == bloque_id:
                return pagina, pagina["bloques"], False
            hijos = ensamblado.hijos_de(bloque)
            if hijos is not None:
                for hijo in hijos:
                    if hijo.get("id") == bloque_id:
                        return pagina, hijos, True
    raise ErrorDeEdicion(f"No existe el bloque {bloque_id!r}.")


def _op_eliminar_bloque(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    _, lista, i = localizar_bloque(curso, op.bloque_id)
    antes = copy.deepcopy(lista.pop(i))
    return {
        "operacion": "eliminar_bloque",
        "bloque_id": op.bloque_id,
        "antes": antes,
        "despues": None,
    }


def _op_insertar_bloque(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    pagina, lista, anidado = _lista_destino(curso, op.pagina_id, op.dentro_de)
    bloque = copy.deepcopy(op.bloque)
    comprobar_bloque(bloque, anidado=anidado)

    bloque.setdefault("id", ensamblado.nuevo_id_bloque())
    bloque.setdefault("origen", "docente")
    if any(b.get("id") == bloque["id"] for b in lista):
        raise ErrorDeEdicion(f"Ya existe un bloque con id {bloque['id']!r}.")

    indice = min(op.indice, len(lista))
    lista.insert(indice, bloque)
    return {
        "operacion": "insertar_bloque",
        "bloque_id": bloque["id"],
        "pagina_id": pagina.get("id"),
        "antes": None,
        "despues": copy.deepcopy(bloque),
    }


def _op_mover_bloque(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    _, origen_lista, i = localizar_bloque(curso, op.bloque_id)
    bloque = origen_lista[i]

    pagina, destino_lista, anidado = _lista_destino(curso, op.pagina_id, op.dentro_de)

    # Un contenedor con hijos no cabe dentro de otro contenedor: sería nivel 2.
    if anidado and bloque.get("tipo") in CONTENEDORES and bloque.get("bloques"):
        raise ErrorDeEdicion(
            "No se puede meter una caja o un focalizador con contenido dentro de "
            "otro contenedor: excedería el anidamiento de un nivel."
        )
    if anidado and op.dentro_de == op.bloque_id:
        raise ErrorDeEdicion("Un bloque no se puede mover dentro de sí mismo.")

    # `indice` es la posición que el bloque debe ocupar en la lista YA
    # reordenada, no en la de antes. Es lo único que se comporta igual tanto si
    # mueves dentro de la misma lista como si mueves a otra, y lo que hace que
    # 0 sea siempre "al principio" y len() siempre "al final". La alternativa
    # (índice sobre la lista original) obliga al frontend a restar uno solo
    # cuando arrastra hacia abajo dentro de la misma página, y ese "solo
    # cuando" es una fuente clásica de bugs de arrastrar y soltar.
    origen_lista.pop(i)
    indice = min(op.indice, len(destino_lista))
    destino_lista.insert(indice, bloque)

    return {
        "operacion": "mover_bloque",
        "bloque_id": op.bloque_id,
        "pagina_id": pagina.get("id"),
        "antes": None,
        "despues": {"pagina_id": pagina.get("id"), "indice": indice,
                    "dentro_de": op.dentro_de},
    }


def _op_insertar_pagina(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    paginas = _paginas(curso)
    # El id debe cumplir ^p[0-9]+$ y la página no admite claves fuera del
    # esquema: nada de marcar aquí que la creó el docente. Eso se sabe por
    # `ediciones_bloque`, que es donde tiene que estar.
    pagina = {
        "id": ensamblado.nuevo_id_pagina(curso),
        "titulo": op.titulo,
        "semana": op.semana if op.semana is not None else len(paginas) + 1,
        "bloques": [],
    }
    if op.unidad_id is not None:
        pagina["unidad_id"] = op.unidad_id

    paginas.insert(min(op.indice, len(paginas)), pagina)
    return {
        "operacion": "insertar_pagina",
        "pagina_id": pagina["id"],
        "antes": None,
        "despues": copy.deepcopy(pagina),
    }


def _op_eliminar_pagina(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    paginas = _paginas(curso)
    for i, pagina in enumerate(paginas):
        if pagina.get("id") == op.pagina_id:
            antes = copy.deepcopy(paginas.pop(i))
            return {
                "operacion": "eliminar_pagina",
                "pagina_id": op.pagina_id,
                "antes": antes,
                "despues": None,
            }
    raise ErrorDeEdicion(f"No existe la página {op.pagina_id!r}.")


def _op_mover_pagina(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    paginas = _paginas(curso)
    for i, pagina in enumerate(paginas):
        if pagina.get("id") == op.pagina_id:
            paginas.pop(i)
            indice = min(op.indice, len(paginas))
            paginas.insert(indice, pagina)
            return {
                "operacion": "mover_pagina",
                "pagina_id": op.pagina_id,
                "antes": {"indice": i},
                "despues": {"indice": indice},
            }
    raise ErrorDeEdicion(f"No existe la página {op.pagina_id!r}.")


def _op_actualizar_pagina(curso: dict[str, Any], op: Any) -> dict[str, Any]:
    pagina = buscar_pagina(curso, op.pagina_id)
    antes = {k: v for k, v in pagina.items() if k != "bloques"}
    if "id" in op.campos and op.campos["id"] != op.pagina_id:
        raise ErrorDeEdicion("El id de una página no se puede cambiar.")
    if "bloques" in op.campos:
        raise ErrorDeEdicion(
            "Los bloques no se cambian con 'actualizar_pagina'. Usa las "
            "operaciones de bloque, que sí quedan auditadas una por una."
        )
    pagina.update(op.campos)
    return {
        "operacion": "actualizar_pagina",
        "pagina_id": op.pagina_id,
        "antes": antes,
        "despues": {k: v for k, v in pagina.items() if k != "bloques"},
    }


_DESPACHO = {
    "actualizar_bloque": _op_actualizar_bloque,
    "eliminar_bloque": _op_eliminar_bloque,
    "insertar_bloque": _op_insertar_bloque,
    "mover_bloque": _op_mover_bloque,
    "insertar_pagina": _op_insertar_pagina,
    "eliminar_pagina": _op_eliminar_pagina,
    "mover_pagina": _op_mover_pagina,
    "actualizar_pagina": _op_actualizar_pagina,
}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def aplicar(
    curso: dict[str, Any], operaciones: list[Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Aplica el lote entero y devuelve (curso nuevo, registros de edición).

    **Trabaja sobre una copia.** Si la operación número 7 falla, el curso
    original no se ha tocado: se propaga la excepción y el llamante no escribe
    nada. Es lo que hace que "todo o nada" sea cierto también dentro del dict,
    no solo en la transacción de la base de datos.
    """
    borrador = copy.deepcopy(curso)
    registros: list[dict[str, Any]] = []

    for numero, op in enumerate(operaciones, start=1):
        funcion = _DESPACHO.get(getattr(op, "operacion", None))
        if funcion is None:
            raise ErrorDeEdicion(f"Operación desconocida: {getattr(op, 'operacion', None)!r}")
        try:
            registros.append(funcion(borrador, op))
        except ErrorDeEdicion as exc:
            raise ErrorDeEdicion(f"Operación {numero} ({op.operacion}): {exc}") from exc

    ensamblado.asignar_recursos(borrador)
    ensamblado.numerar_figuras(borrador)
    borrador["estadisticas"] = ensamblado.calcular_estadisticas(borrador)
    return borrador, registros
