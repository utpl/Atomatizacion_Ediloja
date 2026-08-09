#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_inicio_ed.py — Render de la página de INICIO en la nueva plantilla
institucional (theme ed-*), consumiendo el JSON canónico + mapa_plantilla.json.

Secciones (según la plantilla nueva):
  - header_course  : nombre del curso.
  - pdfs           : Plan docente / Guía didáctica (href placeholder '#').
  - preliminary    : tabs Visión General / Planificación / Tu Mentor.
       overview    -> video de presentación (si el JSON lo trae).
       planning    -> Competencias genéricas + del perfil + Metodología + Carga horaria.
       mentor      -> placeholder.
  - learning_path  : ruta de aprendizaje (una tarjeta por semana, con 'Zona de
                     evaluación' en las semanas que cierran unidad).
  - general_sections : Foro / Encuentros / Calendario / Fuentes (href placeholder).

Cada botón/tab usa el par de iconos normal+hover, igual que la plantilla.

Uso (modo archivo, para muestra):
    python render_inicio_ed.py salida_curada.json --mapa-plantilla mapa_plantilla.json -o inicio.html
Modo Canvas (sube y edita la página 'Inicio'):
    python render_inicio_ed.py salida_curada.json --curso 89935 \
        --mapa-plantilla mapa_plantilla.json --subir --publicar
"""

import argparse
import json
import sys

import render_ed as red                 # img_tag, _canvas_y_curso_desde_mapa
import canvas_llenar_inicio as ib        # buscar_pagina, obtener_semanas, esc, md_inline, youtube_id
import canvas_llenar_semanas as base     # es_ultima_semana_de_unidad
import plantilla_config as cfg


# ----------------- helpers de icono -----------------

def _par(mapa, cu, curso, rol, w=30, h=30):
    """Dos iconos: normal + hover (para tabs y botones)."""
    n = red.img_tag(mapa, cu, curso, "iconos/%s" % rol, w, h)
    hv = red.img_tag(mapa, cu, curso, "iconos/hover/%s" % rol, w, h)
    return "%s %s" % (n, hv)


def _uno(mapa, cu, curso, rol, w=30, h=30):
    """Un solo icono (para los title-section de Planificación)."""
    return red.img_tag(mapa, cu, curso, "iconos/%s" % rol, w, h)


def _bloques_html(bloques):
    """Render simple de bloques (párrafos, listas...) reutilizando render_ed."""
    return "\n".join(h for h in (red.render_bloque_ed(b, {}, "", "") for b in bloques) if h) \
        or "<p>Texto</p>"


def _bloques_bajo(bloques, patron, nivel=2):
    """Devuelve los bloques entre el subtítulo que contiene `patron` y el
    siguiente subtítulo de nivel <= `nivel`."""
    out, capturando = [], False
    for b in bloques:
        if b.get("tipo") == "subtitulo":
            txt = (b.get("texto") or "").lower()
            niv = b.get("nivel", 2)
            if capturando and niv <= nivel:
                break
            if patron in txt:
                capturando = True
                continue
        if capturando:
            out.append(b)
    return out


# ----------------- secciones -----------------

def sec_header(nombre_curso):
    # Banner VACÍO (solo la imagen de fondo). El título del curso va DEBAJO
    # como texto de la página, igual que en render_ed.py (semanas).
    return ('<section id="header_course" class="course-header">'
            '<header class="ed-header"></header></section>'
            '<h2 class="course-name"><strong>%s</strong></h2>' % ib.esc(nombre_curso))


def sec_pdfs(mapa, cu, curso):
    return ('<section id="pdfs" class="pdf-downloadable">'
            '<a id="plan_docente_pd" href="#"> %s <span>Plan docente</span> </a> '
            '<a id="guia_didactica_gd" href="#"> %s <span>Guía didáctica</span> </a>'
            '</section>'
            % (_par(mapa, cu, curso, "plan_docente", 20, 20),
               _par(mapa, cu, curso, "guia_didactica", 20, 20)))


def _overview(data, mapa, cu, curso):
    """Video de presentación desde la página 'Presentación', si existe.

    Tolerante: acepta bloques con tipo "video" (lo normal, generado por
    docx_a_json.py) Y también bloques tipo "enlace" cuyo url sea de
    YouTube/Vimeo/etc. Esto último cubre el caso de que alguien pegue la URL
    a mano en salida_contextualizada.json / salida_curada.json (los pasos de
    IA no siempre corren) y el bloque quede mal etiquetado como "enlace".
    """
    bloques = ib.buscar_pagina(data, "Presentación", "Presentacion")
    vid = None
    for b in bloques:
        if b.get("tipo") in ("video", "enlace"):
            vid = ib.youtube_id(b.get("url", ""))
            if vid:
                break
    if vid:
        return ('<div id="overview" class="preliminary-tabs__content" role="tabpanel">'
                '<p style="text-align: center;">'
                '<iframe id="video_presentacion" title="YouTube video player" '
                'src="https://www.youtube.com/embed/%s" width="560" height="315" '
                'loading="lazy" allowfullscreen="allowfullscreen" '
                'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
                'gyroscope; picture-in-picture; web-share" frameborder="0"></iframe></p></div>'
                % ib.esc(vid))
    return ('<div id="overview" class="preliminary-tabs__content" role="tabpanel">'
            '<!-- TODO: el JSON no trae video de presentación; se incorpora cuando esté -->'
            '<p>Te damos la bienvenida a la asignatura. El video de presentación se '
            'incorporará próximamente.</p></div>')


def _planning(data, mapa, cu, curso):
    info = ib.buscar_pagina(data, "Información general", "Informacion general")
    met = ib.buscar_pagina(data, "Metodología de aprendizaje", "Metodologia de aprendizaje")

    genericas = _bloques_bajo(info, "genéric") or _bloques_bajo(info, "generic")
    perfil = _bloques_bajo(info, "perfil profesional")
    metod = [b for b in met if not (b.get("tipo") == "subtitulo" and "metodolog" in (b.get("texto") or "").lower())]

    out = ['<div id="planning" class="preliminary-tabs__content" role="tabpanel">']
    out.append('<div class="title-section"><p style="text-align: center;">%s</p>'
               '<h3>Propósito de aprendizaje</h3></div>'
               % _uno(mapa, cu, curso, "propositos_aprendizaje"))
    out.append('<h4><strong>Competencias genéricas</strong></h4>')
    out.append('<div id="generic_skills">%s</div>' % _bloques_html(genericas))
    out.append('<h4><strong>Competencias del perfil profesional</strong></h4>')
    out.append('<div id="professional_profile_skills">%s</div>' % _bloques_html(perfil))
    out.append('<div class="title-section"><p style="text-align: center;">%s</p>'
               '<h3>Metodología de aprendizaje</h3></div>'
               % _uno(mapa, cu, curso, "metodologia_aprendizaje"))
    out.append('<div id="learning_methodology">%s</div>' % _bloques_html(metod))
    out.append('<div class="title-section"><p style="text-align: center;">%s</p>'
               '<h3>Carga horaria</h3></div>'
               % _uno(mapa, cu, curso, "carga_horaria"))
    out.append(
        '<!-- TODO: carga horaria ficticia (simulada). Reemplazar con datos '
        'reales de la guía cuando estén disponibles en el JSON. -->'
        '<div id="workload"><ul class="workload-list">'
        '<li><strong>Aprendizaje Autónomo (AA):</strong> 64 horas</li>'
        '<li><strong>Aprendizaje Práctico Experimental (APE):</strong> 32 horas</li>'
        '<li><strong>Aprendizaje en Contacto con el Docente (ACD):</strong> 48 horas</li>'
        '<li><strong>Total:</strong> 144 horas</li>'
        '</ul></div>')
    out.append('</div>')
    return "\n".join(out)


def _mentor():
    """Tu Mentor: datos ficticios "quemados" mientras se define la integración
    con el sistema académico de UTPL (no viene en el JSON)."""
    return (
        '<div id="mentor" class="preliminary-tabs__content" role="tabpanel">'
        '<!-- TODO: datos ficticios de docente (simulados). Reemplazar cuando '
        'exista integración con el sistema académico de UTPL. -->'
        '<div class="mentor-card">'
        '<img class="mentor-photo" '
        'src="https://ui-avatars.com/api/?name=Maria+Fernanda+Torres&background=54a0f1&color=fff&size=200" '
        'alt="Foto del docente" />'
        '<div class="mentor-info">'
        '<p class="mentor-name"><strong>Mg. María Fernanda Torres</strong></p>'
        '<p class="mentor-role">Docente titular</p>'
        '<p class="mentor-org">Universidad Técnica Particular de Loja</p>'
        '<p class="mentor-email">📧 <a href="mailto:mftorres@utpl.edu.ec">mftorres@utpl.edu.ec</a></p>'
        '<p class="mentor-bio">Docente e investigadora en el área de Gastronomía '
        'Sostenible, con experiencia en gestión de proyectos gastronómicos y '
        'desarrollo curricular. Le apasiona el acompañamiento cercano a los '
        'estudiantes durante todo el curso.</p>'
        '</div></div></div>'
    )


def sec_preliminary(data, mapa, cu, curso):
    nav = ('<div class="preliminary-tabs__nav" role="tablist">'
           '<a class="preliminary-tabs__label" role="tab" href="#overview" '
           'aria-selected="true" aria-controls="overview" data-tab="overview"> %s '
           '<span>Visión General</span> </a> '
           '<a class="preliminary-tabs__label" role="tab" href="#planning" '
           'aria-selected="false" aria-controls="planning" data-tab="planning"> %s '
           '<span>Planificación</span> </a> '
           '<a class="preliminary-tabs__label" role="tab" href="#mentor" '
           'aria-selected="false" aria-controls="mentor" data-tab="mentor"> %s '
           '<span>Tu docente</span> </a></div>'
           % (_par(mapa, cu, curso, "vision_general"),
              _par(mapa, cu, curso, "planificacion"),
              _par(mapa, cu, curso, "mentor")))
    return ('<section id="preliminary" class="preliminary-tabs">%s%s%s%s</section>'
            % (nav, _overview(data, mapa, cu, curso),
               _planning(data, mapa, cu, curso), _mentor()))


def sec_ruta(data, mapa, cu, curso, mapa_urls=None):
    semanas = ib.obtener_semanas(data)
    total = len(semanas) if semanas else 8

    # ---- TODO: avance ficticio "quemado" (DI pidió simulado por ahora) ----
    # Reemplazar cuando exista una fuente real de progreso del estudiante.
    avance_pct = 50
    completadas = round(total * avance_pct / 100)
    semana_actual = min(total, completadas + 1)

    marker = _uno(mapa, cu, curso, "progress") or ""

    # El CSS de la plantilla SOLO tiene reglas para week-5 y week-8.
    # Para cualquier otro número (3, 4, 6, 7...) forzamos el layout
    # con style inline, o el grid cae al default repeat(4,1fr) y los .week
    # no tienen display:grid, desparramando todo.
    css_cubierto = total in (5, 8)
    wb_style = '' if css_cubierto else ' style="grid-template-columns: repeat(%d, 1fr);"' % total
    wk_style = '' if css_cubierto else ' style="display:grid;justify-content:center;text-align:center;row-gap:0.5em;"'

    out = ['<section id="learning_path" class="week-%d">' % total,
           '<h2 class="title-path">Ruta de aprendizaje</h2>',
           '<div class="container-progress">',
           '<div class="route-marker"><p>%s</p></div>' % marker,
           '<div class="route-bar"><span id="progress_completed"></span></div>',
           '<div class="route-percentage"><p><strong>%d%%</strong></p></div>' % avance_pct,
           '</div>',
           '<div class="weeks-block"%s>' % wb_style]

    for i in range(1, total + 1):
        nom = (semanas[i - 1].get("nombre_pagina") if semanas else None) or ("Semana %d" % i)
        href = red.url_pagina(mapa_urls, nom, "#semana-%d" % i)

        if i < semana_actual:
            estado_clase, estado_txt = "completed", "Completado"
        elif i == semana_actual:
            estado_clase, estado_txt = "in-progress", "En progreso"
        else:
            estado_clase, estado_txt = "waiting", "En espera"

        # Atributos data-api-* para enlaces internos de Canvas
        data_attrs = ""
        if href.startswith("http") and cu and curso:
            if "/pages/" in href:
                slug = href.split("/pages/")[-1].split("?")[0]
            else:
                slug = nom.lower().replace(" ", "-")
            api_ep = "%s/api/v1/courses/%s/pages/%s" % (cu.rstrip("/"), curso, slug)
            data_attrs = ' data-api-endpoint="%s" data-api-returntype="Page"' % ib.esc(api_ep)

        # Zona de evaluación donde cierra unidad
        zona = ""
        if semanas and base.es_ultima_semana_de_unidad(semanas, i):
            zona = ' <a class="assessment" title="Zona de evaluación" href="#">Zona de evaluación</a>'
        elif not semanas and i % 2 == 0:
            zona = ' <a class="assessment" title="Zona de evaluación" href="#">Zona de evaluación</a>'
        out.append('<div class="week"%s><span class="state">%s</span> '
                   '<a class="btn-week %s" title="Semana %d" href="%s"%s>%d</a>%s</div>'
                   % (wk_style, estado_txt, estado_clase, i, ib.esc(href), data_attrs, i, zona))

    out.append('</div></section>')
    return "\n".join(out)


def sec_generales(mapa, cu, curso, mapa_urls=None, foro_url=None):
    def btn(rol, etiqueta, titulo_pagina=None, href_directo=None):
        if href_directo:
            href = href_directo
        elif titulo_pagina:
            href = red.url_pagina(mapa_urls, titulo_pagina, "#")
        else:
            href = "#"
        return ('<a class="btn-general" title="%s" href="%s"> %s <span>%s</span></a>'
                % (ib.esc(etiqueta), ib.esc(href), _par(mapa, cu, curso, rol), ib.esc(etiqueta)))

    # Calendario: link directo al syllabus del curso (no depende de mapa_urls)
    calendario_url = "#"
    if cu and curso:
        calendario_url = "%s/courses/%s/assignments/syllabus" % (cu.rstrip("/"), curso)

    return ('<section id="general_sections"><div class="general-container">%s %s %s %s</div></section>'
            % (btn("foro_asesoria_permanente", "Foro de asesoría permanente",
                   href_directo=foro_url or "#"),
               btn("encuentros_en_linea", "Encuentros en línea", "Encuentros en línea"),
               btn("calendario_actividades", "Calendario de actividades",
                   href_directo=calendario_url),
               btn("fuentes_recursos", "Fuentes y recursos", "Fuentes y recursos")))


def html_inicio_ed(data, mapa, canvas_url, curso, titulo=None, mapa_urls=None, foro_url=None):
    nombre = (titulo or data.get("metadata", {}).get("asignatura")
              or data.get("metadata", {}).get("titulo")
              or data.get("metadata", {}).get("nombre") or "Asignatura")
    cu = canvas_url
    return ('<div class="ed-container">%s%s%s%s%s</div>'
            % (sec_header(nombre),
               sec_pdfs(mapa, cu, curso),
               sec_preliminary(data, mapa, cu, curso),
               sec_ruta(data, mapa, cu, curso, mapa_urls),
               sec_generales(mapa, cu, curso, mapa_urls, foro_url)))


# ----------------- main -----------------

def main():
    ap = argparse.ArgumentParser(description="Render de la página de Inicio en ed-*.")
    ap.add_argument("entrada")
    ap.add_argument("--curso", type=int, default=None)
    ap.add_argument("--mapa-plantilla", default="mapa_plantilla.json")
    ap.add_argument("--titulo", default=None)
    ap.add_argument("--subir", action="store_true")
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-o", "--salida", default=None)
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)
    try:
        with open(args.mapa_plantilla, encoding="utf-8") as f:
            mapa = json.load(f)
    except FileNotFoundError:
        sys.exit("No existe %s. Ejecuta antes el paso de subir plantilla." % args.mapa_plantilla)

    canvas_url, curso_mapa = red._canvas_y_curso_desde_mapa(mapa)
    curso = args.curso or curso_mapa

    # Mapa de URLs reales (mapa_paginas.json + URLs vivas de Canvas en modo subir)
    mapa_urls = red.cargar_mapa_paginas()
    curso_obj = None
    if args.subir and not args.dry_run:
        try:
            from canvasapi import Canvas
        except ImportError:
            sys.exit("Falta canvasapi:  pip install canvasapi")
        import os
        url = os.environ.get("CANVAS_URL")
        token = os.environ.get("CANVAS_TOKEN")
        if not url or not token:
            sys.exit("Define CANVAS_URL y CANVAS_TOKEN.")
        if not curso:
            sys.exit("No se pudo determinar el curso. Pasa --curso.")
        canvas = Canvas(url, token)
        curso_obj = canvas.get_course(int(curso))
        print("Conectado al curso: %s" % curso_obj.name)
        for pg in curso_obj.get_pages():
            if pg.title not in mapa_urls:
                u_html = getattr(pg, "html_url", "") or ""
                if u_html:
                    mapa_urls[pg.title] = u_html

    # ---- Foro de Asesoría Permanente: crear el foro si no existe ----
    foro_url = None
    if curso_obj:
        foro_titulo = "Foro de asesoría permanente"
        discusiones = {d.title: d for d in curso_obj.get_discussion_topics()}
        foro = discusiones.get(foro_titulo)
        if not foro:
            foro = curso_obj.create_discussion_topic(
                title=foro_titulo,
                message="Espacio para consultas y asesoría permanente durante el curso.",
                discussion_type="threaded",
                published=True,
            )
            print("✓ Foro creado: %s" % foro.title)
        else:
            print("✓ Foro ya existía: %s" % foro.title)
        foro_url = "%s/courses/%d/discussion_topics/%d" % (url.rstrip("/"), int(curso), foro.id)

    body = html_inicio_ed(data, mapa, canvas_url, curso, titulo=args.titulo,
                          mapa_urls=mapa_urls, foro_url=foro_url)

    if not args.subir:
        salida = args.salida or "muestra_inicio.html"
        with open(salida, "w", encoding="utf-8") as f:
            f.write(body)
        print("Inicio -> %s (%d caracteres)" % (salida, len(body)))
        return

    if args.dry_run:
        print("PÁGINA: Inicio (%d caracteres)\nDRY-RUN: no se tocó Canvas." % len(body))
        return

    existentes = {pg.title: pg for pg in curso_obj.get_pages()}
    pg = existentes.get("Inicio")
    if not pg:
        sys.exit("No existe la página 'Inicio'. Créala con el paso de páginas.")
    cambios = {"body": body}
    if args.publicar:
        cambios["published"] = True
    # Inicio DEBE ser la Front Page del curso. Una página solo puede ser front
    # page si está publicada, así que forzamos published al marcarla.
    cambios["published"] = True
    cambios["front_page"] = True
    pg.edit(wiki_page=cambios)
    # Además, el curso debe usar la página wiki como su home (si no, la front
    # page existe pero el curso muestra otra vista al entrar).
    try:
        curso_obj.update(course={"default_view": "wiki"})
    except Exception as e:
        print("  AVISO: no se pudo fijar la portada del curso como página: %s" % e)
    print("✓ Página 'Inicio' actualizada y marcada como FRONT PAGE (%d caracteres)%s"
          % (len(body), " [PUBLICADA]" if args.publicar else ""))


if __name__ == "__main__":
    main()