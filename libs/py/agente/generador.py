"""El orquestador: convierte los datos de un curso en un `curso.json` completo.

Genera **semana a semana**, no la guía entera de una vez. Tres razones:

1. Una guía completa no cabe cómodamente en una respuesta, y cuando no cabe el
   modelo la trunca a mitad de un JSON, que es el peor fallo posible.
2. Si falla la semana 6, se reintenta la semana 6, no las ocho.
3. Es lo que hace posible `regenerar_pagina()`, que es lo que el docente pulsa
   cuando una semana no le convence. Sus 3 regeneraciones por semana salen de
   aquí.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from libs.py.agente import ensamblado
from libs.py.agente.cliente import RespuestaModelo, llamar_modelo
from libs.py.agente.contexto import entrada_de_semana
from libs.py.agente.normalizar import normalizar_pagina
from libs.py.agente.prompt import (
    ETIQUETAS_INLINE,
    FOCALIZADORES,
    TIPOS_DE_BLOQUE,
    construir_instrucciones,
)

MAX_INTENTOS = 3
VERSION_ESQUEMA = "1.0.0"

# Firma del transporte: lo que hay que suplantar en los tests.
TipoLlamador = Callable[[str, str], RespuestaModelo]


def _como_dict(resultado: Any) -> dict[str, Any]:
    """El validador devuelve un `Resultado`; el documento necesita un dict."""
    if hasattr(resultado, "como_dict"):
        return resultado.como_dict()
    return resultado if isinstance(resultado, dict) else {"semaforo": "desconocido"}


class ErrorDeGeneracion(RuntimeError):
    """La página no se pudo generar tras agotar los reintentos."""


# ---------------------------------------------------------------------------
# Extracción y comprobación de la respuesta del modelo
# ---------------------------------------------------------------------------

_VALLA = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extraer_json(texto: str) -> dict[str, Any]:
    """Saca el objeto JSON de la respuesta, aunque venga con adornos.

    El prompt pide JSON pelado, pero los modelos a veces envuelven en vallas de
    código o añaden una frase de cortesía. Perdonamos eso: es barato de arreglar
    aquí y caro de arreglar con un reintento.
    """
    candidato = texto.strip()

    valla = _VALLA.search(candidato)
    if valla:
        candidato = valla.group(1).strip()

    if not candidato.startswith("{"):
        inicio = candidato.find("{")
        fin = candidato.rfind("}")
        if inicio == -1 or fin == -1 or fin <= inicio:
            raise ValueError("La respuesta no contiene ningún objeto JSON.")
        candidato = candidato[inicio : fin + 1]

    try:
        datos = json.loads(candidato)
    except json.JSONDecodeError as exc:
        # Distinguir "el modelo escribe mal JSON" de "la respuesta se corto".
        # Son causas distintas: la primera se arregla afinando el prompt, la
        # segunda subiendo MAX_TOKENS_AGENTE. Decir siempre "JSON mal formado"
        # manda a depurar el prompt cuando el problema es de configuracion.
        recortado = candidato.rstrip()
        truncado = bool(recortado) and not recortado.endswith(("}", "]"))
        if truncado:
            raise ValueError(
                f"Respuesta truncada a {len(candidato)} caracteres: el modelo "
                f"agoto max_tokens antes de cerrar el JSON. Sube "
                f"MAX_TOKENS_AGENTE. ({exc})"
            ) from exc
        raise ValueError(f"JSON mal formado: {exc}") from exc

    if not isinstance(datos, dict):
        # ValueError a propósito: generar_pagina() captura ValueError para
        # reintentar. Un TypeError se escaparía y abortaría la generación.
        raise ValueError("El JSON de la respuesta no es un objeto.")  # noqa: TRY004
    return datos


_ETIQUETA = re.compile(r"<\s*/?\s*([a-zA-Z0-9]+)")


def _etiquetas_prohibidas(valor: Any) -> set[str]:
    if not isinstance(valor, str):
        return set()
    return {e.lower() for e in _ETIQUETA.findall(valor)} - set(ETIQUETAS_INLINE)


def _comprobar_pagina(pagina: dict[str, Any]) -> list[str]:
    """Comprobaciones baratas sobre lo que devolvió el modelo.

    Esto NO es el validador institucional de `libs/py/esquema/validador.py`.
    Aquel juzga la guía completa contra las reglas de negocio y produce un
    semáforo para el revisor. Esto de aquí solo comprueba que la respuesta del
    modelo es aprovechable, y su salida se le devuelve al propio modelo como
    corrección. Son dos trabajos distintos y por eso son dos funciones
    distintas.
    """
    errores: list[str] = []

    if not isinstance(pagina.get("titulo"), str) or not pagina["titulo"].strip():
        errores.append("Falta el campo 'titulo' o está vacío.")

    bloques = pagina.get("bloques")
    if not isinstance(bloques, list) or not bloques:
        errores.append("Falta el campo 'bloques' o está vacío.")
        return errores

    def revisar(bloque: Any, nivel: int) -> None:
        if not isinstance(bloque, dict):
            errores.append("Hay un elemento de 'bloques' que no es un objeto.")
            return

        tipo = bloque.get("tipo")
        if tipo not in TIPOS_DE_BLOQUE:
            errores.append(
                f"Tipo de bloque no permitido: {tipo!r}. "
                f"Permitidos: {', '.join(TIPOS_DE_BLOQUE)}."
            )

        if tipo == "focalizador":
            variante = bloque.get("focalizador")
            if variante not in FOCALIZADORES:
                errores.append(
                    f"Focalizador con valor no permitido: {variante!r}. "
                    f"Permitidos: {', '.join(FOCALIZADORES)}."
                )

        for clave, valor in bloque.items():
            if clave == "bloques":
                continue
            sobran = _etiquetas_prohibidas(valor)
            if sobran:
                errores.append(
                    f"Etiquetas HTML no permitidas en '{clave}': "
                    f"{', '.join(sorted(sobran))}. "
                    f"Solo se admiten: {', '.join(ETIQUETAS_INLINE)}."
                )

        hijos = bloque.get("bloques")
        if isinstance(hijos, list):
            if tipo not in ensamblado.CONTENEDORES:
                errores.append(
                    f"El bloque de tipo {tipo!r} no puede contener otros bloques. "
                    f"Solo pueden: {', '.join(ensamblado.CONTENEDORES)}."
                )
            elif nivel >= 1:
                errores.append(
                    "Anidamiento de más de un nivel. Un bloque dentro de una caja "
                    "o un focalizador no puede contener a su vez otros bloques."
                )
            else:
                for hijo in hijos:
                    revisar(hijo, nivel + 1)

    for bloque in bloques:
        revisar(bloque, 0)

    return errores


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------


def _esqueleto(datos_curso: dict[str, Any]) -> dict[str, Any]:
    """El curso.json vacío sobre el que se cuelgan las páginas.

    La raíz tiene `additionalProperties: false`, así que aquí no cabe nada que
    el esquema no declare. Ni telemetría, ni claves de conveniencia: cualquier
    extra hace que el documento se rechace entero.
    """
    return {
        "version_esquema": VERSION_ESQUEMA,
        "info_general": {
            "codigo_banner": datos_curso.get("codigo_banner", ""),
            "asignatura": datos_curso.get("asignatura", ""),
            "periodo": datos_curso.get("periodo", ""),
            "total_semanas": int(datos_curso.get("total_semanas", 0)),
        },
        "estructura": {
            # El learningOutcome del formulario llega aqui como
            # resultados_aprendizaje[]. Sin esta linea el dato que escribe el
            # docente se pierde y la guia se publica sin resultado de
            # aprendizaje, que es lo primero que revisa DI.
            "resultados_aprendizaje": list(datos_curso.get("resultados_aprendizaje", [])),
            "unidades": list(datos_curso.get("unidades", [])),
            "paginas": [],
        },
        "recursos": [],
    }


def generar_pagina(
    *,
    datos_curso: dict[str, Any],
    semana: int,
    pagina_id: str | None = None,
    unidad_id: str | None = None,
    tema: str | None = None,
    bibliografia: list[str] | None = None,
    pagina_previa: dict[str, Any] | None = None,
    cierra_unidad: bool = False,
    llamador: TipoLlamador = llamar_modelo,
    max_intentos: int = MAX_INTENTOS,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Genera una sola página (semana), reintentando si la salida no sirve.

    Devuelve la página y la telemetría de tokens. `llamador` está ahí para
    poder inyectar un modelo simulado en los tests: es lo que permite probar
    toda la lógica de reintentos sin gastar una sola llamada real.
    """
    instrucciones = construir_instrucciones()
    telemetria = {"intentos": 0, "tokens_entrada": 0, "tokens_salida": 0}
    error_previo: str | None = None
    ultimos_errores: list[str] = []

    for intento in range(1, max_intentos + 1):
        telemetria["intentos"] = intento

        contenido = entrada_de_semana(
            datos_curso=datos_curso,
            semana=semana,
            unidad_id=unidad_id,
            tema=tema,
            bibliografia=bibliografia,
            pagina_previa=pagina_previa,
            cierra_unidad=cierra_unidad,
            error_previo=error_previo,
        )

        respuesta = llamador(instrucciones, contenido)
        telemetria["tokens_entrada"] += respuesta.tokens_entrada
        telemetria["tokens_salida"] += respuesta.tokens_salida

        try:
            pagina = _extraer_json(respuesta.texto)
        except ValueError as exc:
            error_previo = str(exc)
            ultimos_errores = [error_previo]
            continue

        # Traducir las variantes del modelo ANTES de comprobar. `contenido` en
        # vez de `bloques`, listas de cadenas, `pregunta` en vez de
        # `enunciado`: son sinonimos inequivocos y rechazar la pagina por eso
        # cuesta un reintento de minutos para volver a jugar a los dados.
        pagina = normalizar_pagina(pagina)

        errores = _comprobar_pagina(pagina)
        if not errores:
            # El modelo devuelve titulo y bloques; todo lo demás lo pone el
            # código. Se filtra a las claves que el esquema permite en una
            # página, porque `additionalProperties` es false y una clave de más
            # inventada por el modelo tumbaría el documento entero.
            limpia: dict[str, Any] = {
                "id": pagina_id or f"p{semana}",
                "titulo": pagina.get("titulo", ""),
                "semana": semana,
                "bloques": pagina["bloques"],
            }
            if unidad_id is not None:
                limpia["unidad_id"] = unidad_id
            if cierra_unidad:
                limpia["cierra_unidad"] = True
            ensamblado.poner_ids_y_origen(limpia["bloques"], origen="agente")
            return limpia, telemetria

        ultimos_errores = errores
        error_previo = "\n".join(f"- {e}" for e in errores)

    raise ErrorDeGeneracion(
        f"La semana {semana} no se pudo generar tras {max_intentos} intentos. "
        f"Últimos errores: {'; '.join(ultimos_errores)}"
    )


def generar_guia(
    datos_curso: dict[str, Any],
    *,
    plan: list[dict[str, Any]] | None = None,
    bibliografia: list[str] | None = None,
    llamador: TipoLlamador = llamar_modelo,
    validar: Callable[[dict[str, Any]], Any] | None = None,
    avisar: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Genera la guía completa, semana a semana.

    `plan` es la lista de qué generar en cada semana:
        [{"semana": 1, "unidad": 1, "tema": "...", "cierra_unidad": False}, ...]
    Si no se pasa, se deduce uno plano a partir de `datos_curso["semanas"]`.

    `validar` es el **único punto de contacto con el validador institucional**.
    Por defecto se importa de `libs.py.esquema.validador`. Está inyectado para
    que los tests no dependan de él y para que, si su firma cambia, solo haya
    que tocar aquí.
    """
    if validar is None:
        from libs.py.esquema.validador import validar as validar  # noqa: PLC0414

    total = int(datos_curso.get("total_semanas", 0))
    if plan is None:
        plan = [{"semana": n} for n in range(1, total + 1)]

    curso = _esqueleto(datos_curso)
    telemetria_total = {"intentos": 0, "tokens_entrada": 0, "tokens_salida": 0}
    previa: dict[str, Any] | None = None
    total_pasos = len(plan)

    for indice, paso in enumerate(plan, start=1):
        pagina, telemetria = generar_pagina(
            datos_curso=datos_curso,
            semana=paso["semana"],
            pagina_id=paso.get("pagina_id"),
            unidad_id=paso.get("unidad_id"),
            tema=paso.get("tema"),
            bibliografia=bibliografia,
            pagina_previa=previa,
            cierra_unidad=bool(paso.get("cierra_unidad")),
            llamador=llamador,
        )
        ensamblado.paginas_de(curso).append(pagina)
        previa = pagina
        for clave in telemetria_total:
            telemetria_total[clave] += telemetria[clave]

        # Aviso de avance. Se pasa una funcion en vez de escribir en la base
        # aqui: este modulo no importa SQLAlchemy por ninguna parte y no debe
        # empezar ahora. El worker le pasa una que hace el commit; los tests
        # no pasan nada y el bucle sigue igual.
        if avisar is not None:
            avisar(indice, total_pasos)

    ensamblado.asignar_recursos(curso)
    ensamblado.numerar_figuras(curso)
    curso["estadisticas"] = ensamblado.calcular_estadisticas(curso)

    # La validación se guarda en `validaciones`, que es la clave que declara el
    # esquema. La telemetría NO va dentro del documento: la raíz no admite
    # claves extra, así que se devuelve aparte y el llamante la guarda en
    # `solicitudes_generacion`, que es su sitio.
    resultado = validar(curso)
    curso["validaciones"] = _como_dict(resultado)
    return curso, telemetria_total


def regenerar_pagina(
    curso: dict[str, Any],
    semana: int,
    *,
    datos_curso: dict[str, Any] | None = None,
    tema: str | None = None,
    bibliografia: list[str] | None = None,
    llamador: TipoLlamador = llamar_modelo,
    validar: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Sustituye una sola semana sin tocar el resto de la guía.

    Es lo que hay detrás del botón de regenerar del docente. Las figuras se
    renumeran enteras después, porque si la semana nueva trae una imagen más
    que la vieja, toda la numeración posterior se desplaza.
    """
    if validar is None:
        from libs.py.esquema.validador import validar as validar  # noqa: PLC0414

    paginas = ensamblado.paginas_de(curso)
    indice = next((i for i, p in enumerate(paginas) if p.get("semana") == semana), None)
    if indice is None:
        raise ValueError(f"La guía no tiene ninguna semana {semana}.")

    antigua = paginas[indice]
    previa = paginas[indice - 1] if indice > 0 else None

    nueva, telemetria = generar_pagina(
        datos_curso=datos_curso or curso.get("info_general", {}),
        semana=semana,
        pagina_id=antigua.get("id"),
        unidad_id=antigua.get("unidad_id"),
        tema=tema,
        bibliografia=bibliografia,
        pagina_previa=previa,
        cierra_unidad=bool(antigua.get("cierra_unidad")),
        llamador=llamador,
    )

    paginas[indice] = nueva
    ensamblado.asignar_recursos(curso)
    ensamblado.numerar_figuras(curso)
    curso["estadisticas"] = ensamblado.calcular_estadisticas(curso)
    curso["validaciones"] = _como_dict(validar(curso))
    return curso, telemetria
