#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_llenar_semanas.py — Llena las páginas de Semana en Canvas con HTML
alineado al THEME GLOBAL del Canvas de UTPL (clases cc-*).

REGLAS DE NEGOCIO (acordadas con el equipo):
  - Resultados de Aprendizaje + Contextualización: van JUNTOS, son inseparables.
    Solo aparecen en la PRIMERA semana de cada unidad académica. Si la guía solo
    trae un resultado general, va solo en Semana 1.
  - Encuentros en Línea: NO se renderiza (decisión institucional).
  - Subtemas (1.1, 1.2, ...) se renderizan como TABS verticales del theme cc-*.
  - Sub-subtemas (1.1.1, ...) van como h4 DENTRO del tab del subtema.
  - Actividades Recomendadas: provienen del bloque `actividad_recomendada` del
    JSON (marca propia, no focalizador). El contenido puede estar vacío.
  - Autoevaluación: una por unidad académica, solo en la ÚLTIMA semana de la unidad.
  - Actividad Evaluada: espacio neutro (gestionado desde el libro de calificaciones).
  - Marca UTPL, footer, pager, nav entre semanas y toggle de tema:
    los carga el theme global del curso. NO se generan en el HTML.

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="tu-token"
    python canvas_llenar_semanas.py salida.json --curso 89932 --semana 1
"""

import argparse
import html
import json
import os
import re
import sys


# URL base del servidor donde viven los recursos de autoevaluación que se
# embeben vía <iframe>. El recurso de la unidad N es:
#     <BASE_RECURSOS>/autoevaluacion_N.html
# Nota: se usa https porque Canvas corre en https y bloquea iframes http
# (mixed content). Si el servidor de recursos solo expone http, ajústalo con
# --base-recursos, pero el iframe no cargará dentro de Canvas hasta tener https.
BASE_RECURSOS_DEFAULT = "https://www.ediloja.com/recursos/2026-1/pruebas"


# ============================================================
# Utilidades
# ============================================================

def esc(s):
    return html.escape(s or "", quote=True)


def md_inline(s):
    s = esc(s or "")
    s = re.sub(r"\[([^\]]+)\]\((https?:[^)]+)\)",
               r'<a class="cc-link" href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*\*([^*]+)\*\*\*", r"<strong><em>\1</em></strong>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def youtube_id(url):
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)"
                  r"([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


def slug(t):
    s = re.sub(r"[^a-z0-9]+", "-", (t or "").lower()).strip("-")
    return s[:40] or "x"


# ============================================================
# Render de bloques (sin headings — el outer maneja la jerarquía)
# ============================================================

def render_bloque(b, imagenes=None):
    t = b.get("tipo")
    if t == "parrafo":
        return "<p>%s</p>" % md_inline(b.get("texto", ""))
    if t == "subtitulo":
        # Subtítulos internos (nivel 4+ que cayeron dentro de un sub-subtema)
        # se rendrizan como H5; nivel 5+ como H6.
        nivel = b.get("nivel", 4)
        tag = "h5" if nivel <= 4 else "h6"
        return "<%s>%s</%s>" % (tag, md_inline(b.get("texto", "")), tag)
    if t == "lista":
        tag = "ol" if b.get("estilo") == "numerada" else "ul"
        items = "".join("<li>%s</li>" % md_inline(i) for i in b.get("items", []))
        return "<%s>%s</%s>" % (tag, items, tag)
    if t == "idea_clave":
        return (
            '<div style="background:#eef5ff;border-left:4px solid #2e75b6;'
            'padding:10px 14px;margin:10px 0;border-radius:4px">'
            '<strong>Idea clave:</strong> %s</div>'
        ) % md_inline(b.get("texto", ""))
    if t == "cita":
        return "<blockquote>%s</blockquote>" % md_inline(b.get("texto", ""))
    if t == "enlace":
        return ('<p>🔗 <a class="cc-link" href="%s" target="_blank" rel="noopener">%s</a></p>'
                % (esc(b.get("url", "")), esc(b.get("texto") or b.get("url") or "")))
    if t == "video":
        url = b.get("url") or ""
        titulo = b.get("titulo") or "Video"
        vid = youtube_id(url)
        if vid:
            return ('<p><iframe src="https://www.youtube.com/embed/%s" width="640" '
                    'height="360" allowfullscreen title="%s" '
                    'style="max-width:100%%;"></iframe></p>') % (esc(vid), esc(titulo))
        return ('<p>🎬 <a class="cc-link" href="%s" target="_blank" rel="noopener">%s</a></p>'
                % (esc(url), esc(titulo)))
    if t == "recurso":
        descripcion = b.get("descripcion", "").strip()
        formato = (b.get("formato") or "").lower()

        # Quitar prefijos redundantes que el docente suele escribir en el Word.
        # Ej.: "Recurso interactivo - 🎥 Video animado: ..."
        #      "Recurso de aprendizaje - Teórico + aplicado: 🎥 Video..."
        prefijos = [
            r"^Recurso\s+interactivo\s*[-–—:]\s*",
            r"^Recurso\s+de\s+aprendizaje\s*[-–—:]\s*",
            r"^Recurso\s+complementario\s*[-–—:]\s*",
            r"^Recurso\s+did[áa]ctico\s*[-–—:]\s*",
            r"^Recurso\s+adicional\s*[-–—:]\s*",
            r"^Recurso\s*[-–—:]\s*",
        ]
        for pat in prefijos:
            nuevo = re.sub(pat, "", descripcion, flags=re.IGNORECASE)
            if nuevo != descripcion:
                descripcion = nuevo.strip()
                break

        # También limpiar "Teórico + aplicado:" u otras categorizaciones internas
        descripcion = re.sub(r"^(?:Te[óo]rico|Pr[áa]ctico)\s*\+\s*aplicado\s*:\s*",
                             "", descripcion, flags=re.IGNORECASE).strip()

        # Elegir emoji según formato
        iconos = {
            "video": "🎥",
            "quiz": "📝",
            "lectura": "📖",
            "lectura_complementaria": "📖",
            "podcast": "🎧",
            "simulacion": "🎮",
            "interactivo": "🖱️",
            "infografia": "📊",
            "enlace": "🔗",
        }
        icono = iconos.get(formato, "📎")

        # Si la descripción ya empieza con un emoji (típicamente el docente lo
        # puso al editar el Word), no duplicar el icono del prefijo.
        # Detectamos emoji como cualquier char no-ASCII en posición 0.
        primer_char = descripcion[:1]
        if primer_char and ord(primer_char) > 127 and not primer_char.isalnum():
            etiqueta_prefijo = "Recurso:"
        else:
            etiqueta_prefijo = "%s Recurso:" % icono

        return ('<div class="cc-recurso" '
                'style="background:#eff6ff;border-left:4px solid #1F4E79;'
                'padding:12px 16px;margin:12px 0;border-radius:4px;">'
                '<strong style="color:#1F4E79;">%s</strong> %s</div>'
                % (etiqueta_prefijo, md_inline(descripcion)))
    if t == "focalizador":
        nombres = {
            "reflexione": "Deténgase y reflexione",
            "importante": "Importante",
            "ejemplo": "Ejemplo",
            "ejercicio": "Ejercicio",
            "lectura": "Lectura recomendada",
            "informacion_importante": "Información importante",
            "recuerde": "Recuerde",
            "orientacion_actividades": "Orientación de actividades",
            "idea_clave_focal": "Idea clave",
            "invitacion_explorar": "Los invito a explorar",
            "cierre_reflexivo": "Cierre reflexivo",
            "apoyo_visual": "Apoyo visual del aprendizaje",
            "orientacion": "Orientación",
        }
        contenido = b.get("contenido", [])
        if not contenido:
            return ""
        nombre = nombres.get(b.get("subtipo"), (b.get("subtipo") or "").replace("_", " ").title())

        # Filtrar el primer párrafo si es la misma frase del encabezado del foco
        # (el docente a veces lo escribe explícitamente además del marcador).
        contenido_limpio = []
        primera_filtrada = False
        nombre_norm = re.sub(r"[^\w\s]", "", nombre.lower()).strip()
        for c in contenido:
            if (not primera_filtrada
                    and c.get("tipo") == "parrafo"):
                txt_norm = re.sub(r"\*+|[^\w\s]", "",
                                  (c.get("texto") or "").lower()).strip()
                if txt_norm == nombre_norm:
                    primera_filtrada = True
                    continue
            contenido_limpio.append(c)

        # Detectar recursos embebidos como párrafos: si un párrafo empieza con
        # "Recurso ..." (interactivo, didáctico, complementario, etc.), tratarlo
        # como bloque recurso para mantener el estilo consistente.
        contenido_final = []
        for c in contenido_limpio:
            if c.get("tipo") == "parrafo":
                txt = (c.get("texto") or "").strip()
                # patrón típico: "Recurso interactivo 🧩 Unir con líneas..."
                if re.match(r"^Recurso\s+(interactivo|did[áa]ctico|complementario|de\s+aprendizaje|audiovisual|visual)",
                            txt, re.I):
                    contenido_final.append({"tipo": "recurso", "descripcion": txt})
                    continue
            contenido_final.append(c)

        inner = "".join(render_bloque(x, imagenes) for x in contenido_final)
        if not inner.strip():
            return ""
        return (
            '<div style="background:#f4f4f4;border-left:4px solid #888;'
            'padding:10px 14px;margin:10px 0;border-radius:4px">'
            '<p style="margin:0 0 6px 0;font-weight:bold;color:#444">%s</p>'
            '%s</div>'
        ) % (esc(nombre), inner)
    if t == "figura":
        return render_figura(b, imagenes)
    if t == "tabla":
        return render_tabla(b)
    return ""


def render_figura(b, imagenes):
    """imagenes: dict {nombre_archivo: {file_id, preview_url, download_url}}
    o set (legacy). Devuelve HTML con URL embebible de Canvas cuando esté
    disponible, o placeholder rojo si no.

    Estrategia para resolver la URL de la imagen:
      1. Si imagen.src es URL absoluta -> usar tal cual.
      2. Si imagen.src es ruta local Y el nombre está en el mapa -> usar preview_url.
      3. Si imagen.src está vacío Y la figura tiene número, intentar buscar
         'Figura_N.png', 'Figura_N.jpeg', 'Figura_N_b.png', etc. en el mapa.
      4. Si nada funciona -> placeholder rojo.
    """
    num = b.get("numero")
    titulo = b.get("titulo") or ""
    nota = b.get("nota") or ""
    src = (b.get("imagen") or {}).get("src", "")
    alt = (b.get("imagen") or {}).get("alt", titulo or "Figura")
    es_url = src.startswith("http://") or src.startswith("https://")

    src_final = None

    # Caso 1: src ya es URL absoluta
    if es_url:
        src_final = src

    # Caso 2: src es ruta local con nombre conocido
    elif src and isinstance(imagenes, dict):
        nombre = os.path.basename(src)
        if nombre in imagenes:
            src_final = imagenes[nombre].get("preview_url") or imagenes[nombre].get("download_url")

    # Caso 3: src vacío pero hay número; buscar candidatos comunes en el mapa
    if not src_final and num and isinstance(imagenes, dict):
        candidatos = [
            "Figura_%s.png" % num,
            "Figura_%s.jpeg" % num,
            "Figura_%s.jpg" % num,
            "Figura_%s_a.png" % num,
        ]
        for c in candidatos:
            if c in imagenes:
                src_final = imagenes[c].get("preview_url") or imagenes[c].get("download_url")
                if not alt or alt == "Figura":
                    alt = titulo or ("Figura %s" % num)
                break

    cap = ""
    if num or titulo:
        cap = '<figcaption class="cc-figure__caption"><strong>Figura %s.</strong> %s%s</figcaption>' % (
            esc(str(num) if num else ""), esc(titulo),
            ("<br>%s" % esc(nota)) if nota else "")

    if src_final:
        return ('<figure class="cc-figure" '
                'style="max-width:720px;margin:16px auto;text-align:center;">'
                '<img class="cc-figure__img" src="%s" alt="%s" '
                'width="720" '
                'style="max-width:100%%;width:100%%;height:auto;display:block;">'
                '%s</figure>'
                % (esc(src_final), esc(alt), cap))

    # Placeholder visible para figuras pendientes (compacto, sin img vacío)
    descr = ", ".join(b.get("elementos") or [])[:200]
    return (
        '<div style="background:#fee2e2;border:2px dashed #b91c1c;color:#7f1d1d;'
        'padding:10px 14px;margin:10px 0;border-radius:4px">'
        '<p style="margin:0;font-weight:bold">📷 Figura %s pendiente — %s</p>'
        '%s</div>'
        % (esc(str(num) if num else "?"),
           esc(titulo),
           ('<p style="margin:4px 0 0 0;font-size:13px">%s</p>' % esc(descr)) if descr else ""))


def render_tabla(b):
    num = b.get("numero")
    titulo = b.get("titulo") or ""
    encab = b.get("encabezados") or []
    filas = b.get("filas") or []
    nota = b.get("nota") or ""
    caption = ""
    if num or titulo:
        caption = "<caption>Tabla %s. %s</caption>" % (esc(str(num) if num else ""), esc(titulo))
    thead = ""
    if encab:
        thead = "<thead><tr>%s</tr></thead>" % "".join(
            '<th scope="col">%s</th>' % md_inline(c) for c in encab)
    tbody = "<tbody>%s</tbody>" % "".join(
        "<tr>%s</tr>" % "".join("<td>%s</td>" % md_inline(c) for c in fila)
        for fila in filas)
    nota_h = ('<p style="font-size:13px;color:#595959"><em>Nota.</em> %s</p>'
              % md_inline(nota)) if nota else ""
    return ('<div class="cc-table-wrap"><table class="cc-table">%s%s%s</table>%s</div>'
            % (caption, thead, tbody, nota_h))


# ============================================================
# Agrupador: separa los bloques de la semana en jerarquía
# ============================================================

def es_unidad(t):
    return bool(re.match(r"^\s*unidad\s+\d", (t or "").lower()))


def es_tema(t):
    return bool(re.match(r"^\s*tema\s*[:.\-]", (t or "").lower()))


def limpiar_tema(t):
    return re.sub(r"^\s*tema\s*[:.\-]\s*", "", t or "", flags=re.I).strip()


def estructurar_semana(bloques):
    """Devuelve: {titulo_unidad, tema_principal, intro, subtemas[],
    actividades_recomendadas[]}.

    Jerarquía:
      Heading 2 ("EdiLoja Subtítulo 1") -> subtema (1.x)
      Heading 3 ("EdiLoja Subtítulo 2") -> sub-subtema (1.x.y)
      Heading 4+ ("EdiLoja Subtítulo 3") -> sub-sub-subtema (renderizado como H5)
    """
    titulo_unidad = ""
    tema_principal = None
    intro = []
    subtemas = []
    actividades = []
    estado = "intro"
    sub_actual = None
    ss_actual = None

    def nuevo_sub(t):
        nonlocal sub_actual, ss_actual
        sub_actual = {"titulo": t, "bloques_propios": [], "sub_subtemas": []}
        ss_actual = None
        subtemas.append(sub_actual)

    def nuevo_ss(t):
        nonlocal ss_actual
        ss_actual = {"titulo": t, "bloques": []}
        if sub_actual:
            sub_actual["sub_subtemas"].append(ss_actual)

    for b in bloques:
        tipo = b.get("tipo")

        if tipo == "actividad_recomendada":
            actividades.append(b)
            continue

        if tipo in ("resultado_aprendizaje", "contextualizacion",
                    "encuentros_linea", "tema_principal"):
            continue

        if tipo == "subtitulo":
            txt = (b.get("texto") or "").strip()
            nivel = b.get("nivel", 2)
            if es_unidad(txt):
                titulo_unidad = txt
                continue
            if es_tema(txt):
                # El primer "Tema:" es el tema principal de la semana.
                # Los "Tema:" siguientes son etiquetas extras que el docente
                # repitió; las ignoramos para no romper la jerarquía.
                if tema_principal is None:
                    tema_principal = limpiar_tema(txt)
                continue
            if nivel <= 2:
                # Heading 2 sin "Tema:" = subtema (1.x)
                nuevo_sub(txt)
                estado = "subtema"
                continue
            if nivel == 3:
                # Heading 3 = sub-subtema (1.x.y)
                if sub_actual is None:
                    nuevo_sub(tema_principal or "Contenido")
                    estado = "subtema"
                nuevo_ss(txt)
                continue
            # nivel 4+: sub-sub-subtema. Lo metemos como bloque heading dentro del
            # contexto actual (sub-subtema si hay, o subtema propio si no).
            destino = (ss_actual["bloques"] if ss_actual
                       else (sub_actual["bloques_propios"] if sub_actual else intro))
            destino.append(b)
            continue

        if estado == "intro":
            intro.append(b)
        elif ss_actual is not None:
            ss_actual["bloques"].append(b)
        elif sub_actual is not None:
            sub_actual["bloques_propios"].append(b)
        else:
            intro.append(b)

    return {"titulo_unidad": titulo_unidad,
            "tema_principal": tema_principal,
            "intro_bloques": intro,
            "subtemas": subtemas,
            "actividades_recomendadas": actividades}


# ============================================================
# Render: Outcome (Resultado + Contextualización) — solo Semana 1
# ============================================================

def render_outcome(ra, ctx, mostrar_ctx=True):
    """Render del bloque cc-outcome con Resultados + Contextualización.

    ra:          str (un RA) o list[str] (varios RAs).
    ctx:         list[str] de párrafos de la contextualización.
    mostrar_ctx: si False, se renderiza SOLO el RA (sin botón ni panel).
                 Se usa para mostrar el RA en todas las semanas pero la
                 contextualización solo donde el RA inicia.
    """
    if not ra and not ctx:
        return ""

    # Lista de resultados: si el JSON trae uno solo en párrafo, lo convertimos
    # a UN <li>; si más adelante el etiquetador detecta varios, ya queda listo.
    items_html = ""
    if isinstance(ra, list):
        items_html = "".join("<li>%s</li>" % md_inline(t) for t in ra)
    elif ra:
        items_html = "<li>%s</li>" % md_inline(ra)

    ctx_html = ""
    if mostrar_ctx and ctx:
        ctx_html = "".join("<p>%s</p>" % md_inline(p) for p in ctx)

    btn_ctx = ""
    panel_ctx = ""
    if ctx_html:
        btn_ctx = (
            '<div class="cc-outcome__actions">'
            '<a id="cc-ctx-toggle" class="cc-btn cc-btn--primary" '
            'title="Mostrar la contextualización de la semana" role="button" '
            'href="#cc-ctx-panel" aria-expanded="false" '
            'aria-controls="cc-ctx-panel" data-cc-toggle-target="cc-ctx-panel">'
            ' Contextualización </a></div>')
        panel_ctx = (
            '<div id="cc-ctx-panel" class="cc-context" role="region" '
            'aria-labelledby="cc-ctx-toggle">'
            '<div class="cc-context__inner cc-prose">%s</div></div>') % ctx_html

    return (
        '<section class="cc-section">'
        '<div class="cc-outcome">'
        '<div class="cc-outcome__aside">'
        '<h2 class="cc-outcome__title">Resultados de Aprendizaje</h2>'
        '</div>'
        '<div class="cc-outcome__body">'
        '<ul class="cc-outcome__list">%s</ul>'
        '%s'
        '</div>'
        '</div>'
        '%s'
        '</section>') % (items_html or "<li>(pendiente)</li>", btn_ctx, panel_ctx)


# ============================================================
# Render: Tabs verticales con los subtemas
# ============================================================

def render_intro_y_tabs(estructura, imagenes, unidad_acad, offset_subtema):
    """offset_subtema: cuántos subtemas hubo antes en semanas previas de la misma
    unidad. El primer subtema de esta semana se numera unidad.(offset+1)."""
    intro = estructura["intro_bloques"]
    subtemas = estructura["subtemas"]

    out = ['<section class="cc-section">']

    # Intro prose (sin título)
    if intro:
        out.append('<div class="cc-prose">')
        for i, b in enumerate(intro):
            if b.get("tipo") == "parrafo":
                cls = ' class="cc-intro"' if i == 0 else ""
                out.append("<p%s>%s</p>" % (cls, md_inline(b.get("texto", ""))))
            else:
                out.append(render_bloque(b, imagenes))
        out.append("</div>")

    # Tabs verticales con numeración continua
    if subtemas:
        ids = []
        numeros = []
        for i, sub in enumerate(subtemas):
            num = "%s.%d" % (unidad_acad or 1, offset_subtema + i + 1)
            numeros.append(num)
            sid = "%s-%s" % (num.replace(".", "-"), slug(sub["titulo"]))
            ids.append(sid)

        out.append('<div class="cc-tabs cc-tabs--vertical" data-cc-tabs="" data-cc-default="0">')
        out.append('<div class="cc-tabs__nav" role="tablist" aria-orientation="vertical" '
                   'aria-label="Temas de la semana">')
        for i, (sub, sid, num) in enumerate(zip(subtemas, ids, numeros), 1):
            sel = "true" if i == 1 else "false"
            etiqueta = "%s. %s" % (num, sub["titulo"])
            out.append(
                '<a id="cc-t-%s" class="cc-tabs__tab" title="%s" role="tab" '
                'href="#cc-p-%s" aria-controls="cc-p-%s" aria-selected="%s">'
                '<span class="cc-tabs__label">%s</span></a>'
                % (sid, esc(etiqueta), sid, sid, sel, esc(etiqueta)))
        out.append('</div>')

        out.append('<div class="cc-tabs__panels">')
        for i, (sub, sid, num) in enumerate(zip(subtemas, ids, numeros), 1):
            out.append('<div id="cc-p-%s" class="cc-tabs__panel cc-prose" role="tabpanel" '
                       'aria-labelledby="cc-t-%s">' % (sid, sid))
            out.append("<h3>%s. %s</h3>" % (esc(num), md_inline(sub["titulo"])))
            for b in sub["bloques_propios"]:
                out.append(render_bloque(b, imagenes))
            for j, ss in enumerate(sub["sub_subtemas"], 1):
                out.append("<h4>%s.%d %s</h4>" % (esc(num), j, md_inline(ss["titulo"])))
                for b in ss["bloques"]:
                    out.append(render_bloque(b, imagenes))
            out.append('</div>')
        out.append('</div></div>')

    out.append('</section>')
    return "\n".join(out)


# ============================================================
# Render: Zona de Práctica (Actividades / Autoevaluación / Actividad Evaluada)
# ============================================================

def render_zona_practica(actividades, imagenes, mostrar_autoeval, unidad_num, base_recursos):
    """Tres tabs horizontales, pero la pestaña 'Autoevaluación' SOLO se incluye
    cuando mostrar_autoeval es True (última semana de la unidad y existe el
    recurso). En las demás semanas esa pestaña no se renderiza en absoluto.

    Cuando se incluye, el panel embebe el recurso interactivo vía <iframe>
    (link fijo del servidor de recursos), en lugar de listar las preguntas."""
    # --- Construcción de la barra de tabs (Autoevaluación es opcional) ---
    tabs_nav = [
        '<a id="cc-zp-rec" class="cc-tabs__tab" title="Actividades Recomendadas" '
        'role="tab" href="#cc-zp-panel-rec" aria-controls="cc-zp-panel-rec" '
        'aria-selected="true"><span class="cc-tabs__label">Actividades Recomendadas</span></a>'
    ]
    if mostrar_autoeval:
        tabs_nav.append(
            '<a id="cc-zp-auto" class="cc-tabs__tab" title="Autoevaluación" '
            'role="tab" href="#cc-zp-panel-auto" aria-controls="cc-zp-panel-auto" '
            'aria-selected="false"><span class="cc-tabs__label">Autoevaluación</span></a>'
        )
    tabs_nav.append(
        '<a id="cc-zp-eval" class="cc-tabs__tab" title="Actividad Evaluada" '
        'role="tab" href="#cc-zp-panel-eval" aria-controls="cc-zp-panel-eval" '
        'aria-selected="false"><span class="cc-tabs__label">Actividad Evaluada</span></a>'
    )

    out = ['<section class="cc-section">',
           '<div class="cc-bar cc-bar--solid">',
           '<h2 class="cc-bar__title">Zona de Práctica</h2>',
           '</div>',
           '<div class="cc-tabs" data-cc-tabs="" data-cc-default="0">',
           '<div class="cc-tabs__nav" role="tablist" '
           'aria-label="Zona de práctica de la semana">',
           "".join(tabs_nav),
           '</div>',
           '<div class="cc-tabs__panels">']

    # Tab 1: Actividades Recomendadas
    out.append('<div id="cc-zp-panel-rec" class="cc-tabs__panel" role="tabpanel" '
               'aria-labelledby="cc-zp-rec">')
    out.append('<p class="cc-activities__intro">Las siguientes actividades son de '
               'carácter formativo y no tienen calificación. Te recomendamos realizarlas '
               'para reforzar los conceptos revisados en esta semana.</p>')
    if actividades:
        for i, act in enumerate(actividades, 1):
            out.append('<div class="cc-activity">'
                       '<span class="cc-activity__num" aria-hidden="true">%d</span>'
                       '<div>' % i)
            contenido = act.get("contenido", [])
            if contenido:
                for b in contenido:
                    out.append(render_bloque(b, imagenes))
            else:
                out.append('<p class="cc-activity__text"><em>Actividad pendiente '
                           'de definir por el equipo docente.</em></p>')
            out.append('</div></div>')
    else:
        out.append('<p><em>Aún no se han definido actividades recomendadas '
                   'para esta semana.</em></p>')
    out.append('</div>')

    # Tab 2: Autoevaluación — SOLO en la última semana de la unidad.
    # El contenido es el recurso interactivo embebido (iframe), no las preguntas.
    if mostrar_autoeval:
        url_recurso = "%s/autoevaluacion_%s.html" % (base_recursos.rstrip("/"), unidad_num)
        out.append('<div id="cc-zp-panel-auto" class="cc-tabs__panel" '
                   'role="tabpanel" aria-labelledby="cc-zp-auto">')
        out.append('<p class="cc-activities__intro">Resuelve la autoevaluación de la '
                   'unidad. Es de carácter formativo y te permite verificar tu avance '
                   'antes de la evaluación calificada.</p>')
        out.append(
            '<div class="cc-resource-embed" '
            'style="width:100%%;margin:8px 0;border:1px solid #e5e9f2;'
            'border-radius:8px;overflow:hidden;">'
            '<iframe src="%s" title="Autoevaluación de la Unidad %s" '
            'width="100%%" height="800" loading="lazy" '
            'style="border:0;width:100%%;min-height:800px;display:block;background:#fff;">'
            '</iframe></div>'
            % (esc(url_recurso), esc(str(unidad_num)))
        )
        out.append('<p style="font-size:13px;color:#595959;margin-top:8px;">'
                   'Si la autoevaluación no carga, ábrela directamente en '
                   '<a class="cc-link" href="%s" target="_blank" rel="noopener">'
                   'esta página</a>.</p>' % esc(url_recurso))
        out.append('</div>')

    # Tab 3: Actividad Evaluada (espacio neutro)
    out.append('<div id="cc-zp-panel-eval" class="cc-tabs__panel" role="tabpanel" '
               'aria-labelledby="cc-zp-eval">')
    out.append('<p class="cc-activities__intro">Las actividades evaluadas y su '
               'detalle se gestionan desde el libro de calificaciones de Canvas.</p>')
    out.append('</div>')

    out.append('</div></div></section>')
    return "\n".join(out)


# ============================================================
# Helpers de extracción del JSON
# ============================================================

def buscar_pagina(data, *titulos):
    aceptables = {t.lower().strip() for t in titulos}
    for s in data.get("secciones", []):
        if s.get("tipo") == "pagina" and (s.get("titulo") or "").lower().strip() in aceptables:
            return s
    return None


def obtener_semanas(data):
    for s in data.get("secciones", []):
        if s.get("tipo") == "contenido":
            return s.get("unidades", [])
    return []


def autoeval_por_unidad(data, num):
    for s in data.get("secciones", []):
        if s.get("tipo") == "autoevaluacion" and s.get("unidad") == num:
            return s
    return None


def obtener_resultado_aprendizaje(data):
    """Devuelve el resultado de aprendizaje. Puede ser str (uno solo) o lista (varios)."""
    pg = buscar_pagina(data, "Orientaciones didácticas por resultados de aprendizaje",
                       "Orientaciones didácticas")
    if not pg:
        return None
    bs = pg.get("bloques", [])
    # Nuevo: bloque semántico v2
    for b in bs:
        if b.get("tipo") == "resultado_aprendizaje":
            textos = []
            for ib in b.get("contenido", []):
                if ib.get("tipo") == "parrafo" and ib.get("texto", "").strip():
                    textos.append(ib["texto"])
                elif ib.get("tipo") == "lista":
                    textos.extend(ib.get("items", []))
            if len(textos) == 1:
                return textos[0]
            if textos:
                return textos
            return None
    # Fallback
    for i, b in enumerate(bs):
        if b.get("tipo") == "subtitulo" and "resultado" in (b.get("texto") or "").lower():
            for j in range(i + 1, min(i + 5, len(bs))):
                if bs[j].get("tipo") == "parrafo" and bs[j].get("texto", "").strip():
                    return bs[j]["texto"]
    return None


def obtener_contextualizacion(data):
    """Devuelve los párrafos de la contextualización."""
    pg = buscar_pagina(data, "Orientaciones didácticas por resultados de aprendizaje",
                       "Orientaciones didácticas")
    if not pg:
        return []
    for b in pg.get("bloques", []):
        if b.get("tipo") == "contextualizacion":
            return [ib.get("texto", "") for ib in b.get("contenido", [])
                    if ib.get("tipo") == "parrafo" and ib.get("texto", "").strip()]
    return []


def _ctx_a_parrafos(texto):
    """Parte la contextualización (string que devuelve el agente) en párrafos."""
    if not texto:
        return []
    return [p.strip() for p in re.split(r"\n+", texto) if p.strip()]


def plan_outcomes_por_semana(data):
    """Calcula, por cada semana (idx 1-based), qué Resultado de Aprendizaje
    mostrar y si toca mostrar su Contextualización.

    REGLAS (acordadas):
      - El RA se muestra en TODAS las semanas a las que aplica.
      - La Contextualización se muestra SOLO en la semana donde ese RA INICIA
        (la primera vez que aparece). En las semanas siguientes va solo el RA.
      - En la página "Orientaciones didácticas" puede haber MÁS DE UN RA (uno
        por Unidad académica): el RA #1 aplica desde la Unidad 1, el RA #2
        desde la Unidad 2, etc. (ej. Semanas 1-2 = Unidad 1 → RA #1; Semana 3
        = Unidad 2 → RA #2).

    Fuente de datos (en orden de preferencia):
      1. Output del agente curar_contextualizaciones.py:
           data['ras_globales_curados']           -> lista de RAs, uno por
                                                      Unidad (unidad_aplica)
           data['ra_global_curado']               -> (compat) un solo RA
                                                      global para todo el curso
           semana['contextualizaciones_finales']  -> RAs específicos de la semana
      2. Fallback (JSON sin pasar por el agente): bloques crudos de la página
         'Orientaciones didácticas'.

    Devuelve: {idx: {"ra": str|list, "ctx": list[str], "mostrar_ctx": bool}}
    """
    semanas = obtener_semanas(data)
    plan = {}

    ras_globales = data.get("ras_globales_curados")
    ra_por_unidad = {}
    if ras_globales:
        for r in ras_globales:
            ra_por_unidad[r.get("unidad_aplica")] = r

    ra_global = data.get("ra_global_curado")  # compat: un solo RA para todo

    # Fallback solo si el JSON no trae ningún output del agente.
    ra_fallback, ctx_fallback = None, []
    if not ras_globales and not ra_global:
        ra_fallback = obtener_resultado_aprendizaje(data)
        ctx_fallback = obtener_contextualizacion(data)

    ctx_mostradas = set()  # claves de RA cuya contextualización ya se mostró

    for i, sem in enumerate(semanas, 1):
        especificos = sem.get("contextualizaciones_finales") or []
        numero_unidad = sem.get("numero")

        # Caso A: la semana declara su(s) propio(s) RA específico(s).
        # Un RA específico siempre INICIA en su propia semana.
        if especificos:
            ras = [e.get("ra", "") for e in especificos if e.get("ra")]
            ctx = []
            for e in especificos:
                ctx.extend(_ctx_a_parrafos(e.get("contextualizacion_final", "")))
            ra = ras[0] if len(ras) == 1 else ras
            plan[i] = {"ra": ra, "ctx": ctx, "mostrar_ctx": bool(ctx)}
            continue

        # Caso B: la semana hereda el RA de su Unidad académica (puede haber
        # un RA distinto por Unidad).
        if ras_globales:
            ra_de_la_unidad = ra_por_unidad.get(numero_unidad)
            if ra_de_la_unidad is None:
                # No hay un RA exacto para esta unidad: usar el último RA
                # conocido con unidad_aplica <= numero_unidad (por si hay
                # huecos), o si no hay ninguno anterior, el primero.
                candidatos = [r for r in ras_globales
                             if (r.get("unidad_aplica") or 0) <= (numero_unidad or 0)]
                ra_de_la_unidad = candidatos[-1] if candidatos else ras_globales[0]
            clave = "unidad-%s" % ra_de_la_unidad.get("unidad_aplica")
            es_inicio = clave not in ctx_mostradas
            ctx = _ctx_a_parrafos(ra_de_la_unidad.get("contextualizacion_final", "")) if es_inicio else []
            if es_inicio:
                ctx_mostradas.add(clave)
            plan[i] = {"ra": ra_de_la_unidad.get("ra"), "ctx": ctx, "mostrar_ctx": es_inicio}
            continue

        # Caso B' (compat): un solo RA global para todo el curso (JSON
        # generado antes de que existiera 'ras_globales_curados').
        if ra_global:
            es_inicio = "global" not in ctx_mostradas
            ctx = _ctx_a_parrafos(ra_global.get("contextualizacion_final", "")) if es_inicio else []
            if es_inicio:
                ctx_mostradas.add("global")
            plan[i] = {"ra": ra_global.get("ra"), "ctx": ctx, "mostrar_ctx": es_inicio}
            continue

        # Caso C: fallback (sin agente) — RA crudo de Orientaciones didácticas.
        es_inicio = "fallback" not in ctx_mostradas
        ctx = ctx_fallback if es_inicio else []
        if es_inicio:
            ctx_mostradas.add("fallback")
        plan[i] = {"ra": ra_fallback, "ctx": ctx, "mostrar_ctx": es_inicio}

    return plan


def es_primera_semana_de_unidad(semanas, idx):
    """idx es 1-based. True si la semana N es la primera de su unidad académica."""
    if idx == 1:
        return True
    actual = semanas[idx - 1].get("numero")
    anterior = semanas[idx - 2].get("numero")
    return actual != anterior


def es_ultima_semana_de_unidad(semanas, idx):
    """True si la semana N es la última de su unidad académica."""
    if idx >= len(semanas):
        return True
    actual = semanas[idx - 1].get("numero")
    siguiente = semanas[idx].get("numero")
    return actual != siguiente


def contar_subtemas_previos_en_unidad(semanas, idx):
    """Cuenta cuántos subtemas hay ANTES de la semana idx, pero dentro de la
    misma unidad académica. Sirve para que la numeración sea continua entre
    semanas: si Semana 1 tuvo 4 subtemas, Semana 2 (misma unidad) arranca en
    1.5, no en 1.1."""
    if idx <= 1:
        return 0
    unidad_actual = semanas[idx - 1].get("numero")
    total = 0
    for k in range(idx - 1):
        s = semanas[k]
        if s.get("numero") != unidad_actual:
            continue
        est = estructurar_semana(s.get("bloques", []))
        total += len(est["subtemas"])
    return total


# ============================================================
# HTML de una semana completa
# ============================================================

def render_weeknav(semanas, semana_actual):
    """Navegación entre semanas (cc-weeknav). Marca la semana activa."""
    total = len(semanas)
    weeks = []
    for i in range(1, total + 1):
        cls = "cc-weeknav__week"
        if i == semana_actual:
            cls += " cc-weeknav__week--active"
        weeks.append(
            '<a class="%s" title="Semana %d" href="#">%d</a>'
            % (cls, i, i))
    return (
        '<nav class="cc-weeknav" aria-label="Navegación del curso">'
        '<a class="cc-weeknav__home" title="Volver al inicio del curso" href="#">'
        '<span class="cc-visually-hidden">Inicio del curso</span></a> '
        '<span class="cc-weeknav__label">Semanas</span> '
        '<span class="cc-weeknav__weeks">%s</span>'
        '</nav>') % " ".join(weeks)


def titulo_unidad_global(semanas, unidad_num):
    """Busca el título de la unidad académica en cualquier semana de esa unidad.
    Útil porque en las semanas posteriores a la primera, el docente no repite
    'Unidad N: ...' y el banner queda sin texto."""
    for s in semanas:
        if s.get("numero") != unidad_num:
            continue
        for b in s.get("bloques", []):
            if b.get("tipo") == "subtitulo":
                txt = (b.get("texto") or "").strip()
                if es_unidad(txt):
                    return txt
                # solo miramos el primer subtítulo de cada semana
                break
    return None


def html_semana(data, semana_idx, imagenes, base_recursos=BASE_RECURSOS_DEFAULT):
    semanas = obtener_semanas(data)
    if semana_idx < 1 or semana_idx > len(semanas):
        return None, None
    u = semanas[semana_idx - 1]
    bloques = u.get("bloques", [])
    nombre_pagina = u.get("nombre_pagina", "Semana %d" % semana_idx)
    unidad_acad = u.get("numero")
    est = estructurar_semana(bloques)
    titulo_uni = est["titulo_unidad"]
    ultima_de_unidad = es_ultima_semana_de_unidad(semanas, semana_idx)

    out = []
    # Wrapper completo del theme global (toolbar + banner + weeknav + secciones +
    # pager + footer). El theme NO funciona si falta el wrapper cc-curso.
    out.append('<div id="cc-curso" class="cc-curso">')

    # Toolbar con toggle de modo oscuro (todas las páginas del theme lo tienen)
    out.append('<div class="cc-toolbar">'
               '<a id="cc-theme-toggle" class="cc-theme-toggle" '
               'title="Activar modo oscuro" role="button" href="#" '
               'aria-pressed="false" aria-label="Activar modo oscuro">'
               '<span class="cc-theme-icon" aria-hidden="true">☽</span></a></div>')

    # 1) Banner — el theme lo estiliza con cc-banner--semana
    # El título del banner debe ser el título de la unidad académica.
    # Si esta semana no lo trae explícito, lo buscamos en otras semanas de la
    # misma unidad (típicamente la primera semana de la unidad lo tiene).
    titulo_banner = titulo_uni or titulo_unidad_global(semanas, unidad_acad) or "Unidad %s" % (unidad_acad or "?")
    out.append('<header class="cc-banner cc-banner--semana">')
    out.append('<p class="cc-banner__eyebrow">%s</p>' % esc(nombre_pagina))
    out.append('<h1 class="cc-banner__title">%s</h1>' % esc(titulo_banner))
    out.append('<span class="cc-banner__brand">UTPL</span>')
    out.append('</header>')

    # 2) Navegación entre semanas (cc-weeknav)
    out.append(render_weeknav(semanas, semana_idx))

    # 3) Outcome (Resultados + Contextualización)
    #    El RA va en TODAS las semanas a las que aplica; la contextualización
    #    solo en la semana donde ese RA inicia.
    plan = plan_outcomes_por_semana(data)
    info = plan.get(semana_idx)
    if info and (info["ra"] or info["ctx"]):
        out.append(render_outcome(info["ra"], info["ctx"], info["mostrar_ctx"]))

    # 4) Intro prose + Tabs verticales con subtemas (numeración continua)
    offset = contar_subtemas_previos_en_unidad(semanas, semana_idx)
    out.append(render_intro_y_tabs(est, imagenes, unidad_acad, offset))

    # 5) Zona de Práctica
    #    La pestaña Autoevaluación va SOLO en la última semana de la unidad y
    #    solo si existe el recurso de esa unidad; se embebe vía iframe.
    autoeval = autoeval_por_unidad(data, unidad_acad)
    mostrar_autoeval = ultima_de_unidad and (autoeval is not None)
    out.append(render_zona_practica(est["actividades_recomendadas"], imagenes,
                                     mostrar_autoeval, unidad_acad, base_recursos))

    # 6) Pager (Anterior/Siguiente) — el theme lo estiliza
    out.append('<nav class="cc-pager" aria-label="Navegación entre páginas">'
               '<a title="Ir a la página anterior" href="#">◀ Anterior</a> '
               '<a title="Ir a la página siguiente" href="#">Siguiente ▶</a></nav>')

    # 7) Footer con marca UTPL
    out.append('<footer class="cc-footer">'
               '<span class="cc-footer__brand">UTPL</span></footer>')

    out.append('</div>')  # cierre cc-curso
    return nombre_pagina, "\n".join(out)


# ============================================================
# main()
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="Llena páginas de semana en Canvas (theme cc-*).")
    ap.add_argument("entrada", help="JSON canónico (salida.json)")
    ap.add_argument("--curso", type=int, required=True)
    ap.add_argument("--semana", type=int, default=None,
                    help="semana a llenar (def: todas)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--mapa-imagenes", default="mapa_imagenes.json")
    ap.add_argument("--base-recursos", default=BASE_RECURSOS_DEFAULT,
                    help="URL base del servidor de recursos para los iframes de "
                         "autoevaluación (def: %s)" % BASE_RECURSOS_DEFAULT)
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)

    imagenes_disp = {}  # nombre -> {file_id, preview_url, download_url}
    if os.path.exists(args.mapa_imagenes):
        with open(args.mapa_imagenes, encoding="utf-8") as f:
            imagenes_disp = json.load(f)
        print("Imágenes disponibles en Canvas: %d (cargadas desde %s)"
              % (len(imagenes_disp), args.mapa_imagenes))
    else:
        print("⚠ NO se encontró el mapa de imágenes en: %s" % args.mapa_imagenes)
        print("  Las figuras se renderizarán como placeholder rojo.")
        print("  Sube las imágenes primero con: python canvas_subir_imagenes.py")

    total = len(obtener_semanas(data))
    rango = [args.semana] if args.semana else list(range(1, total + 1))
    print("Semanas a procesar: %s\n" % rango)

    pendientes = {}
    for n in rango:
        nombre, body = html_semana(data, n, imagenes_disp, args.base_recursos)
        if not body:
            print("  ⚠ Semana %d no existe" % n)
            continue
        pendientes[nombre] = body

    if args.dry_run:
        for nombre, body in pendientes.items():
            print("\n" + "=" * 70)
            print("PÁGINA: %s  (%d caracteres)" % (nombre, len(body)))
            print("=" * 70)
            print(body[:2500] + ("\n... [truncado]" if len(body) > 2500 else ""))
        print("\nDRY-RUN: no se tocó Canvas.")
        return

    try:
        from canvasapi import Canvas
    except ImportError:
        sys.exit("Falta canvasapi:  pip install canvasapi")
    url = os.environ.get("CANVAS_URL")
    token = os.environ.get("CANVAS_TOKEN")
    if not url or not token:
        sys.exit("Define CANVAS_URL y CANVAS_TOKEN.")
    canvas = Canvas(url, token)
    try:
        curso = canvas.get_course(args.curso)
        print("Conectado al curso: %s\n" % curso.name)
    except Exception as e:
        sys.exit("Error: %s" % e)

    existentes = {pg.title: pg for pg in curso.get_pages()}
    act, falt = 0, []
    for nombre, body in pendientes.items():
        pg = existentes.get(nombre)
        if not pg:
            falt.append(nombre)
            print("  ⚠ No existe '%s'" % nombre)
            continue
        cambios = {"body": body}
        if args.publicar:
            cambios["published"] = True
        pg.edit(wiki_page=cambios)
        print("  ✓ '%s' actualizada (%d caracteres)" % (nombre, len(body)))
        act += 1

    print("\n=========== RESUMEN ===========")
    print("  Actualizadas:   %d" % act)
    print("  No encontradas: %d %s" % (len(falt), ("(%s)" % ", ".join(falt)) if falt else ""))
    print("================================")


if __name__ == "__main__":
    main()