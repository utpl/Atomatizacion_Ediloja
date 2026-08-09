#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_ed.py — Render de páginas semanales en la NUEVA plantilla institucional
(theme ed-*), consumiendo:
  - el JSON canónico (salida_curada.json / salida_contextualizada.json),
  - mapa_plantilla.json (iconos/banners/focalizadores subidos a Canvas Files),
  - plantilla_config.py (roles semánticos + focalizadores).

Reutiliza la lógica de estructuración de semana ya probada en
canvas_llenar_semanas.py (unidad / tema / subtemas / intro / zona de práctica),
y solo cambia la capa de presentación a la estructura ed-*.

Reglas de negocio nuevas (plantilla ed-*):
  - Resultados de aprendizaje: en TODAS las semanas de la unidad.
  - Contextualización: en un collapse, solo donde el RA inicia.
  - Intro: el texto entre el título de unidad y el primer subtema (1.x):
      * <= UMBRAL_INTRO_PALABRAS  -> va arriba en #introduction
      * >  UMBRAL_INTRO_PALABRAS  -> arriba va la frase por defecto y el texto
                                     se mueve a una pestaña 'Introducción'
                                     (primer tab del ctab, antes de 1.x)
  - Frase final (#final_content): siempre placeholder por ahora.
  - Autoevaluación: pestaña solo en la última semana de la unidad, embebida por
    iframe (recurso externo). En las demás semanas esa pestaña no se renderiza.

Uso:
    python render_ed.py salida_curada.json --curso 89932 --semana 1 \
        --mapa-plantilla mapa_plantilla.json -o muestra_semana_1.html
"""

import argparse
import json
import re
import sys

import canvas_llenar_semanas as base   # reutiliza estructura + helpers
import plantilla_config as cfg


# ----------------- helpers de imagen -----------------

def _canvas_y_curso_desde_mapa(mapa):
    """Deriva (canvas_url, curso) de cualquier url del mapa."""
    for e in mapa.values():
        m = re.match(r"(https?://[^/]+)/courses/(\d+)/files/", e.get("url", ""))
        if m:
            return m.group(1), m.group(2)
    return "", ""


def cargar_mapa_paginas(ruta="mapa_paginas.json"):
    """Lee mapa_paginas.json -> {titulo_pagina: url_real}. Vacío si no existe.
    Lo genera canvas_crear_paginas.py al crear/reusar las páginas; permite que
    los botones apunten a la URL real aunque Canvas renombre los slugs."""
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, ValueError):
        return {}
    out = {}
    for titulo, v in d.items():
        if isinstance(v, str):
            out[titulo] = v
        elif isinstance(v, dict):
            out[titulo] = v.get("url") or v.get("html_url") or ""
    return out


def url_pagina(mapa_urls, titulo, fallback="#"):
    """URL real de una página por título; fallback si no está en el mapa."""
    return (mapa_urls or {}).get(titulo) or fallback


def img_tag(mapa, canvas_url, curso, nombre, width, height, alt=""):
    """<img> institucional con data-api-endpoint (editable en Canvas).
    NO se emite atributo id: el mismo icono aparece muchas veces por página
    (focalizadores, tabs...) y un id repetido rompe el getElementById del theme,
    dejando inservibles los tabs ctab de la 2ª pestaña en adelante."""
    e = mapa.get(nombre)
    if not e:
        # asset ausente en el mapa: comentario visible para depurar, sin romper
        return "<!-- FALTA asset en mapa_plantilla.json: %s -->" % base.esc(nombre)
    fid = e["file_id"]
    src = e["url"]
    api = "%s/api/v1/courses/%s/files/%s" % (canvas_url.rstrip("/"), curso, fid)
    role = "" if alt else 'role="presentation" '
    return ('<img %ssrc="%s" alt="%s" width="%d" height="%d" '
            'data-api-endpoint="%s" data-api-returntype="File" />'
            % (role, src, base.esc(alt), width, height, api))


# ----------------- render de bloques en ed-* -----------------

def render_tabla_ed(b):
    enc = b.get("encabezados", [])
    filas = b.get("filas", [])
    ncols = len(enc) or (len(filas[0]) if filas else 1)
    titulo = b.get("titulo") or "Detalle"
    out = ['<table class="table-general">']
    out.append('<caption>%s</caption>' % base.md_inline(titulo))
    if enc:
        out.append('<thead><tr>%s</tr></thead>'
                   % "".join('<th scope="col">%s</th>' % base.md_inline(c) for c in enc))
    out.append('<tbody>')
    for fila in filas:
        celdas = "".join('<td style="text-align: center;">%s</td>' % base.md_inline(c) for c in fila)
        out.append('<tr>%s</tr>' % celdas)
    out.append('</tbody>')
    if b.get("nota"):
        out.append('<tfoot><tr><td colspan="%d">Nota. %s</td></tr></tfoot>'
                   % (ncols, base.md_inline(b["nota"])))
    out.append('</table>')
    return "\n".join(out)


def _resolver_src_imagen(b, mapa_imagenes):
    """Resuelve la URL embebible de una figura a partir de mapa_imagenes.json,
    que tiene forma {nombre_archivo: {file_id, preview_url, download_url}}.
    Estrategia (igual que el render base):
      1. src absoluto (http/https) -> tal cual.
      2. src local -> basename -> buscar en el mapa -> preview_url/download_url.
      3. src vacío + número -> probar 'Figura_N.(png|jpeg|jpg|_a.png)'.
    Devuelve (src_final|None, alt, file_id|None)."""
    img = b.get("imagen") or {}
    src = img.get("src", "") or ""
    num = b.get("numero")
    titulo = b.get("titulo") or ""
    alt = img.get("alt") or titulo or "Figura"

    if src.startswith("http://") or src.startswith("https://"):
        return src, alt, None

    if not isinstance(mapa_imagenes, dict):
        return None, alt, None

    def _e(nombre):
        e = mapa_imagenes.get(nombre)
        if not e:
            return None
        return (e.get("preview_url") or e.get("download_url") or e.get("url")), e.get("file_id")

    if src:
        import os as _os
        r = _e(_os.path.basename(src))
        if r:
            return r[0], alt, r[1]

    if num:
        for c in ("Figura_%s.png" % num, "Figura_%s.jpeg" % num,
                  "Figura_%s.jpg" % num, "Figura_%s_a.png" % num):
            r = _e(c)
            if r:
                return r[0], (titulo or ("Figura %s" % num)), r[1]

    return None, alt, None


def render_figura_ed(b, mapa, canvas_url, curso, mapa_imagenes=None):
    num = b.get("numero", "")
    titulo = b.get("titulo", "")
    src_final, alt, fid = _resolver_src_imagen(b, mapa_imagenes)

    if src_final:
        api = ('data-api-endpoint="%s/api/v1/courses/%s/files/%s" data-api-returntype="File" '
               % (canvas_url.rstrip("/"), curso, fid)) if fid else ""
        img_html = ('<img src="%s" alt="%s" width="500" %s/>'
                    % (base.esc(src_final), base.esc(alt), api))
    else:
        # placeholder visible pero discreto (la imagen se resuelve al subir imágenes)
        img_html = ('<!-- imagen pendiente: %s -->'
                    '<span style="display:inline-block;border:1px dashed #b91c1c;color:#b91c1c;'
                    'padding:6px 10px;border-radius:4px;">Figura %s pendiente</span>'
                    % (base.esc((b.get("imagen") or {}).get("src", "")), base.esc(str(num))))

    out = ['<figure class="container-figure">']
    out.append('<figcaption><p><strong>Figura %s.<br /></strong>%s</p></figcaption>'
               % (base.esc(str(num)), base.md_inline(titulo)))
    out.append('<p>%s</p>' % img_html)
    if b.get("nota"):
        out.append('<footer><p>Nota. %s</p></footer>' % base.md_inline(b["nota"]))
    out.append('</figure>')
    return "\n".join(out)


def render_focalizador_ed(b, mapa, canvas_url, curso):
    contenido = b.get("contenido", [])
    if not contenido:
        return ""
    info = cfg.focalizador_de(b.get("subtipo"))
    icono = img_tag(mapa, canvas_url, curso, info["icono"], 80, 80)
    inner = "\n".join(render_bloque_ed(c, mapa, canvas_url, curso) for c in contenido)
    return ('<div class="%s">'
            '<p style="text-align: center;">%s</p>'
            '<div class="content-focuser">%s</div>'
            '</div>') % (info["clase"], icono, inner)


def render_recurso_ed(b, mapa, canvas_url, curso):
    desc = (b.get("descripcion") or "").strip()
    for pat in (r"^Recurso\s+interactivo\s*[-–—:]\s*", r"^Recurso\s+de\s+aprendizaje\s*[-–—:]\s*",
                r"^Recurso\s+complementario\s*[-–—:]\s*", r"^Recurso\s*[-–—:]\s*"):
        nuevo = re.sub(pat, "", desc, flags=re.IGNORECASE)
        if nuevo != desc:
            desc = nuevo.strip()
            break
    icono = img_tag(mapa, canvas_url, curso, "focalizadores/video", 50, 50)
    return ('<div class="focuser important">'
            '<p style="text-align: center;">%s</p>'
            '<div class="content-focuser"><p>%s</p></div></div>'
            % (icono, base.md_inline(desc)))


def render_bloque_ed(b, mapa, canvas_url, curso, mapa_imagenes=None):
    t = b.get("tipo")
    if t == "parrafo":
        return "<p>%s</p>" % base.md_inline(b.get("texto", ""))
    if t == "lista":
        tag = "ol" if b.get("estilo") == "numerada" else "ul"
        items = "".join("<li>%s</li>" % base.md_inline(i) for i in b.get("items", []))
        return "<%s>%s</%s>" % (tag, items, tag)
    if t == "subtitulo":
        nivel = b.get("nivel", 4)
        tag = "h5" if nivel <= 4 else "h6"
        txt = (b.get("texto") or "").strip()
        return ("<%s>%s</%s>" % (tag, base.md_inline(txt), tag)) if txt else ""
    if t == "tabla":
        return render_tabla_ed(b)
    if t == "figura":
        return render_figura_ed(b, mapa, canvas_url, curso, mapa_imagenes)
    if t == "focalizador":
        return render_focalizador_ed(b, mapa, canvas_url, curso)
    if t == "recurso":
        return render_recurso_ed(b, mapa, canvas_url, curso)
    if t == "cita":
        return "<blockquote>%s</blockquote>" % base.md_inline(b.get("texto", ""))
    if t == "enlace":
        return ('<p><a href="%s" target="_blank" rel="noopener">%s</a></p>'
                % (base.esc(b.get("url", "")), base.md_inline(b.get("texto") or b.get("url") or "")))
    if t == "video":
        url = b.get("url") or ""
        vid = base.youtube_id(url)
        if vid:
            return ('<p><iframe src="https://www.youtube.com/embed/%s" width="640" height="360" '
                    'allowfullscreen title="Video" style="max-width:100%%;"></iframe></p>' % base.esc(vid))
        return '<p><a href="%s" target="_blank" rel="noopener">Video</a></p>' % base.esc(url)
    return ""


def render_bloques_ed(bloques, mapa, canvas_url, curso, mapa_imagenes=None):
    return "\n".join(
        h for h in (render_bloque_ed(b, mapa, canvas_url, curso, mapa_imagenes) for b in bloques) if h
    )


# ----------------- utilidades de estructura -----------------

def contar_palabras(bloques):
    """Cuenta palabras del texto plano (párrafos y listas) de una lista de bloques."""
    texto = []
    for b in bloques:
        if b.get("tipo") == "parrafo":
            texto.append(b.get("texto", ""))
        elif b.get("tipo") == "lista":
            texto.extend(b.get("items", []))
    plano = re.sub(r"[*_`#>\[\]()]", " ", " ".join(texto))
    return len(plano.split())


def numero_romano(n):
    romanos = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    return romanos[n] if 0 <= n < len(romanos) else str(n)


# ----------------- ensamblado de la semana en ed-* -----------------

def titulo_unidad_de(semanas, unidad_num):
    """Busca el nombre de la unidad recorriendo TODAS las semanas de esa unidad.
    El bloque 'Unidad N: Nombre' suele estar solo en la primera semana, así que
    las semanas siguientes deben heredarlo."""
    for s in semanas:
        if s.get("numero") != unidad_num:
            continue
        est = base.estructurar_semana(s.get("bloques", []))
        t = est.get("titulo_unidad")
        if t:
            return t
    return None


def html_semana_ed(data, semana_idx, mapa, canvas_url, curso,
                   base_recursos=None, mapa_imagenes=None, mapa_urls=None):
    base_recursos = base_recursos or base.BASE_RECURSOS_DEFAULT
    semanas = base.obtener_semanas(data)
    u = semanas[semana_idx - 1]
    unidad_num = u.get("numero")
    est = base.estructurar_semana(u.get("bloques", []))

    ult_de_unidad = base.es_ultima_semana_de_unidad(semanas, semana_idx)
    autoeval = base.autoeval_por_unidad(data, unidad_num)
    mostrar_autoeval = ult_de_unidad and (autoeval is not None)

    # RA + contextualización (plan por semana: RA siempre, ctx donde inicia)
    plan = base.plan_outcomes_por_semana(data)
    info_ra = plan.get(semana_idx, {}) or {}

    out = ['<div class="ed-container">']

    # ---- Header/banner de unidad (SOLO la imagen; el título va DEBAJO) ----
    # En la plantilla nueva el banner es solo el fondo; el título de la unidad
    # se coloca como texto de la página, entre el nav de semanas y el recuadro
    # de RA (ver más abajo), NO encima del banner.
    tit_unidad = est.get("titulo_unidad") or titulo_unidad_de(semanas, unidad_num) \
                 or ("Unidad %s" % unidad_num)
    m = re.match(r"\s*Unidad\s*\d+\s*[:.\-]?\s*(.*)$", tit_unidad, re.IGNORECASE)
    nombre_unidad = m.group(1).strip() if m else tit_unidad
    out.append('<section id="week_course" class="course-header">'
               '<header class="ed-header"></header></section>')
    # HTML del título de unidad, para insertarlo debajo del nav (ver abajo).
    titulo_unidad_html = ('<h2 id="unit_%s" class="unit"><strong>Unidad %s.</strong> %s</h2>'
                          % (unidad_num, unidad_num, base.md_inline(nombre_unidad)))

    # ---- Nav de semanas ----
    home = img_tag(mapa, canvas_url, curso, "iconos/home", 30, 30)
    home_h = img_tag(mapa, canvas_url, curso, "iconos/hover/home", 30, 30)
    href_inicio = url_pagina(mapa_urls, "Inicio", "#")
    enlaces = []
    for i, s in enumerate(semanas, 1):
        activo = ' aria-current="page"' if i == semana_idx else ''
        nom_i = s.get("nombre_pagina") or ("Semana %d" % i)
        href = url_pagina(mapa_urls, nom_i, "#semana-%d" % i)
        enlaces.append('<a title="Semana %d" href="%s"%s>%d</a>'
                       % (i, base.esc(href), activo, i))
    out.append('<section class="container-homepage-bnt">'
               '<a class="homepage-btn" href="%s">%s %s</a>'
               '<div class="block"><span><strong>Semanas</strong></span> %s</div>'
               '</section>' % (base.esc(href_inicio), home, home_h, " ".join(enlaces)))

    # ---- Título de unidad: DEBAJO del banner y del nav, ENCIMA del recuadro RA ----
    out.append(titulo_unidad_html)

    # ---- Resultados de aprendizaje + Contextualización (collapse) ----
    ic_ra = img_tag(mapa, canvas_url, curso, "iconos/resultado_aprendizaje", 30, 30)
    ra = info_ra.get("ra")
    if isinstance(ra, list):
        ra_items = "".join("<li>%s</li>" % base.md_inline(x) for x in ra)
    elif ra:
        ra_items = "<li>%s</li>" % base.md_inline(ra)
    else:
        ra_items = "<li><em>Resultado de aprendizaje pendiente.</em></li>"

    out.append('<section id="container-learning-outcome">')
    out.append('<div class="title-learning-outcomes">'
               '<div><p style="text-align: center;">%s</p>'
               '<h3 style="text-align: center;">Resultados de aprendizaje</h3></div>'
               '<div id="learning_outcomes"><ul>%s</ul></div></div>' % (ic_ra, ra_items))

    ctx = info_ra.get("ctx") or []
    if info_ra.get("mostrar_ctx") and ctx:
        ctx_html = "".join("<p>%s</p>" % base.md_inline(p) for p in ctx)
        out.append('<div class="collapse">'
                   '<a class="collapse__link" role="button" href="#contenido-collapse" '
                   'aria-expanded="false"> <span>Contextualización</span> '
                   '<span class="collapse__icon" aria-hidden="true">+</span> </a>'
                   '<div id="contenido-collapse" class="collapse__content">'
                   '<div id="contextualization" class="collapse__inner">%s</div></div></div>'
                   % ctx_html)
    else:
        # IMPORTANTE: el JS del theme (interaction.js) hace
        #   const collapse = document.querySelector(".collapse");
        #   const link = collapse.querySelector(".collapse__link");
        # SIN comprobar null y SIN try/catch. Si la página no tiene ningún
        # ".collapse", esa línea revienta con TypeError y detiene el resto
        # del callback "load" — incluyendo el registro del listener de los
        # tabs ".ctab__tab" (subtemas), que se define más abajo en el mismo
        # archivo. Por eso en las semanas sin contextualización (mostrar_ctx
        # falso) los subtemas dejaban de abrir. Se emite un ".collapse"
        # vacío y oculto solo para que ese querySelector nunca sea null.
        out.append('<div class="collapse" style="display:none;" aria-hidden="true">'
                   '<a class="collapse__link" href="#" tabindex="-1"></a></div>')
    out.append('</section>')

    # ---- Contenido ----
    out.append('<section class="content">')

    # Intro: decidir según cantidad de palabras
    intro_bloques = est.get("intro_bloques", [])
    intro_larga = contar_palabras(intro_bloques) > cfg.UMBRAL_INTRO_PALABRAS

    if intro_larga:
        out.append('<div id="introduction"><p>%s</p></div>' % base.md_inline(cfg.FRASE_INTRO_DEFAULT))
    else:
        cuerpo = render_bloques_ed(intro_bloques, mapa, canvas_url, curso, mapa_imagenes) \
                 if intro_bloques else ("<p>%s</p>" % base.md_inline(cfg.FRASE_INTRO_DEFAULT))
        out.append('<div id="introduction">%s</div>' % cuerpo)

    # Tabs de temas (ctab). Numeración: unidad.N continua entre semanas.
    inicio_num = base.contar_subtemas_previos_en_unidad(semanas, semana_idx)
    subtemas = est.get("subtemas", [])

    tabs = []      # (id, etiqueta, contenido_html, activo)
    if intro_larga:
        tabs.append(("ctab-intro", "Introducción",
                     render_bloques_ed(intro_bloques, mapa, canvas_url, curso, mapa_imagenes), True))

    for j, sub in enumerate(subtemas):
        num = "%s.%d" % (unidad_num, inicio_num + j + 1)
        cuerpo = [render_bloques_ed(sub.get("bloques_propios", []), mapa, canvas_url, curso, mapa_imagenes)]
        for ss in sub.get("sub_subtemas", []):
            if ss.get("titulo"):
                cuerpo.append("<h4>%s</h4>" % base.md_inline(ss["titulo"]))
            cuerpo.append(render_bloques_ed(ss.get("bloques", []), mapa, canvas_url, curso, mapa_imagenes))
        etiqueta = "%s. %s" % (num, sub.get("titulo", ""))
        activo = (not tabs)  # el primero es el activo
        tabs.append(("ctab-%d" % (j + 1), etiqueta, "\n".join(cuerpo), activo))

    if tabs:
        out.append('<div id="topics" class="ctab">')
        nav = []
        for tid, etiqueta, _, activo in tabs:
            cls = "ctab__tab is-active" if activo else "ctab__tab"
            nav.append('<li class="%s" data-target="%s">%s</li>' % (cls, tid, base.md_inline(etiqueta)))
        out.append('<ul class="ctab__nav">%s</ul>' % "".join(nav))
        for tid, etiqueta, cuerpo, activo in tabs:
            cls = "ctab__panel is-active" if activo else "ctab__panel"
            # h3 con el título del panel (para 1.x); la Introducción usa su etiqueta
            h3 = etiqueta
            out.append('<div id="%s" class="%s"><h3>%s</h3>%s</div>'
                       % (tid, cls, base.md_inline(h3), cuerpo))
        out.append('</div>')

    # Frase final (placeholder), fuera del contenedor de tabs
    out.append('<div id="final_content"><p>%s</p></div>' % base.md_inline(cfg.FRASE_FINAL_DEFAULT))

    # ---- Zona de Práctica ----
    ic_zp = img_tag(mapa, canvas_url, curso, "iconos/zona_practica", 30, 30)
    out.append('<div class="title-section bg-color">'
               '<p style="text-align: center;">%s</p><h2>Zona de práctica</h2></div>' % ic_zp)
    out.append(_zona_practica_ed(est.get("actividades_recomendadas", []), mapa, canvas_url, curso,
                                 mostrar_autoeval, unidad_num, base_recursos, mapa_imagenes))

    out.append('</section>')   # .content
    out.append('</div>')       # .ed-container
    return "\n".join(out)


def _tab_zp(mapa, canvas_url, curso, control, rol_icono, etiqueta, activo):
    # La plantilla usa DOS iconos por tab (normal + hover); el theme muestra el
    # que contrasta según el estado del tab (activo/inactivo).
    ic_norm = img_tag(mapa, canvas_url, curso, "iconos/%s" % rol_icono, 30, 30)
    ic_hover = img_tag(mapa, canvas_url, curso, "iconos/hover/%s" % rol_icono, 30, 30)
    sel = "true" if activo else "false"
    cls = "preliminary-tabs__label is-active" if activo else "preliminary-tabs__label"
    return ('<a class="%s" role="tab" href="#%s" aria-selected="%s" '
            'aria-controls="%s" data-tab="%s"> %s %s <span>%s</span> </a>'
            % (cls, control, sel, control, control, ic_norm, ic_hover, etiqueta))


def _zona_practica_ed(actividades, mapa, canvas_url, curso,
                      mostrar_autoeval, unidad_num, base_recursos, mapa_imagenes):
    out = ['<section id="sources_resources" class="preliminary-tabs">']

    # Nav (la pestaña Autoevaluación solo si corresponde)
    # La plantilla usa el ícono "fuentes_recursos" (carpeta, normal + hover
    # blanco, igual que en la página de Inicio) en las tres pestañas — NO el
    # ícono "zona_practica" (engranaje) que sí va en el título de la sección.
    ROL_ICONO_TABS_ZP = "fuentes_recursos"
    nav = [_tab_zp(mapa, canvas_url, curso, "recommended_activities",
                   ROL_ICONO_TABS_ZP, "Actividades recomendadas", True)]
    if mostrar_autoeval:
        nav.append(_tab_zp(mapa, canvas_url, curso, "self_assessment",
                           ROL_ICONO_TABS_ZP, "Autoevaluación", False))
    nav.append(_tab_zp(mapa, canvas_url, curso, "activities_evaluated",
                       ROL_ICONO_TABS_ZP, "Actividad evaluada", False))
    out.append('<div class="preliminary-tabs__nav" role="tablist">%s</div>' % "".join(nav))

    # Panel: Actividades recomendadas
    if actividades:
        cuerpo = render_bloques_ed(
            [c for act in actividades for c in act.get("contenido", [])],
            mapa, canvas_url, curso, mapa_imagenes) or "<p>Texto</p>"
    else:
        cuerpo = ('<p>Las siguientes actividades son de carácter formativo y no tienen '
                  'calificación. Te recomendamos realizarlas para reforzar los conceptos '
                  'revisados en esta semana.</p>'
                  '<p><em>Aún no se han definido actividades recomendadas para esta semana.</em></p>')
    out.append('<div id="recommended_activities" class="preliminary-tabs__content is-active" '
               'role="tabpanel">%s</div>' % cuerpo)

    # Panel: Autoevaluación (iframe) solo si corresponde
    if mostrar_autoeval:
        url = "%s/autoevaluacion_%s.html" % (base_recursos.rstrip("/"), unidad_num)
        out.append('<div id="self_assessment" class="preliminary-tabs__content" role="tabpanel">'
                   '<p>Resuelve la autoevaluación de la unidad. Es de carácter formativo.</p>'
                   '<div style="width:100%%;border:1px solid #e5e9f2;border-radius:8px;overflow:hidden;">'
                   '<iframe src="%s" title="Autoevaluación de la Unidad %s" width="100%%" '
                   'height="800" loading="lazy" style="border:0;width:100%%;min-height:800px;">'
                   '</iframe></div>'
                   '<p style="font-size:13px;">Si no carga, ábrela en '
                   '<a href="%s" target="_blank" rel="noopener">esta página</a>.</p></div>'
                   % (base.esc(url), base.esc(str(unidad_num)), base.esc(url)))

    # Panel: Actividad evaluada
    out.append('<div id="activities_evaluated" class="preliminary-tabs__content" role="tabpanel">'
               '<p>Las actividades evaluadas y su detalle se gestionan desde el libro de '
               'calificaciones de Canvas.</p></div>')

    out.append('</section>')
    return "\n".join(out)


# ----------------- main -----------------

def _cargar(entrada, mapa_plantilla, mapa_imagenes_path):
    with open(entrada, encoding="utf-8") as f:
        data = json.load(f)
    with open(mapa_plantilla, encoding="utf-8") as f:
        mapa = json.load(f)
    mapa_img = None
    try:
        with open(mapa_imagenes_path, encoding="utf-8") as f:
            mapa_img = json.load(f)
    except FileNotFoundError:
        pass
    return data, mapa, mapa_img


def main():
    ap = argparse.ArgumentParser(description="Render de semanas en la plantilla ed-*.")
    ap.add_argument("entrada", help="JSON canónico (salida_curada.json)")
    ap.add_argument("--curso", type=int, default=None,
                    help="ID del curso (si no, se deriva del mapa de plantilla)")
    ap.add_argument("--semana", type=int, default=None,
                    help="una semana (def: todas)")
    ap.add_argument("--mapa-plantilla", default="mapa_plantilla.json")
    ap.add_argument("--mapa-imagenes", default="mapa_imagenes.json")
    ap.add_argument("--base-recursos", default=base.BASE_RECURSOS_DEFAULT)
    # Modo Canvas
    ap.add_argument("--subir", action="store_true",
                    help="sube a Canvas (edita las páginas 'Semana N')")
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    # Modo archivo (muestra)
    ap.add_argument("-o", "--salida", default=None,
                    help="modo archivo: ruta de salida (solo con --semana)")
    args = ap.parse_args()

    try:
        data, mapa, mapa_img = _cargar(args.entrada, args.mapa_plantilla, args.mapa_imagenes)
    except FileNotFoundError as e:
        sys.exit("No se encontró un archivo requerido: %s\n"
                 "¿Ejecutaste el paso de subir plantilla (genera mapa_plantilla.json)?" % e)

    canvas_url, curso_mapa = _canvas_y_curso_desde_mapa(mapa)
    curso = args.curso or curso_mapa
    if mapa_img is None:
        print("⚠ No se encontró %s; las figuras saldrán como placeholder." % args.mapa_imagenes)

    semanas = base.obtener_semanas(data)
    total = len(semanas)
    rango = [args.semana] if args.semana else list(range(1, total + 1))

    # Mapa de URLs reales de páginas (para los botones de navegación).
    # Prioridad: mapa_paginas.json (lo genera canvas_crear_paginas.py) y, en modo
    # Canvas, se completa/valida con las URLs vivas del curso.
    mapa_urls = cargar_mapa_paginas()

    # Conexión a Canvas (necesaria para subir y para resolver URLs vivas)
    curso_obj = None
    existentes = {}
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
        try:
            curso_obj = canvas.get_course(int(curso))
            print("Conectado al curso: %s\n" % curso_obj.name)
        except Exception as e:
            sys.exit("Error: %s" % e)
        existentes = {pg.title: pg for pg in curso_obj.get_pages()}
        # URLs vivas: rellenan lo que no esté ya en mapa_paginas.json
        for titulo, pg in existentes.items():
            if titulo not in mapa_urls:
                u_html = getattr(pg, "html_url", "") or ""
                if u_html:
                    mapa_urls[titulo] = u_html

    # Generar (nombre_pagina, body) por semana — ya con las URLs resueltas
    pendientes = []
    for n in rango:
        if n < 1 or n > total:
            print("  ⚠ Semana %d fuera de rango (1..%d)" % (n, total))
            continue
        nombre = semanas[n - 1].get("nombre_pagina") or ("Semana %d" % n)
        body = html_semana_ed(data, n, mapa, canvas_url, curso,
                              base_recursos=args.base_recursos, mapa_imagenes=mapa_img,
                              mapa_urls=mapa_urls)
        pendientes.append((nombre, body))

    # ---- Modo archivo (muestra) ----
    if not args.subir:
        if args.salida and len(pendientes) == 1:
            with open(args.salida, "w", encoding="utf-8") as f:
                f.write(pendientes[0][1])
            print("%s -> %s (%d caracteres)" % (pendientes[0][0], args.salida, len(pendientes[0][1])))
        else:
            for nombre, body in pendientes:
                slug = re.sub(r"\s+", "_", (nombre or "semana").strip().lower())
                fn = "%s.html" % slug
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(body)
                print("%s -> %s (%d caracteres)" % (nombre, fn, len(body)))
        return

    # ---- Modo Canvas ----
    if args.dry_run:
        for nombre, body in pendientes:
            print("=" * 70)
            print("PÁGINA: %s  (%d caracteres)" % (nombre, len(body)))
        print("\nDRY-RUN: no se tocó Canvas.")
        return

    act, falt = 0, []
    for nombre, body in pendientes:
        pg = existentes.get(nombre)
        if not pg:
            falt.append(nombre)
            print("  ⚠ No existe la página '%s'" % nombre)
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