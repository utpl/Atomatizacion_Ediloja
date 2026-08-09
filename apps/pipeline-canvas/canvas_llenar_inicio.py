#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_llenar_inicio.py — Llena la página "Inicio" del curso en Canvas con el
HTML del theme institucional (clases cc-*), igual al modelo del equipo de diseño.

Estructura de la página de Inicio:
  - Toolbar con toggle de modo oscuro.
  - Banner con TÍTULO DEL CURSO (no de semana).
  - Botones de descarga: Plan Docente / Guía Didáctica (placeholders href="#").
  - 3 tabs colapsables:
      · Visión General  → video de la página "Presentación" del JSON.
      · Planificación   → Competencias + Metodología + Carga horaria (donut).
      · Tu Mentor       → comentario HTML "pendiente" (no está en el JSON).
  - Ruta de Aprendizaje → cuadritos por semana detectados del JSON.
  - Quicknav inferior (Foro, Encuentros, Calendario, Recursos).
  - Pager + Footer (los estiliza el theme).

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="..."
    python canvas_llenar_inicio.py salida.json --curso 89932

Flags:
    --dry-run    muestra el HTML, sin tocar Canvas
    --publicar   publica la página tras actualizar
    --titulo X   sobreescribe el título del curso (def: metadata.titulo del JSON)
"""

import argparse
import html
import json
import os
import re
import sys


# ----------------- Utilidades -----------------

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


def buscar_pagina(data, *titulos):
    aceptables = {t.lower().strip() for t in titulos}
    for s in data.get("secciones", []):
        if s.get("tipo") == "pagina" and (s.get("titulo") or "").lower().strip() in aceptables:
            return s.get("bloques", [])
    return []


def obtener_semanas(data):
    for s in data.get("secciones", []):
        if s.get("tipo") == "contenido":
            return s.get("unidades", [])
    return []


# ----------------- Render de bloques internos -----------------

def render_video_iframe(b):
    url = b.get("url") or ""
    titulo = b.get("titulo") or "Video"
    vid = youtube_id(url)
    if vid:
        return ('<figure class="cc-figure">'
                '<iframe src="https://www.youtube.com/embed/%s" width="640" height="360" '
                'allowfullscreen allow="accelerometer; autoplay; encrypted-media; '
                'gyroscope; picture-in-picture" title="%s" style="max-width:100%%;"></iframe>'
                '<figcaption class="cc-figure__caption">%s</figcaption></figure>'
                ) % (esc(vid), esc(titulo), esc(titulo))
    return ('<p>🎬 <a class="cc-link" href="%s" target="_blank" rel="noopener">%s</a></p>'
            % (esc(url), esc(titulo)))


def render_bloque_prose(b):
    """Render simple para los paneles 'cc-prose' (sin clases especiales)."""
    t = b.get("tipo")
    if t == "parrafo":
        return "<p>%s</p>" % md_inline(b.get("texto", ""))
    if t == "lista":
        tag = "ol" if b.get("estilo") == "numerada" else "ul"
        items = "".join("<li>%s</li>" % md_inline(i) for i in b.get("items", []))
        return "<%s>%s</%s>" % (tag, items, tag)
    if t == "video":
        return render_video_iframe(b)
    if t == "enlace":
        return ('<p>🔗 <a class="cc-link" href="%s" target="_blank" rel="noopener">%s</a></p>'
                % (esc(b.get("url", "")), esc(b.get("texto") or b.get("url") or "")))
    if t == "idea_clave":
        return '<blockquote><strong>Idea clave:</strong> %s</blockquote>' % md_inline(b.get("texto", ""))
    if t == "subtitulo":
        # Subtítulos internos: H3
        return "<h3 class=\"cc-subhead\">%s</h3>" % md_inline(b.get("texto", ""))
    return ""


# ----------------- Construcción del HTML por tab -----------------

def html_vision_general(data):
    """Visión General: video de la página 'Presentación' del JSON."""
    bloques = buscar_pagina(data, "Presentación", "Presentacion")
    if not bloques:
        return ('<p>Te damos la bienvenida a esta asignatura. A lo largo del curso '
                'analizaremos los temas centrales y la metodología de trabajo.</p>'
                '<!-- TODO: agregar video de presentación cuando esté disponible en el JSON -->'
                '<p><em>Video de presentación pendiente de incorporar.</em></p>')

    out = ['<p>Te damos la bienvenida a esta asignatura. En el siguiente video '
           'encontrarás una breve presentación de la asignatura, sus propósitos '
           'y su metodología de trabajo.</p>']
    for b in bloques:
        # Solo nos interesa el video y párrafos introductorios
        if b.get("tipo") in ("video", "parrafo", "enlace"):
            h = render_bloque_prose(b)
            if h:
                out.append(h)
    return "\n".join(out)


def html_planificacion(data):
    """Planificación: Competencias + Metodología + Carga horaria (donut)."""
    info = buscar_pagina(data, "Información general", "Informacion general")
    met = buscar_pagina(data, "Metodología de aprendizaje", "Metodologia de aprendizaje")

    out = []

    # ---- Propósitos de Aprendizaje ----
    out.append('<h3 class="cc-subhead">Propósitos de Aprendizaje</h3>')

    # Buscar competencias dentro de "Información general"
    if info:
        inicio = None
        for i, b in enumerate(info):
            if b.get("tipo") == "subtitulo" and "competencia" in (b.get("texto") or "").lower():
                inicio = i
                break
        if inicio is not None:
            for b in info[inicio + 1:]:
                if b.get("tipo") == "subtitulo":
                    # Solo seguir hasta el siguiente subtítulo de mismo nivel
                    nivel = b.get("nivel", 2)
                    if nivel <= 2 and "competencia" not in (b.get("texto") or "").lower():
                        break
                    out.append('<p><strong>%s</strong></p>' % md_inline(b.get("texto", "")))
                    continue
                h = render_bloque_prose(b)
                if h:
                    out.append(h)
        else:
            out.append('<p><em>Competencias pendientes de definir en la guía.</em></p>')
    else:
        out.append('<!-- TODO: no se encontró Información general en el JSON -->')
        out.append('<p><em>Competencias pendientes de definir.</em></p>')

    # ---- Metodología ----
    out.append('<h3 class="cc-subhead">Metodología</h3>')
    out.append('<div class="cc-scrollbox cc-scroll-y">')
    if met:
        for b in met:
            if b.get("tipo") == "subtitulo" and "metodolog" in (b.get("texto") or "").lower():
                continue
            h = render_bloque_prose(b)
            if h:
                out.append(h)
    else:
        out.append('<p><em>Metodología pendiente de definir.</em></p>')
    out.append('</div>')

    # ---- Carga horaria (donut) ----
    # Valores estándar para metacursos UTPL (igual que el ejemplo del equipo)
    out.append('<h3 class="cc-subhead">Carga horaria</h3>')
    out.append(
        '<div class="cc-donut" data-cc-donut="" '
        'data-cc-segments=\'[{"label":"Aprendizaje Autónomo (AA)","value":64,"color":"#54a0f1"},'
        '{"label":"Aprendizaje Práctico Experimental (APE)","value":32,"color":"#00b985"},'
        '{"label":"Aprendizaje en Contacto con el Docente (ACD)","value":48,"color":"#8b9cf7"}]\'>'
        '<div class="cc-donut__chart">'
        '<div class="cc-donut__center">'
        '<span class="cc-donut__center-value">144</span> '
        '<span class="cc-donut__center-label">horas</span></div></div>'
        '<ul class="cc-donut__legend">'
        '<li class="cc-donut__item">'
        '<span class="cc-donut__name">Aprendizaje Autónomo (AA)</span>'
        '<span class="cc-donut__value">64 h</span></li>'
        '<li class="cc-donut__item">'
        '<span class="cc-donut__name">Aprendizaje Práctico Experimental (APE)</span>'
        '<span class="cc-donut__value">32 h</span></li>'
        '<li class="cc-donut__item">'
        '<span class="cc-donut__name">Aprendizaje en Contacto con el Docente (ACD)</span>'
        '<span class="cc-donut__value">48 h</span></li>'
        '</ul></div>'
    )

    return "\n".join(out)


def html_tu_mentor():
    """Tu Mentor: datos ficticios "quemados" a pedido de DI, mientras se define
    la integración con el sistema académico de UTPL (no viene en el JSON)."""
    return (
        '<!-- TODO: datos ficticios de docente (DI pidió simulados por ahora). '
        'Reemplazar cuando exista integración con el sistema académico de UTPL. -->'
        '<div class="cc-mentor">'
        '<img class="cc-mentor__photo" '
        'src="https://ui-avatars.com/api/?name=Maria+Fernanda+Torres&background=54a0f1&color=fff&size=200" '
        'alt="Foto del docente" />'
        '<div>'
        '<p class="cc-mentor__name">Mg. María Fernanda Torres</p>'
        '<p class="cc-mentor__role">Docente titular</p>'
        '<p class="cc-mentor__org">Universidad Técnica Particular de Loja</p>'
        '<p class="cc-mentor__email">📧 <a class="cc-link" '
        'href="mailto:mftorres@utpl.edu.ec">mftorres@utpl.edu.ec</a></p>'
        '<p class="cc-mentor__bio">Docente e investigadora en el área de '
        'Gastronomía Sostenible, con experiencia en gestión de proyectos '
        'gastronómicos y desarrollo curricular. Le apasiona el acompañamiento '
        'cercano a los estudiantes durante todo el curso.</p>'
        '</div></div>'
    )


# ----------------- Ruta de Aprendizaje -----------------

def html_ruta_aprendizaje(data):
    """Cuadritos por semana + barra de progreso, como la plantilla de DI.

    El avance (% y semana actual) es un dato FICTICIO/QUEMADO por ahora, ya
    que no existe todavía una fuente real de progreso del estudiante.
    Estados: completado (verde), actual (azul), locked (gris/cerrado).
    """
    semanas = obtener_semanas(data)
    total = len(semanas) if semanas else 10

    # Identificar qué semanas tienen evaluación (última de cada unidad)
    semanas_con_eval = set()
    if semanas:
        for i in range(len(semanas)):
            unidad_actual = semanas[i].get("numero")
            siguiente = semanas[i + 1].get("numero") if i + 1 < len(semanas) else None
            if unidad_actual != siguiente:
                semanas_con_eval.add(i + 1)
    else:
        # Fallback: cada 3 semanas hay evaluación
        semanas_con_eval = {3, 6, 9, total}

    # ---- TODO: avance ficticio "quemado" (DI pidió simulado por ahora) ----
    # Reemplazar cuando exista una fuente real de progreso del estudiante.
    avance_pct = 50
    semana_actual = max(1, round(total * avance_pct / 100))

    out = ['<div class="cc-route">']

    # Barra de progreso con "caminante" y %
    out.append('<div class="cc-route__progress">')
    out.append('<div class="cc-route__track">')
    out.append('<div class="cc-route__fill" style="width:%d%%;"></div>' % avance_pct)
    out.append('<span class="cc-route__walker" style="left:%d%%;" '
               'aria-hidden="true">🚶</span>' % avance_pct)
    out.append('</div>')
    out.append('<span class="cc-route__pct">%d%%</span>' % avance_pct)
    out.append('</div>')

    # Cuadritos por semana
    out.append('<div class="cc-route__map"><div class="cc-route__grid">')
    for n in range(1, total + 1):
        if n < semana_actual:
            estado, status_txt = "completado", "Completado"
        elif n == semana_actual:
            estado, status_txt = "actual", "En curso"
        else:
            estado, status_txt = "locked", "Cerrado"

        # Color inline de respaldo, por si el theme cc-* todavía no trae las
        # clases cc-step--completado / cc-step--actual (solo tenía --locked).
        colores = {"completado": "#00b985", "actual": "#54a0f1", "locked": "#c9ced6"}
        eval_html = ('<span class="cc-step__eval">Zona de Evaluación</span>'
                     if n in semanas_con_eval else '')
        out.append(
            '<a class="cc-step cc-step--%s" style="background-color:%s;" '
            'title="Semana %d · %s" href="#">'
            '<span class="cc-step__num">%d</span>'
            '<span class="cc-step__status">%s</span>'
            '%s</a>' % (estado, colores[estado], n, status_txt, n, status_txt, eval_html))
    out.append('</div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------- Quicknav inferior (enlaces dinámicos) -----------------

def html_quicknav(foro_url="#", encuentros_url="#", calendario_url="#", recursos_url="#"):
    return (
        '<nav class="cc-quicknav" aria-label="Accesos del curso">'
        '<a class="cc-quicknav__item cc-quicknav__item--primary" '
        'title="Ir al foro de asesoría permanente" href="%s">'
        'Foro de Asesoría Permanente</a> '
        '<a class="cc-quicknav__item" '
        'title="Ir a Encuentros en Línea" href="%s">Encuentros en Línea</a> '
        '<a class="cc-quicknav__item" '
        'title="Ir al Calendario de Actividades" href="%s">'
        'Calendario de Actividades</a> '
        '<a class="cc-quicknav__item" '
        'title="Ir a Fuentes y Recursos" href="%s">Fuentes y Recursos</a>'
        '</nav>'
    ) % (esc(foro_url), esc(encuentros_url), esc(calendario_url), esc(recursos_url))


# ----------------- HTML completo de la página de Inicio -----------------

def html_inicio(data, titulo_curso, foro_url="#", encuentros_url="#",
                calendario_url="#", recursos_url="#"):
    out = []
    out.append('<div id="cc-curso" class="cc-curso">')

    # Toolbar
    out.append('<div class="cc-toolbar">'
               '<a id="cc-theme-toggle" class="cc-theme-toggle" '
               'title="Activar modo oscuro" role="button" href="#" '
               'aria-pressed="false" aria-label="Activar modo oscuro">'
               '<span class="cc-theme-icon" aria-hidden="true">☽</span></a></div>')

    # Banner con título del curso
    out.append('<header class="cc-banner cc-banner--inicio">')
    out.append('<h2 class="cc-banner__title">%s</h2>' % esc(titulo_curso))
    out.append('<span class="cc-banner__brand">UTPL</span>')
    out.append('</header>')

    # Botones de descarga (placeholders)
    out.append('<div class="cc-downloads">'
               '<a class="cc-btn cc-btn--primary" '
               'title="Descargar el Plan Docente en PDF" href="#">Plan Docente</a> '
               '<a class="cc-btn cc-btn--ghost" '
               'title="Descargar la Guía Didáctica en PDF" href="#">Guía Didáctica</a>'
               '</div>')

    # Tabs: Visión General / Planificación / Tu Mentor
    out.append('<section class="cc-tabs cc-section" data-cc-tabs="" '
               'data-cc-default="none" data-cc-collapsible="true">')
    out.append('<div class="cc-tabs__nav" role="tablist" '
               'aria-label="Información general del curso">')
    out.append('<a id="cc-tab-vision" class="cc-tabs__tab" title="Visión General" '
               'role="tab" href="#cc-panel-vision" aria-controls="cc-panel-vision" '
               'aria-selected="false">'
               '<span class="cc-tabs__label">Visión General</span></a>')
    out.append('<a id="cc-tab-plan" class="cc-tabs__tab" title="Planificación" '
               'role="tab" href="#cc-panel-plan" aria-controls="cc-panel-plan" '
               'aria-selected="false">'
               '<span class="cc-tabs__label">Planificación</span></a>')
    out.append('<a id="cc-tab-mentor" class="cc-tabs__tab" title="Tu Mentor" '
               'role="tab" href="#cc-panel-mentor" aria-controls="cc-panel-mentor" '
               'aria-selected="false">'
               '<span class="cc-tabs__label">Tu Mentor</span></a>')
    out.append('</div>')

    out.append('<div class="cc-tabs__panels">')

    # Panel: Visión General
    out.append('<div id="cc-panel-vision" class="cc-tabs__panel cc-prose" '
               'role="tabpanel" aria-labelledby="cc-tab-vision">')
    out.append(html_vision_general(data))
    out.append('</div>')

    # Panel: Planificación
    out.append('<div id="cc-panel-plan" class="cc-tabs__panel cc-prose" '
               'role="tabpanel" aria-labelledby="cc-tab-plan">')
    out.append(html_planificacion(data))
    out.append('</div>')

    # Panel: Tu Mentor
    out.append('<div id="cc-panel-mentor" class="cc-tabs__panel" '
               'role="tabpanel" aria-labelledby="cc-tab-mentor">')
    out.append(html_tu_mentor())
    out.append('</div>')

    out.append('</div></section>')

    # Ruta de Aprendizaje
    out.append('<section class="cc-section">')
    out.append('<div class="cc-bar cc-bar--solid cc-bar--center">'
               '<h2 class="cc-bar__title">Ruta de Aprendizaje</h2></div>')
    out.append(html_ruta_aprendizaje(data))
    out.append('</section>')

    # Quicknav inferior (enlaces reales: foro creado, syllabus, página de recursos)
    out.append(html_quicknav(foro_url, encuentros_url, calendario_url, recursos_url))

    # Pager + Footer
    out.append('<nav class="cc-pager" aria-label="Navegación entre páginas">'
               '<a title="Ir a la página anterior" href="#">◀ Anterior</a> '
               '<a title="Ir a la página siguiente" href="#">Siguiente ▶</a></nav>')
    out.append('<footer class="cc-footer">'
               '<span class="cc-footer__brand">UTPL</span></footer>')

    out.append('</div>')
    return "\n".join(out)


# ----------------- main -----------------

def main():
    ap = argparse.ArgumentParser(
        description="Llena la página Inicio del curso (theme cc-*).")
    ap.add_argument("entrada", help="JSON canónico (salida.json)")
    ap.add_argument("--curso", type=int, required=True, help="ID del curso")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--titulo", default=None,
                    help="sobreescribe el título del curso (def: metadata.titulo del JSON)")
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)

    # Título del curso: --titulo > metadata.titulo > fallback
    titulo_curso = (args.titulo
                    or data.get("metadata", {}).get("titulo")
                    or data.get("metadata", {}).get("nombre")
                    or "Asignatura")

    # ---- Enlaces del quicknav (foro, encuentros, calendario, recursos) ----
    foro_url = "#"
    encuentros_url = "#"          # TODO: sin definir aún por DI
    calendario_url = "#"
    recursos_url = "#"

    if args.dry_run:
        # En dry-run no tocamos Canvas: se arma el HTML con placeholders
        # visibles para que se note qué falta resolver.
        body = html_inicio(data, titulo_curso, foro_url, encuentros_url,
                           calendario_url, recursos_url)
        print("=" * 70)
        print("PÁGINA: Inicio  (%d caracteres)" % len(body))
        print("Título del curso: %s" % titulo_curso)
        print("=" * 70)
        print(body[:3000])
        if len(body) > 3000:
            print("... [%d caracteres más]" % (len(body) - 3000))
        print("\nDRY-RUN: no se tocó Canvas (enlaces del quicknav quedaron en '#').")
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
        print("Conectado al curso: %s" % curso.name)
    except Exception as e:
        sys.exit("Error: %s" % e)

    # Buscar la página "Inicio" en el curso
    existentes = {pg.title: pg for pg in curso.get_pages()}
    pg = existentes.get("Inicio")
    if not pg:
        sys.exit("⚠ No existe la página 'Inicio' en el curso. "
                 "Créala primero con canvas_crear_paginas.py.")

    # ---- Botón "Foro de Asesoría Permanente": crear el foro si no existe ----
    foro_titulo = "Foro de asesoría permanente"
    discusiones = {d.title: d for d in curso.get_discussion_topics()}
    foro = discusiones.get(foro_titulo)
    if not foro:
        foro = curso.create_discussion_topic(
            title=foro_titulo,
            message="Espacio para consultas y asesoría permanente durante el curso.",
            discussion_type="threaded",
            published=True,
        )
        print("✓ Foro creado: %s" % foro.title)
    else:
        print("✓ Foro ya existía: %s" % foro.title)
    foro_url = "%s/courses/%d/discussion_topics/%d" % (url.rstrip("/"), args.curso, foro.id)

    # ---- Botón "Calendario de Actividades": syllabus del curso ----
    calendario_url = "%s/courses/%d/assignments/syllabus" % (url.rstrip("/"), args.curso)

    # ---- Botón "Fuentes y Recursos": página ya creada por DI ----
    pagina_recursos = existentes.get("Fuentes y Recursos") or existentes.get("Fuentes y recursos")
    if pagina_recursos:
        recursos_url = "%s/courses/%d/pages/%s" % (url.rstrip("/"), args.curso, pagina_recursos.url)
    else:
        print("⚠ No se encontró la página 'Fuentes y Recursos'; el botón quedará sin enlace.")

    body = html_inicio(data, titulo_curso, foro_url, encuentros_url,
                       calendario_url, recursos_url)

    cambios = {"body": body}
    if args.publicar:
        cambios["published"] = True
    pg.edit(wiki_page=cambios)
    print("✓ Página 'Inicio' actualizada (%d caracteres)%s"
          % (len(body), " [PUBLICADA]" if args.publicar else ""))

    # Sugerencia: marcarla como front page del curso
    print("\nSugerencia: en Canvas, abre la página 'Inicio' y haz click en")
    print("            'Use as Front Page' para que sea la portada del curso.")


if __name__ == "__main__":
    main()