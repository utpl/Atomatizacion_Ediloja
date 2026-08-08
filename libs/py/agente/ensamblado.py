"""La contabilidad.

Regla de oro: **el modelo genera contenido, nuestro código lleva la contabilidad.**
Ids, numeración de semanas y figuras y estadísticas los pone este módulo.

Todo el acceso al `curso.json` pasa por las funciones de este archivo. Si el
esquema se mueve, se toca aquí y en ningún otro sitio. Los nombres de clave
siguen `packages/esquemas/curso.schema.json` v1.0.0:

    raíz → version_esquema, info_general, secciones, estructura, finales,
           recursos, validaciones, estadisticas   (additionalProperties: FALSE)
    estructura → unidades[], paginas[]
    pagina → id (^p[0-9]+$), semana, titulo, unidad_id, cierra_unidad, bloques[]
    bloque → id (^b[0-9a-z]{6,}$), tipo, ..., bloques[]  ← los hijos van aquí
"""

from __future__ import annotations

import uuid
from typing import Any

# Claves del curso.json v1.0.0.
CLAVE_ESTRUCTURA = "estructura"
CLAVE_PAGINAS = "paginas"
CLAVE_UNIDADES = "unidades"
CLAVE_BLOQUES = "bloques"  # sirve para la página Y para los hijos de un bloque
CLAVE_RECURSOS = "recursos"
CLAVE_INFO = "info_general"

ORIGENES = ("agente", "docente", "mixto")
CONTENEDORES = ("caja", "focalizador")
NUMERABLES = ("imagen", "diagrama")


# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------


def paginas_de(curso: dict[str, Any]) -> list[dict[str, Any]]:
    """Las páginas viven en `estructura.paginas`, no en la raíz."""
    return curso.setdefault(CLAVE_ESTRUCTURA, {}).setdefault(CLAVE_PAGINAS, [])


def unidades_de(curso: dict[str, Any]) -> list[dict[str, Any]]:
    return curso.setdefault(CLAVE_ESTRUCTURA, {}).setdefault(CLAVE_UNIDADES, [])


def hijos_de(bloque: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Los bloques anidados van en `bloques`, solo en caja y focalizador."""
    if bloque.get("tipo") not in CONTENEDORES:
        return None
    hijos = bloque.get(CLAVE_BLOQUES)
    return hijos if isinstance(hijos, list) else None


def bloques_de_pagina(pagina: dict[str, Any]) -> list[dict[str, Any]]:
    """Bloques de una página, aplanados: contenedores y sus hijos."""
    aplanados: list[dict[str, Any]] = []
    for bloque in pagina.get(CLAVE_BLOQUES, []):
        aplanados.append(bloque)
        hijos = hijos_de(bloque)
        if hijos:
            aplanados.extend(hijos)
    return aplanados


def todos_los_bloques(curso: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for p in paginas_de(curso) for b in bloques_de_pagina(p)]


# ---------------------------------------------------------------------------
# Identificadores
# ---------------------------------------------------------------------------


def nuevo_id_bloque() -> str:
    """Id de bloque. El esquema exige el patrón ^b[0-9a-z]{6,}$.

    uuid4 en hexadecimal cumple (solo 0-9a-f) y no colisiona entre procesos,
    que es lo que hace falta porque el worker corre en varios.
    """
    return f"b{uuid.uuid4().hex[:12]}"


def nuevo_id_pagina(curso: dict[str, Any]) -> str:
    """Id de página. El esquema exige ^p[0-9]+$: solo dígitos, no vale hex.

    Se calcula como "el mayor que haya + 1" y no "cuántas hay + 1", porque si
    se borró una página intermedia el conteo reutilizaría un id vivo y dos
    páginas distintas acabarían con el mismo.
    """
    usados = [
        int(p["id"][1:])
        for p in paginas_de(curso)
        if isinstance(p.get("id"), str) and p["id"][1:].isdigit()
    ]
    return f"p{max(usados, default=0) + 1}"


def nuevo_id_unidad(curso: dict[str, Any]) -> str:
    """Id de unidad. Patrón ^u[0-9]+$."""
    usados = [
        int(u["id"][1:])
        for u in unidades_de(curso)
        if isinstance(u.get("id"), str) and u["id"][1:].isdigit()
    ]
    return f"u{max(usados, default=0) + 1}"


def poner_ids_y_origen(
    bloques: list[dict[str, Any]], origen: str = "agente"
) -> list[dict[str, Any]]:
    """Asigna id y origen a cada bloque y a sus hijos.

    Respeta lo que ya exista: es lo que permite que una edición del docente
    conserve la identidad del bloque y que `ediciones_bloque` apunte a algo
    estable.
    """
    if origen not in ORIGENES:
        raise ValueError(f"origen no válido: {origen!r}. Debe ser uno de {ORIGENES}.")

    for bloque in bloques:
        bloque.setdefault("id", nuevo_id_bloque())
        bloque.setdefault("origen", origen)
        hijos = hijos_de(bloque)
        if hijos:
            for hijo in hijos:
                hijo.setdefault("id", nuevo_id_bloque())
                hijo.setdefault("origen", origen)
    return bloques


# ---------------------------------------------------------------------------
# Numeración y estadísticas
# ---------------------------------------------------------------------------


def asignar_recursos(curso: dict[str, Any]) -> dict[str, Any]:
    """Da de alta en `recursos[]` una entrada por cada figura y la referencia.

    El esquema exige `recurso_ref` en imagen y diagrama. El modelo NO lo
    inventa —le pedimos explícitamente que no lo haga— así que lo asigna el
    código: el archivo todavía no existe, pero la referencia sí, y eso es lo
    que permite que el documento valide antes de que se generen las imágenes.
    """
    recursos = curso.setdefault(CLAVE_RECURSOS, [])
    existentes = {r.get("ref") for r in recursos}
    contador = len(recursos)

    for bloque in todos_los_bloques(curso):
        if bloque.get("tipo") not in NUMERABLES:
            continue
        if bloque.get("recurso_ref") in existentes:
            continue
        contador += 1
        ref = f"r{contador}"
        while ref in existentes:
            contador += 1
            ref = f"r{contador}"
        bloque["recurso_ref"] = ref
        existentes.add(ref)
        recursos.append({
            "ref": ref,
            "tipo": "imagen" if bloque["tipo"] == "imagen" else "diagrama",
            "archivo": f"{ref}.svg" if bloque["tipo"] == "diagrama" else f"{ref}.png",
            "mime": "image/svg+xml" if bloque["tipo"] == "diagrama" else "image/png",
        })
    return curso


def numerar_figuras(curso: dict[str, Any]) -> dict[str, Any]:
    """Numera imágenes y diagramas correlativos en todo el curso.

    Global y no por página: es el estilo editorial de EdiLoja ("Figura 12" en
    la semana 5). Se recalcula entera cada vez, así que regenerar o editar una
    semana intermedia renumera lo posterior sin dejar huecos.
    """
    contador = 0
    for pagina in paginas_de(curso):
        for bloque in bloques_de_pagina(pagina):
            if bloque.get("tipo") in NUMERABLES:
                contador += 1
                bloque["numero_figura"] = contador
    return curso


def calcular_estadisticas(curso: dict[str, Any]) -> dict[str, Any]:
    """Las cinco cifras del esquema, más el desglose por origen.

    `por_origen` y `por_tipo` no están en el esquema, pero `estadisticas` es el
    único objeto del documento que admite propiedades extra. Y `por_origen` es
    la métrica más útil que hay: cuánto reescribe el docente lo que generó la
    IA. Sin ella no se puede saber si el agente está mejorando.
    """
    paginas = paginas_de(curso)
    bloques = todos_los_bloques(curso)

    por_origen: dict[str, int] = {}
    por_tipo: dict[str, int] = {}
    for bloque in bloques:
        origen = bloque.get("origen", "desconocido")
        por_origen[origen] = por_origen.get(origen, 0) + 1
        tipo = bloque.get("tipo", "desconocido")
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1

    return {
        "total_paginas": len(paginas),
        "total_unidades": len(unidades_de(curso)),
        "total_autoevaluaciones": por_tipo.get("autoevaluacion", 0),
        "total_citas": por_tipo.get("cita", 0),
        "total_recursos": len(curso.get(CLAVE_RECURSOS, [])),
        "por_tipo": dict(sorted(por_tipo.items())),
        "por_origen": dict(sorted(por_origen.items())),
    }
