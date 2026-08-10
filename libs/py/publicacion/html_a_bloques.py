"""Convierte el HTML de un curso migrado en bloques de curso.json v1.0.0.

Por qué se puede hacer con fiabilidad
------------------------------------
El HTML de estos cursos NO es arbitrario: pasó por el migrador, que lo
normalizó a la plantilla institucional. Eso da marcas en las que apoyarse:

    div.ed-container                 la página entera
    section#container-learning-outcome  resultado de aprendizaje + contexto
    div.subtitle-section             título de unidad
    div.ctab                         pestañas de subtema
    div.ctab__panel                  contenido de cada subtema
    div.focuser {tipo}               focalizador, con su tipo en la clase
    figure.container-figure          figura con su pie
    table.table-general              tabla
    div.container-resources          recurso incrustado (iframe)
    section.preliminary-tabs         zona de práctica

Sobre un HTML cualquiera esto sería frágil. Sobre este, es un mapeo directo.

Qué se descarta, y por qué
--------------------------
La navegación entre semanas, el botón de inicio, el pie y los iconos de la
plantilla NO son contenido: los vuelve a poner el render al publicar. Traerlos
como bloques duplicaría el andamiaje y ensuciaría el editor.

Las autoevaluaciones vienen como iframe a un recurso externo, que no se puede
convertir en preguntas. Se marcan como pendientes: el docente decide si las
regenera con el agente.
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

# Etiquetas que el esquema permite dentro de un texto. El resto se desenvuelve
# conservando el contenido: el backend rechaza con 422 cualquier otra.
INLINE_PERMITIDAS = {"strong", "em", "u", "sub", "sup", "a", "br", "b", "i"}

FOCALIZADORES_VALIDOS = {
    "informacion_importante", "orientacion_actividades", "muy_bien", "apuntar",
    "avancemos", "buscar", "caso", "ejemplo", "ejercicio", "enlace", "foro",
    "importante", "lectura", "nota", "observe", "recuerde", "reflexione", "video",
}

# El migrador emite la clase en inglés para los cuatro que DI confirmó.
DESDE_INGLES = {"important": "importante", "reading": "lectura",
                "reflection": "reflexione", "video": "video"}


def _inline(nodo: Tag) -> str:
    """Texto de un nodo conservando solo el marcado permitido."""
    partes: list[str] = []
    for hijo in nodo.children:
        if isinstance(hijo, NavigableString):
            partes.append(str(hijo))
            continue
        if not isinstance(hijo, Tag):
            continue
        etiqueta = hijo.name.lower()
        if etiqueta == "br":
            partes.append("<br>")
        elif etiqueta == "a" and hijo.get("href"):
            partes.append(f'<a href="{hijo["href"]}">{_inline(hijo)}</a>')
        elif etiqueta in INLINE_PERMITIDAS:
            # b -> strong, i -> em: el esquema no admite las cortas.
            nombre = {"b": "strong", "i": "em"}.get(etiqueta, etiqueta)
            partes.append(f"<{nombre}>{_inline(hijo)}</{nombre}>")
        else:
            partes.append(_inline(hijo))
    texto = "".join(partes)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _tipo_focalizador(clases: list[str]) -> str:
    for c in clases:
        if c == "focuser":
            continue
        c = DESDE_INGLES.get(c, c)
        if c in FOCALIZADORES_VALIDOS:
            return c
    return "importante"


def _items(lista: Tag) -> list[dict[str, Any]]:
    salida = []
    for li in lista.find_all("li", recursive=False):
        sub = li.find(["ul", "ol"], recursive=False)
        if sub:
            sub.extract()
        item: dict[str, Any] = {"texto": _inline(li)}
        if sub:
            hijos = [{"texto": _inline(x)} for x in sub.find_all("li", recursive=False)]
            hijos = [h for h in hijos if h["texto"]]
            if hijos:
                item["items"] = hijos
        if item["texto"]:
            salida.append(item)
    return salida


def _tabla(tabla: Tag) -> dict[str, Any] | None:
    encabezados = [_inline(th) for th in tabla.find_all("th")]
    filas = []
    for tr in tabla.find_all("tr"):
        celdas = tr.find_all("td")
        if celdas:
            filas.append([_inline(td) for td in celdas])
    if not filas:
        return None
    if not encabezados:
        # Sin thead, la primera fila hace de encabezado: el esquema lo exige.
        encabezados, filas = filas[0], filas[1:]
    bloque: dict[str, Any] = {"tipo": "tabla", "encabezados": encabezados,
                              "filas": filas}
    caption = tabla.find("caption")
    if caption:
        bloque["titulo"] = _inline(caption)
    return bloque


def _figura(fig: Tag, recursos: list[dict[str, Any]]) -> dict[str, Any] | None:
    img = fig.find("img")
    if img is None:
        return None
    alt = (img.get("alt") or "").strip()
    pie = fig.find("footer")
    if not alt and pie:
        alt = re.sub(r"\s+", " ", pie.get_text(" ", strip=True))[:300]
    if not alt:
        figcap = fig.find("figcaption")
        alt = _inline(figcap) if figcap else ""

    ref = f"r{len(recursos) + 1}"
    recursos.append({
        "ref": ref, "tipo": "imagen",
        "archivo": f"{ref}.png", "mime": "image/png",
        # La URL original queda en generado_por para poder recuperarla: al
        # republicar hay que subir el archivo al curso NUEVO, porque Canvas
        # resuelve permisos por curso y una imagen alojada en otro se ve rota.
        "generado_por": img.get("src", "")[:400],
    })
    bloque: dict[str, Any] = {"tipo": "imagen", "recurso_ref": ref}
    if alt:
        bloque["alt"] = alt
    else:
        bloque["decorativa"] = True
    return bloque


def _bloques_de(nodo: Tag, recursos: list[dict[str, Any]],
                profundidad: int = 1) -> list[dict[str, Any]]:
    """Recorre un contenedor y emite los bloques que encuentra."""
    salida: list[dict[str, Any]] = []

    for hijo in nodo.children:
        if not isinstance(hijo, Tag):
            continue
        clases = hijo.get("class") or []
        etiqueta = hijo.name.lower()

        if "focuser" in clases:
            cuerpo = hijo.find(class_="content-focuser") or hijo
            hijos = _bloques_de(cuerpo, recursos, profundidad + 1)
            # Solo caja y focalizador anidan, y solo un nivel: los nietos se
            # aplanan en vez de perderse.
            hijos = [h for h in hijos if h.get("tipo") != "focalizador"]
            if hijos:
                salida.append({"tipo": "focalizador",
                               "focalizador": _tipo_focalizador(clases),
                               "bloques": hijos})
            continue

        if etiqueta == "figure" or "container-figure" in clases:
            fig = _figura(hijo, recursos)
            if fig:
                salida.append(fig)
            continue

        if etiqueta == "table" or "table-general" in clases or "table-design" in clases:
            tabla = hijo if etiqueta == "table" else hijo.find("table")
            if tabla:
                b = _tabla(tabla)
                if b:
                    salida.append(b)
            continue

        if "container-resources" in clases:
            marco = hijo.find("iframe")
            if marco and marco.get("src"):
                salida.append({"tipo": "recurso_ediloja",
                               "titulo": marco.get("title") or "Recurso interactivo",
                               "url": marco["src"]})
            continue

        if etiqueta in ("h1", "h2", "h3", "h4", "h5", "h6"):
            texto = _inline(hijo)
            if texto:
                # Los temas del curso viejo son h4 dentro de su panel de
                # pestaña. Aqui ya no hay panel, asi que bajan a nivel 2 para
                # que estructurar_semana los vuelva a tomar como subtemas: solo
                # mira nivel 2. Un h5 (sub-subtema) baja a 3.
                # Se conserva la JERARQUIA, no se aplana: en el curso
                # viejo los temas son h4 y los sub-subtemas h5, dentro de su
                # panel de pestaña. Bajar todo a 2 convierte cada uno en una
                # pestaña propia -- 17 en una semana.
                # Un titulo YA es un titulo: el <strong> de dentro solo
                # sirve para que acabe como ** en la etiqueta de la pestaña.
                texto = re.sub(r"</?(?:strong|b|em|i)>", "", texto).strip()

                # La jerarquia real esta en la NUMERACION, no en el nivel: en
                # el curso viejo "1.2." y "1.2.1." son los dos <h4>, y por
                # nivel no se distinguen. Se cuenta la profundidad del numero.
                m = re.match(r"^(\d+(?:\.\d+)*)\.?\s", texto)
                if m:
                    nivel = 2 if m.group(1).count(".") + 1 <= 2 else 3
                else:
                    # Sin numeracion es un subapartad dentro del tema
                    # ("Objetivos de aseguramiento"), nunca una pestaña.
                    nivel = 3
                salida.append({"tipo": "encabezado", "nivel": nivel, "texto": texto})
            continue

        if etiqueta == "p":
            if hijo.find("img") and not hijo.get_text(strip=True):
                continue  # <p> que solo envuelve el icono de un focalizador
            texto = _inline(hijo)
            if texto:
                salida.append({"tipo": "parrafo", "texto": texto})
            continue

        if etiqueta in ("ul", "ol"):
            items = _items(hijo)
            if items:
                salida.append({"tipo": "lista", "ordenada": etiqueta == "ol",
                               "items": items})
            continue

        if etiqueta in ("div", "section", "article", "span"):
            salida.extend(_bloques_de(hijo, recursos, profundidad))
            continue

    return salida


def _texto_de(sopa: BeautifulSoup, id_div: str) -> str:
    div = sopa.find(id=id_div)
    if div is None:
        return ""
    return re.sub(r"\s+", " ", div.get_text(" ", strip=True)).strip()


def pagina_desde_html(html: str, semana: int, unidad_id: str,
                      recursos: list[dict[str, Any]]) -> dict[str, Any]:
    """Una página de curso.json a partir del HTML de una semana."""
    sopa = BeautifulSoup(html or "", "html.parser")
    bloques: list[dict[str, Any]] = []

    titulo_unidad = ""
    sub = sopa.find(class_="subtitle-section")
    if sub:
        titulo_unidad = re.sub(r"\s+", " ", sub.get_text(" ", strip=True)).strip()

    # El contenido vive en las pestañas; lo de fuera es andamiaje.
    for panel in sopa.find_all(class_="ctab__panel"):
        bloques.extend(_bloques_de(panel, recursos))

    # Introducción de la unidad: va antes de las pestañas.
    intro = sopa.find(attrs={"data-origen": "introduccion-fuente"})
    if intro:
        bloques = _bloques_de(intro, recursos) + bloques

    # Actividades recomendadas de la zona de práctica.
    panel_act = sopa.find(id="recommended_activities")
    if panel_act:
        texto = re.sub(r"\s+", " ", panel_act.get_text(" ", strip=True)).strip()
        if len(texto) > 40:
            bloques.append({"tipo": "actividades",
                            "titulo": "Actividades recomendadas",
                            "texto": texto[:4000]})

    pagina: dict[str, Any] = {
        "id": f"p{semana}",
        "semana": semana,
        "titulo": titulo_unidad or f"Semana {semana}",
        "unidad_id": unidad_id,
        "bloques": bloques,
    }
    return pagina


def curso_desde_extraido(extraido: dict[str, Any]) -> dict[str, Any]:
    """curso.json v1.0.0 a partir de la salida de extraer_curso().

    Los campos que no se pueden deducir quedan vacíos a propósito: el código
    Banner, el periodo y el resultado de aprendizaje los pone el docente.
    Rellenarlos con el nombre del curso de Canvas ("Migracion V5") solo
    consigue que nadie se dé cuenta de que están mal.
    """
    recursos: list[dict[str, Any]] = []
    paginas: list[dict[str, Any]] = []
    ra_texto = ""
    ctx_texto = ""
    titulo_unidad = ""

    vistas: set[int] = set()
    for mod in extraido.get("modulos", []):
        for item in mod.get("items", []):
            titulo = (item.get("titulo") or "").strip()
            m = re.match(r"^semana\s+(\d+)", titulo, re.I)
            if not m:
                continue
            semana = int(m.group(1))
            if semana in vistas:
                continue          # extraer_curso puede repetir módulos
            vistas.add(semana)

            html = item.get("html", "")
            if not ra_texto:
                sopa = BeautifulSoup(html, "html.parser")
                ra_texto = _texto_de(sopa, "learning_outcomes")
                ctx_texto = _texto_de(sopa, "contextualization")

            pagina = pagina_desde_html(html, semana, "u1", recursos)
            paginas.append(pagina)
            # El titulo de unidad viene en subtitle-section: "Unidad 1. El
            # espiritu innovador". Se guarda el primero que aparezca; el valor
            # por defecto ("Unidad 1") hace que el render escriba
            # "Unidad 1. Unidad 1".
            if not titulo_unidad and pagina.get("titulo", "").lower().startswith("unidad"):
                titulo_unidad = pagina["titulo"]

    paginas.sort(key=lambda p: p["semana"])

    # Se quita el "Unidad N." del principio: el render lo antepone solo.
    limpio = re.sub(r"^\s*unidad\s+\d+[.:]?\s*", "", titulo_unidad, flags=re.I).strip()
    unidad: dict[str, Any] = {"id": "u1", "numero": 1,
                              "titulo": limpio or "Contenidos",
                              "semana_inicio": 1,
                              "semana_fin": max((p["semana"] for p in paginas), default=1)}
    if len(ctx_texto) >= 50:
        unidad["contextualizacion"] = ctx_texto[:4000]

    estructura: dict[str, Any] = {"unidades": [unidad], "paginas": paginas}
    if len(ra_texto) >= 10:
        estructura["resultados_aprendizaje"] = [
            {"id": "ra1", "numero": 1, "texto": ra_texto[:2000]}]
        unidad["resultado_aprendizaje_id"] = "ra1"

    return {
        "version_esquema": "1.0.0",
        "info_general": {
            "codigo_banner": "SIN-CODIGO",
            "asignatura": extraido.get("nombre", ""),
            "periodo": "",
            # El esquema solo admite 8 o 16, y el validador exige que
            # coincida con el numero de paginas. Un curso viejo de 5 semanas
            # no encaja en ninguno de los dos: se deja el mas cercano y la
            # alerta 'semanas_incompletas' avisa al docente de que hay que
            # completarlo antes de publicar.
            "total_semanas": 8 if len(paginas) <= 8 else 16,
        },
        "estructura": estructura,
        "recursos": recursos,
    }
