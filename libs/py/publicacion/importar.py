"""Importa un curso viejo de Canvas como requerimientos para el agente.

Por qué a requerimientos y no a curso.json
------------------------------------------
El curso viejo es HTML: páginas completas con la maquetación de su plantilla.
Convertirlo a los 12 tipos de bloque exigiría un analizador nuevo, con casos
raros que fallan en silencio.

Y no hace falta. Lo que el agente consume es el `contents` del formulario:
el temario en texto. Así que la importación rellena esos campos a partir del
curso viejo y el flujo sigue siendo el que ya funciona -- generar, editar,
aprobar, publicar -- con la plantilla nueva.

Se pierde el HTML original. Se gana una guía escrita con las reglas
institucionales vigentes, que es lo que se quiere al remigrar.
"""
from __future__ import annotations

import re
from typing import Any

# clasificar() etiqueta por el titulo, y una pagina llamada "Semana 3" cae en
# "otro" aunque sea todo el contenido de la semana. Asi que no se filtra por
# clasificacion: se DESCARTA lo que sabemos que no aporta temario, y entra
# todo lo demas.
#
# Las autoevaluaciones se descartan porque el agente las regenera con sus diez
# preguntas (regla institucional 10); pasarle las viejas solo gastaria tokens.
DESCARTADAS = ("autoevaluacion", "solucionario", "actividad")

# Titulos de paginas que no son temario aunque traigan texto.
TITULOS_IGNORADOS = ("inicio", "datos generales", "anexos", "encuentros en línea",
                     "encuentros en linea", "fuentes y recursos", "autoevaluaciones")


def _es_temario(titulo: str, clasificacion: str | None) -> bool:
    if (clasificacion or "") in DESCARTADAS:
        return False
    return (titulo or "").strip().lower() not in TITULOS_IGNORADOS


def _texto(html: str) -> str:
    """HTML -> texto con los titulos marcados.

    No se intenta reconstruir la estructura: al agente le basta con el temario
    legible. Los h2/h3 se conservan como lineas propias porque de ahi salen
    las unidades y los temas.
    """
    t = html or ""
    t = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<h[1-3][^>]*>(.*?)</h[1-3]>", r"\n\n\1\n", t, flags=re.S | re.I)
    t = re.sub(r"</(?:p|div|li|tr)>", "\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&lt;", "<").replace("&gt;", ">")
          .replace("&aacute;", "á").replace("&eacute;", "é")
          .replace("&iacute;", "í").replace("&oacute;", "ó")
          .replace("&uacute;", "ú").replace("&ntilde;", "ñ"))
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t.strip()


def _referencias(texto: str) -> list[str]:
    """Lineas que son una referencia APA, no parrafos que citan.

    Una referencia EMPIEZA por el apellido y la inicial: "Schumpeter, J.
    (1934). Titulo." Un parrafo que cita lleva el año en medio, y buscar solo
    "(2020)" en una linea larga los pilla todos.
    """
    patron = re.compile(
        r"^[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’-]+,\s+[A-ZÁÉÍÓÚÑ]\.[^\n]{0,200}?"
        r"\(\d{4}[a-z]?\)[^\n]{5,300}$",
        re.M)
    vistas, salida = set(), []
    for linea in patron.findall(texto):
        clave = linea.strip()[:80]
        if clave not in vistas:
            vistas.add(clave)
            salida.append(linea.strip())
    return salida[:40]


def _titulos_de(texto: str) -> list[str]:
    """Los temas de una semana: los encabezados que _texto() dejo en su linea.

    El titulo de la pagina es "Semana 3", que no dice nada del temario. Lo que
    interesa esta dentro, en los h2/h3 numerados: "1.4. Emprendimiento en
    Ecuador".
    """
    salida = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not (5 < len(linea) < 120):
            continue
        # Un tema empieza por su numeracion o es una linea corta sin punto
        # final -- los parrafos acaban en punto y son largos.
        if re.match(r"^\d+(\.\d+)*\.?\s+\S", linea) and not linea.endswith("."):
            salida.append(linea)
    return salida


def _bibliografia_de(extraido: dict[str, Any]) -> list[str]:
    """Referencias de la pagina "Fuentes y recursos".

    Se toma linea a linea y se descartan los encabezados y las lineas cortas.
    No se valida el formato APA: el curso viejo trae de todo -- apellidos con
    guion, comas donde va punto, listas de autores sin inicial -- y filtrar
    por formato perderia referencias buenas. Que las revise el docente.
    """
    paginas = []
    for mod in extraido.get("modulos", []):
        paginas.extend(mod.get("items", []))
    paginas.extend(extraido.get("paginas_sueltas", []))

    salida: list[str] = []
    vistas: set[str] = set()
    for pagina in paginas:
        titulo = (pagina.get("titulo") or "").strip().lower()
        if "fuente" not in titulo and "bibliograf" not in titulo:
            continue
        for linea in _texto(pagina.get("html", "")).splitlines():
            linea = linea.lstrip("- ").strip()
            if len(linea) < 30 or not re.search(r"\(?\d{4}", linea):
                continue
            clave = linea[:60].lower()
            if clave in vistas:
                continue
            vistas.add(clave)
            salida.append(linea)
    return salida[:60]


def requerimientos_desde_curso(extraido: dict[str, Any]) -> dict[str, Any]:
    """Convierte la salida de extraer_curso() en los 12 campos del formulario.

    Lo que no se puede deducir queda vacío: el operador lo completa antes de
    generar. Inventarlo sería peor -- el nivel o la modalidad equivocados
    cambian el tono de toda la guía.
    """
    unidades: dict[str, dict[str, str]] = {}
    todo: list[str] = []

    for mod in extraido.get("modulos", []):
        clave = mod.get("unidad") or mod.get("semana") or mod.get("nombre")
        for item in mod.get("items", []):
            if not _es_temario(item.get("titulo"), item.get("clasificacion")):
                continue
            cuerpo = _texto(item.get("html", ""))
            if len(cuerpo) < 40:
                continue
            titulo = item.get("titulo", "").strip()
            # Deduplicacion por titulo dentro de la unidad: extraer_curso puede
            # devolver el mismo modulo dos veces si el curso los tiene
            # repetidos, y el temario saldria doble.
            grupo = unidades.setdefault(str(clave), {})
            if titulo in grupo:
                continue
            grupo[titulo] = cuerpo
            todo.append(cuerpo)

    for pagina in extraido.get("paginas_sueltas", []):
        if _es_temario(pagina.get("titulo"), pagina.get("clasificacion")):
            cuerpo = _texto(pagina.get("html", ""))
            if len(cuerpo) >= 40:
                todo.append(cuerpo)

    # El temario: un bloque por unidad con sus temas. Es lo que lee
    # extraer_unidades para repartir las semanas.
    partes = []
    for i, (clave, grupo) in enumerate(unidades.items(), start=1):
        temas: list[str] = []
        for titulo, cuerpo in grupo.items():
            propios = _titulos_de(cuerpo)
            # Si la pagina no trae temas numerados dentro, se usa su titulo.
            temas.extend(propios or [titulo])
        partes.append(f"Unidad {i}: {clave}\n" +
                      "\n".join(f"  - {x}" for x in temas))
    contents = "\n\n".join(partes)

    texto_completo = "\n\n".join(todo)

    # Las referencias viven en su propia pagina ("Fuentes y recursos"), no
    # desperdigadas por el temario. Buscarlas ahi da muchos menos falsos
    # positivos que rastrear el texto entero: un parrafo que cita "(2020)"
    # se parece mucho a una referencia y no lo es.
    bibliografia = _bibliografia_de(extraido)
    if not bibliografia:
        bibliografia = _referencias(texto_completo)

    return {
        "subjectName": extraido.get("nombre", ""),
        "subjectCode": "",
        "academicPeriod": "",
        "level": "",
        "modality": "",
        "faculty": "",
        "program": "",
        "weeks": 8,
        "credits": "",
        "learningOutcome": "",
        "contents": contents,
        "methodology": "",
        "bibliography": "\n".join(bibliografia),
        # Trazabilidad: de qué curso salió esto. Sin esto, dentro de un año
        # nadie sabe si una guía es original o remigrada.
        "_origen_migracion": {
            "curso_canvas": extraido.get("curso_id"),
            "nombre": extraido.get("nombre"),
            "extraido": extraido.get("extraido"),
            "modulos": len(extraido.get("modulos", [])),
        },
    }
