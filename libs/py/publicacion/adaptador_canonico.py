"""Traduce curso.json v1.0.0 al esquema canónico que consume render_ed.py.

Hay dos contratos JSON en el proyecto, y los dos son legítimos:

  curso.json v1.0.0  — lo produce el agente. DECLARA la estructura:
                       unidades, páginas, resultados de aprendizaje.
  esquema_canonico   — lo consume el pipeline de publicación. Nació de
                       docx_a_json, cuando el origen era Word, y por eso
                       INFIERE la estructura de la secuencia de títulos.

render_ed.py y los canvas_*.py son ~2000 líneas ya probadas contra Canvas
real. Reescribirlas para el contrato nuevo costaría días y arriesgaría
romper lo que funciona. Traducir cuesta este archivo.

Va en esta dirección y no al revés porque curso.json tiene MÁS información:
donde el pipeline adivina el título de unidad de un heading que empieza por
"Unidad", aquí está declarado en estructura.unidades[].

Limitaciones conocidas:
  - `caja` no tiene equivalente: se aplana a sus hijos con el título como
    subtítulo. Se pierde el recuadro, no el contenido.
  - Las citas pierden el enlace a la referencia (su `cita` solo tiene texto
    y fuente).
"""
from __future__ import annotations

import re
from typing import Any

SUBTIPOS_VALIDOS = {
    "apuntar", "avancemos", "buscar", "caso", "ejemplo", "ejercicio", "enlace",
    "foro", "importante", "informacion_importante", "lectura", "muy_bien",
    "nota", "observe", "orientacion_actividades", "recuerde", "reflexione",
    "video",
}


def _a_markdown(html: str) -> str:
    """HTML en línea -> Markdown, que es lo que espera el pipeline.

    md_inline() de canvas_llenar_semanas hace esc(s) ANTES de traducir, o sea
    que un <strong> llega a Canvas como texto literal "<strong>". Espera
    Markdown porque venía de Word.

    Se convierte aquí y no allí a propósito: tocar md_inline rompería el caso
    de Word, que sí manda Markdown. El adaptador es el sitio donde los dos
    contratos se encuentran.

    Los enlaces se convierten al formato [texto](url) que md_inline reconoce.
    """
    t = html or ""
    t = re.sub(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", t, flags=re.I | re.S)
    t = re.sub(r"</?(?:strong|b)\s*>", "**", t, flags=re.I)
    t = re.sub(r"</?(?:em|i)\s*>", "*", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", " ", t, flags=re.I)
    # Lo que quede (sub, sup, u) no tiene equivalente en Markdown: se quita la
    # etiqueta y se conserva el texto, que es mejor que mostrarla en crudo.
    t = re.sub(r"<[^>]+>", "", t)
    return t.strip()


def _texto_plano(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _bloque(b: dict[str, Any], contador: dict[str, int]) -> list[dict[str, Any]]:
    """Traduce un bloque. Devuelve LISTA porque `caja` se aplana en varios."""
    tipo = b.get("tipo")

    if tipo == "parrafo":
        return [{"tipo": "parrafo", "texto": _a_markdown(b.get("texto", ""))}]

    if tipo == "encabezado":
        # El pipeline llama "subtitulo" a lo que curso.json llama "encabezado",
        # y de su nivel deduce la jerarquía de subtemas (nivel 2 = subtema 1.x,
        # nivel 3 = sub-subtema). Por eso el nivel se respeta tal cual.
        # En los titulos NO se convierte a Markdown: acaban como etiqueta de
        # pestaña, donde md_inline no llega, y salen los ** en crudo.
        return [{"tipo": "subtitulo", "nivel": int(b.get("nivel", 2)),
                 "texto": _texto_plano(b.get("texto", ""))}]

    if tipo == "lista":
        return [{
            "tipo": "lista",
            "estilo": "numerada" if b.get("ordenada") else "vinetas",
            "items": [_a_markdown(i.get("texto", "")) for i in (b.get("items") or [])],
        }]

    if tipo == "tabla":
        contador["tabla"] += 1
        return [{
            "tipo": "tabla", "numero": contador["tabla"],
            "titulo": b.get("titulo", ""),
            "encabezados": b.get("encabezados", []),
            "filas": [[_a_markdown(c) for c in fila] for fila in b.get("filas", [])],
            "nota": b.get("nota", ""),
        }]

    if tipo == "focalizador":
        subtipo = b.get("focalizador")
        if subtipo not in SUBTIPOS_VALIDOS:
            subtipo = "importante"
        hijos: list[dict[str, Any]] = []
        for h in b.get("bloques") or []:
            hijos.extend(_bloque(h, contador))
        if not hijos:
            return []
        return [{"tipo": "focalizador", "subtipo": subtipo, "contenido": hijos}]

    if tipo == "caja":
        salida: list[dict[str, Any]] = []
        if b.get("titulo"):
            salida.append({"tipo": "subtitulo", "nivel": 4, "texto": b["titulo"]})
        if b.get("texto"):
            salida.append({"tipo": "parrafo", "texto": b["texto"]})
        for h in b.get("bloques") or []:
            salida.extend(_bloque(h, contador))
        return salida

    if tipo == "cita":
        return [{"tipo": "cita", "texto": _a_markdown(b.get("texto", "")),
                 "fuente": b.get("pagina_citada", "")}]

    if tipo in ("imagen", "diagrama"):
        contador["figura"] += 1
        alt = b.get("alt") or "Figura"
        return [{
            "tipo": "figura",
            "numero": b.get("numero_figura") or contador["figura"],
            "titulo": alt, "origen": "imagen",
            # El src lo resuelve mapa_imagenes.json en el pipeline; aquí se
            # deja la ref para que lo cruce.
            "imagen": {"src": b.get("recurso_ref", ""), "alt": alt},
            "nota": "",
        }]

    if tipo == "recurso_ediloja":
        return [{"tipo": "recurso", "titulo": b.get("titulo", ""),
                 "descripcion": b.get("texto") or b.get("titulo", "")}]

    if tipo == "actividades":
        return [{"tipo": "actividad_recomendada",
                 "contenido": [{"tipo": "parrafo", "texto": _a_markdown(b.get("texto", ""))}]}]

    if tipo == "autoevaluacion":
        # No es un bloque en el esquema canónico: es una sección aparte.
        # Lo recoge convertir() y aquí se descarta.
        return []

    if b.get("texto"):
        return [{"tipo": "parrafo", "texto": b["texto"]}]
    return []


# ---------------------------------------------------------------------------
# Los siete apartados del prompt institucional
# ---------------------------------------------------------------------------
# El modelo los emite como encabezados de nivel 2, uno por semana. Pero NO son
# subtemas: son la estructura de la semana que pide la UTPL.
#
# estructurar_semana() no puede distinguirlos y los convierte en pestañas, con
# dos consecuencias: se repiten el resultado de aprendizaje y la
# contextualización (que ya se muestran arriba, en su propia banda), y la
# numeración crece sin freno -- 7 apartados x 8 semanas = 1.44 en la misma
# unidad.
#
# Aquí se colocan en su sitio:
#   - resultado de aprendizaje y contextualización -> se DESCARTAN (duplicados)
#   - contextualización de la semana -> se descarta, la de la unidad ya está
#   - desarrollo de contenidos -> su contenido sube un nivel y se convierte en
#     los subtemas reales, tomando los encabezados de nivel 3 que lleve dentro
#   - estrategias, recursos y cierre -> subtemas propios, que sí lo son

APARTADOS_DESCARTADOS = (
    "resultado de aprendizaje",
    "contextualizacion",
    "contextualización",
)

APARTADO_DESARROLLO = ("desarrollo de contenidos", "contenidos argumentados",
                       "desarrollo de los contenidos")


def _normaliza(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t or "").strip().lower()
    t = re.sub(r"^\d+[.)]?\s*", "", t)          # "1.2. " al principio
    return t.rstrip(" .:")


def _reestructurar_apartados(bloques: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coloca los siete apartados del prompt en la estructura de la semana."""
    # Cada apartado del prompt tiene su sitio en la pagina, y no es una pestaña:
    #   introduccion -> intro, justo bajo el titulo de unidad (antes del ctab)
    #   cierre       -> final_content, tras el contenedor de contenidos
    #   actividad N  -> zona de practica, pestaña "Actividades recomendadas"
    # estructurar_semana ya separa esas tres cosas: lo que va antes del primer
    # h2 es la intro, y los actividad_recomendada los recoge aparte. Aqui solo
    # hay que emitirlos de la forma que reconoce.
    intro: list[dict[str, Any]] = []
    cuerpo: list[dict[str, Any]] = []
    actividades: list[dict[str, Any]] = []
    cierre: list[dict[str, Any]] = []

    destino = cuerpo
    saltando = False

    for b in bloques:
        # Las actividades se detectan en CUALQUIER nivel de encabezado: el
        # modelo las emite como h3 dentro de "Estrategias de aprendizaje", no
        # como apartado propio. Si solo se mirara nivel <= 2 caerian en la
        # rama de subtemas y acabarian como pestañas.
        if b.get("tipo") == "subtitulo" and re.match(
                r"^actividad\s+\d", _normaliza(b.get("texto", ""))):
            actividades.append({"tipo": "actividad_recomendada",
                                "contenido": [{"tipo": "parrafo",
                                               "texto": b.get("texto", "")}]})
            destino = actividades[-1]["contenido"]
            saltando = False
            continue

        if b.get("tipo") == "subtitulo" and int(b.get("nivel", 2)) <= 2:
            titulo = _normaliza(b.get("texto", ""))

            if titulo in APARTADOS_DESCARTADOS:
                # Ya se muestran arriba, en container-learning-outcome.
                saltando = True
                continue

            saltando = False

            if titulo.startswith("introduccion") or titulo.startswith("introducción"):
                destino = intro
                continue

            if titulo.startswith("cierre"):
                destino = cierre
                continue

            if re.match(r"^actividad\s+\d", titulo):
                actividades.append({"tipo": "actividad_recomendada",
                                    "contenido": []})
                destino = actividades[-1]["contenido"]
                continue

            destino = cuerpo

            if titulo in APARTADO_DESARROLLO:
                # El apartado desaparece; lo que lleva dentro son los temas.
                # Sus encabezados de nivel 3 pasan a nivel 2 para que
                # estructurar_semana los tome como subtemas.
                continue

            destino.append(b)
            continue

        if saltando:
            continue

        # Dentro del desarrollo, los h3 se convierten en los subtemas reales.
        if b.get("tipo") == "subtitulo" and int(b.get("nivel", 3)) == 3 and destino is cuerpo:
            texto = b.get("texto", "")
            # El modelo YA numera sus temas ("1.1. Concepto..."). El render
            # antepone la suya y sale "1.2. 1.1. Concepto". Se quita la del
            # modelo: la buena es la del render, que cuenta los subtemas de
            # toda la unidad y no los de esta semana.
            texto = re.sub(r"^\s*\d+(\.\d+)*[.)]?\s*", "", texto)
            destino.append({**b, "nivel": 2, "texto": texto})
            continue

        destino.append(b)

    # El orden importa: la intro va PRIMERO porque estructurar_semana toma
    # como intro todo lo anterior al primer h2. El cierre va al final, ya
    # fuera de las pestañas.
    return intro + cuerpo + cierre + actividades


def _pregunta(p: dict[str, Any]) -> dict[str, Any]:
    opciones = []
    for o in p.get("opciones") or []:
        opciones.append({"letra": o.get("letra", "a"), "texto": o.get("texto", ""),
                         "correcta": o.get("letra") == p.get("correcta")})
    return {
        "numero": p.get("numero") or 1,
        "tipo_pregunta": "opcion_multiple",
        "enunciado": p.get("enunciado", ""),
        "opciones": opciones,
        "respuesta_correcta": p.get("correcta", ""),
        "retroalimentacion": p.get("retroalimentacion", ""),
    }


def convertir(curso: dict[str, Any]) -> dict[str, Any]:
    """curso.json v1.0.0 -> esquema canónico del pipeline de publicación."""
    info = curso.get("info_general", {})
    estructura = curso.get("estructura", {})
    finales = curso.get("finales", {})

    unidades_por_id = {u["id"]: u for u in estructura.get("unidades", [])}
    ras_por_id = {r["id"]: r for r in estructura.get("resultados_aprendizaje", [])}

    contador = {"tabla": 0, "figura": 0}
    unidades_salida: list[dict[str, Any]] = []
    autoevaluaciones: list[dict[str, Any]] = []

    for pagina in estructura.get("paginas", []):
        unidad = unidades_por_id.get(pagina.get("unidad_id"), {})
        numero_unidad = unidad.get("numero", 1)
        bloques: list[dict[str, Any]] = []

        # El pipeline deduce el título de unidad de un subtítulo que empiece
        # por "Unidad". Aquí lo tenemos declarado, así que se emite explícito.
        if unidad.get("titulo"):
            bloques.append({"tipo": "subtitulo", "nivel": 2,
                            "texto": f"Unidad {numero_unidad}. {unidad['titulo']}"})

        for b in pagina.get("bloques", []):
            if b.get("tipo") == "autoevaluacion":
                autoevaluaciones.append({
                    "tipo": "autoevaluacion", "unidad": numero_unidad,
                    "titulo": b.get("titulo") or f"Autoevaluación {numero_unidad}",
                    "instrucciones": "",
                    "preguntas": [_pregunta(p) for p in b.get("preguntas", [])],
                })
                continue
            bloques.extend(_bloque(b, contador))

        bloques = _reestructurar_apartados(bloques)

        unidades_salida.append({
            "numero": numero_unidad,
            "nombre_pagina": f"Semana {pagina.get('semana')}",
            "titulo": pagina.get("titulo", ""),
            "bloques": bloques,
        })

    secciones: list[dict[str, Any]] = [
        {"tipo": "contenido", "titulo": "Contenidos", "unidades": unidades_salida}
    ]
    secciones.extend(autoevaluaciones)

    if finales.get("glosario"):
        secciones.append({"tipo": "glosario", "titulo": "Glosario",
                          "terminos": [{"termino": g["termino"], "definicion": g["definicion"]}
                                       for g in finales["glosario"]]})

    if finales.get("referencias"):
        secciones.append({"tipo": "referencias", "titulo": "Referencias",
                          "entradas": [r.get("apa", "") for r in finales["referencias"]]})

    # render_ed no lee el bloque `resultado_aprendizaje`: plan_outcomes_por_semana
    # busca los RA en data["ras_globales_curados"], una lista con unidad_aplica.
    # Esa clave NO esta en esquema_canonico.schema.json -- la anaden agentes
    # posteriores del pipeline -- pero es la que consume el render, asi que el
    # adaptador la emite. El esquema no es la fuente de verdad completa de lo
    # que render_ed espera.
    ras_globales = []
    for u in estructura.get("unidades", []):
        ra = ras_por_id.get(u.get("resultado_aprendizaje_id"))
        if ra:
            ras_globales.append({
                "unidad_aplica": u.get("numero"),
                # Nombres exactos que lee plan_outcomes_por_semana:
                # "ra" para el texto y "contextualizacion_final" para el
                # parrafo que se muestra SOLO en la semana donde la unidad
                # arranca (el render lleva la cuenta con ctx_mostradas).
                "ra": ra.get("texto", ""),
                "contextualizacion_final": u.get("contextualizacion", ""),
            })

    return {
        "ras_globales_curados": ras_globales,
        "metadata": {
            "asignatura": info.get("asignatura", ""),
            "codigo": info.get("codigo_banner", ""),
            "docente": info.get("autor", ""),
            "nivel": info.get("nivel", ""),
            "periodo": info.get("periodo", ""),
            "canvas_course_id": None,
        },
        "secciones": secciones,
    }
