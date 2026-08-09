#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_utpl.py — Render de páginas semanales en el vocabulario ed-* que
estiliza el tema global de Canvas.

Por qué existe
--------------
render_ed.py emite clases cc-* (cc-curso, cc-tabs, cc-outcome…). Ese es el
tema ANTERIOR: su hoja style_app.css está desactualizada y no se sube al
Theme Editor. El tema vigente estiliza ed-* (ed-container, ctab,
title-learning-outcomes, table-general, focuser…), que es lo que produce el
MIGRADOR y lo que se ve en los cursos reales.

Publicar con cc-* deja las páginas sin estilo. De ahí este porte.

Qué se reutiliza y qué no
-------------------------
Se reutiliza TODA la lógica de estructuración de canvas_llenar_semanas:
reparto de subtemas, plan de resultados por semana, detección de la última
semana de la unidad, agrupación de actividades. Eso está probado y no se
toca.

Se reescribe SOLO la capa de presentación. render_ed.py queda intacto para
poder comparar las dos salidas.

Referencia del HTML destino: curso 90015 de utpl.test.instructure.com,
generado por el migrador y aprobado por Diseño Instruccional.

Uso:
    python render_utpl.py canonico.json --curso 90019 --semana 1 \
        --mapa-plantilla mapa_plantilla.json -o /tmp/semana1.html
"""

import argparse
import json
import re
import sys

import canvas_llenar_semanas as base
import plantilla_config as cfg

esc = base.esc
md_inline = base.md_inline


# ---------------------------------------------------------------------------
# Mapeo cc-* -> ed-*
# ---------------------------------------------------------------------------
# cc-curso            -> ed-container
# cc-banner*          -> section#week_course.course-header > header.ed-header
# cc-weeknav*         -> section.container-homepage-bnt + div.block
# cc-outcome*         -> section#container-learning-outcome con CUATRO divs
#                        hermanos: title/content x2. NO es un bloque con
#                        aside+body, y no lleva boton colapsable: la
#                        contextualizacion va desplegada (decision de DI).
# cc-section          -> section.content
# cc-tabs (subtemas)  -> div.ctab > ul.ctab__nav > li.ctab__tab
#                        + div.ctab__panel  (paneles hermanos, no envueltos)
# cc-figure*          -> figure.container-figure > p > img + footer
# cc-table*           -> table.table-general con caption/thead/tbody/tfoot
# cc-recurso          -> div.container-resources
# cc-bar              -> div.title-section.bg-color > h2
# zona de practica    -> section#sources_resources.preliminary-tabs
# cierre              -> div#final_content
# cc-footer           -> footer.ed-footer


def _img(mapa, canvas_url, curso, nombre_logico, ancho=30, alto=None, alt=""):
    """<img> de un asset de la plantilla, resuelto contra mapa_plantilla.json."""
    entrada = (mapa or {}).get(nombre_logico) or {}
    src = entrada.get("url", "")
    if not src:
        return ""
    medidas = 'width="%d"' % ancho
    if alto:
        medidas += ' height="%d"' % alto
    return ('<img role="presentation" src="%s" alt="%s" %s loading="lazy">'
            % (esc(src), esc(alt), medidas))


def _icono_focalizador(subtipo, mapa, canvas_url, curso):
    info = cfg.focalizador_de(subtipo)
    return _img(mapa, canvas_url, curso, info["icono"], 80, 80)


def _clase_focalizador(subtipo):
    """La clase que espera el tema: `focuser {tipo}`, dos clases separadas.

    Los cuatro confirmados por DI llevan el nombre en ingles; el resto usa el
    del enum en espanol hasta que DI confirme sus traducciones.
    """
    en_ingles = {"importante": "important", "lectura": "reading",
                 "reflexione": "reflection", "video": "video"}
    return "focuser %s" % en_ingles.get(subtipo, subtipo or "important")


# ---------------------------------------------------------------------------
# Bloques
# ---------------------------------------------------------------------------

def render_figura(b, mapa_imagenes=None):
    """figure.container-figure — el pie va en <footer>, no en <figcaption>.

    El figcaption, cuando existe, lleva el NUMERO y titulo; el footer lleva
    la nota de procedencia. Asi lo emite el migrador.
    """
    num = b.get("numero")
    titulo = b.get("titulo") or ""
    nota = b.get("nota") or ""
    img = b.get("imagen") or {}
    alt = img.get("alt") or titulo
    src = img.get("src") or ""

    if mapa_imagenes and src in mapa_imagenes:
        entrada = mapa_imagenes[src]
        src = entrada.get("preview_url") or entrada.get("download_url") or src

    if not src or not src.startswith("http"):
        # Figura pendiente: marcador discreto con la descripcion, no un hueco
        # roto. El alt es el encargo para quien la produzca.
        return ('<figure class="container-figure">'
                '<p><em>[Figura %s pendiente: %s]</em></p>'
                '</figure>' % (esc(str(num) if num else "?"), esc(alt)))

    cap = ""
    if num or titulo:
        cap = ('<figcaption><strong>Figura %s</strong><br><em>%s</em></figcaption>'
               % (esc(str(num) if num else ""), esc(titulo)))
    pie = ('<footer><p><em>Nota</em>. %s</p></footer>' % md_inline(nota)) if nota else ""

    return ('<figure class="container-figure">%s'
            '<p><img src="%s" alt="%s" loading="lazy"></p>%s</figure>'
            % (cap, esc(src), esc(alt), pie))


def render_tabla(b):
    """table.table-general — con caption, thead, tbody y la nota en tfoot."""
    num = b.get("numero")
    titulo = b.get("titulo") or ""
    encab = b.get("encabezados") or []
    filas = b.get("filas") or []
    nota = b.get("nota") or ""

    caption = ""
    if num or titulo:
        caption = ('<caption><strong>Tabla %s</strong> <br><em>%s</em></caption>'
                   % (esc(str(num) if num else ""), esc(titulo)))
    thead = ""
    if encab:
        thead = "<thead><tr>%s</tr></thead>" % "".join(
            '<th scope="col">%s</th>' % md_inline(c) for c in encab)
    tbody = "<tbody>%s</tbody>" % "".join(
        "<tr>%s</tr>" % "".join("<td>%s</td>" % md_inline(c) for c in fila)
        for fila in filas)
    tfoot = ""
    if nota:
        cols = max(len(encab), 1)
        tfoot = ('<tfoot><tr><td colspan="%d"><em>Nota</em>. %s</td></tr></tfoot>'
                 % (cols, md_inline(nota)))

    return ('<table class="table-general">%s%s%s%s</table>'
            % (caption, thead, tbody, tfoot))


def render_bloque(b, mapa, canvas_url, curso, mapa_imagenes=None):
    t = b.get("tipo")

    if t == "parrafo":
        return "<p>%s</p>" % md_inline(b.get("texto", ""))

    if t == "subtitulo":
        n = min(max(int(b.get("nivel", 3)), 3), 6)
        return "<h%d><strong>%s</strong></h%d>" % (n, md_inline(b.get("texto", "")), n)

    if t == "lista":
        etiqueta = "ol" if b.get("estilo") == "numerada" else "ul"
        items = "".join("<li>%s</li>" % md_inline(i) for i in (b.get("items") or []))
        return "<%s>%s</%s>" % (etiqueta, items, etiqueta)

    if t == "tabla":
        return render_tabla(b)

    if t == "figura":
        return render_figura(b, mapa_imagenes)

    if t == "focalizador":
        subtipo = b.get("subtipo")
        icono = _icono_focalizador(subtipo, mapa, canvas_url, curso)
        inner = "\n".join(
            render_bloque(c, mapa, canvas_url, curso, mapa_imagenes)
            for c in (b.get("contenido") or []))
        return ('<div class="%s">'
                '<p style="text-align: center;">%s</p>'
                '<div class="content-focuser">%s</div></div>'
                % (_clase_focalizador(subtipo), icono, inner))

    if t == "cita":
        fuente = b.get("fuente") or ""
        cola = (" (%s)" % esc(fuente)) if fuente else ""
        return ('<p style="padding-left: 40px;">%s%s</p>'
                % (md_inline(b.get("texto", "")), cola))

    if t == "recurso":
        desc = b.get("descripcion") or b.get("titulo") or ""
        return ('<div class="container-resources"><p>%s</p></div>' % md_inline(desc))

    if t in ("enlace", "video"):
        url = b.get("url") or ""
        texto = b.get("texto") or b.get("titulo") or url
        return ('<p><a class="inline_disabled" href="%s" target="_blank" '
                'rel="noopener">%s</a></p>' % (esc(url), md_inline(texto)))

    if t == "idea_clave":
        return ('<div class="focuser important"><div class="content-focuser">'
                '<p>%s</p></div></div>' % md_inline(b.get("texto", "")))

    if t == "referencia":
        return "<p>%s</p>" % md_inline(b.get("texto", ""))

    # Tipo desconocido: no se pierde el contenido ni se rompe la pagina.
    if b.get("texto"):
        return "<p>%s</p>" % md_inline(b["texto"])
    return ""


# ---------------------------------------------------------------------------
# Secciones de la pagina
# ---------------------------------------------------------------------------

def render_cabecera(titulo_unidad=None):
    """El header va VACIO: el tema pone ahi la imagen de banner.

    El titulo de unidad NO va aqui -- se veria encima de la foto. Va mas
    abajo, en div.subtitle-section, igual que en el HTML del migrador.
    El parametro se mantiene por compatibilidad de la llamada.
    """
    return ('<section id="week_course" class="course-header">'
            '<header class="ed-header"></header></section>')


def render_nav_semanas(total_semanas, activa, mapa, canvas_url, curso, mapa_urls=None):
    """section.container-homepage-bnt — boton de inicio + numeros de semana.

    Los enlaces se construyen con la URL directa de la pagina. El migrador usa
    $WIKI_REFERENCE$, que solo resuelve en exportaciones .imscc; via API hay
    que poner la URL completa.
    """
    mapa_urls = mapa_urls or {}
    home = (mapa_urls.get("Inicio")
            or "%s/courses/%s/pages/inicio" % (canvas_url.rstrip("/"), curso))
    ico_home = _img(mapa, canvas_url, curso, "iconos/home", 30, 30)
    ico_home_mo = _img(mapa, canvas_url, curso, "iconos/hover/home", 30, 30)

    enlaces = []
    for n in range(1, total_semanas + 1):
        url = (mapa_urls.get("Semana %d" % n)
               or "%s/courses/%s/pages/semana-%d" % (canvas_url.rstrip("/"), curso, n))
        cls = ' class="active"' if n == activa else ""
        enlaces.append('<a%s title="Semana %d" href="%s" data-course-type="wikiPages" '
                       'data-published="true">%d</a>' % (cls, n, esc(url), n))

    return ('<section class="container-homepage-bnt">'
            '<a class="homepage-btn" title="Inicio" href="%s">%s %s</a>'
            '<div class="block"><span><strong>Semanas</strong></span> %s</div>'
            '</section>'
            % (esc(home), ico_home, ico_home_mo, " ".join(enlaces)))


def render_outcome(ra, ctx, mapa, canvas_url, curso, mostrar_ctx=True):
    """section#container-learning-outcome con CUATRO divs hermanos.

    Sin boton ni acordeon: la contextualizacion va desplegada. El colapsable
    del tema anterior dependia de JavaScript y se eliminó por decision de DI
    (ver generar_curso.py: 'boton de Contextualización eliminado').
    """
    if not ra and not ctx:
        return ""

    ico_ra = _img(mapa, canvas_url, curso, "iconos/resultado_aprendizaje", 30,
                  alt="Resultado de aprendizaje")
    ico_ctx = _img(mapa, canvas_url, curso, "iconos/contextualizacion", 30,
                   alt="Contextualización")

    if isinstance(ra, list):
        ra_html = "".join("<p>%s</p>" % md_inline(t) for t in ra if t)
    else:
        ra_html = "<p>%s</p>" % md_inline(ra) if ra else ""

    partes = ['<section id="container-learning-outcome">',
              '<div class="title-learning-outcomes">%s<h3>Resultado de Aprendizaje</h3></div>'
              % ico_ra,
              '<div id="learning_outcomes" class="content-learning-outcomes">%s</div>'
              % ra_html]

    if mostrar_ctx and ctx:
        ctx_html = "".join("<p>%s</p>" % md_inline(p) for p in ctx)
        partes.append('<div class="title-learning-outcomes">%s<h3>Contextualización</h3></div>'
                      % ico_ctx)
        partes.append('<div id="contextualization" class="content-learning-outcomes">%s</div>'
                      % ctx_html)

    partes.append('</section>')
    return "".join(partes)


def render_contenido(estructura, mapa, canvas_url, curso, unidad_acad,
                     offset_subtema, titulo_unidad, mapa_imagenes=None):
    """section.content con el subtitulo de unidad, la intro y las pestañas.

    Las pestañas son div.ctab con ul.ctab__nav > li.ctab__tab y paneles
    HERMANOS (no envueltos en un contenedor de paneles, a diferencia de
    cc-tabs__panels). El vinculo tab-panel es data-target, no aria-controls.
    """
    out = ['<section class="content">']

    if titulo_unidad:
        m = re.match(r"^\s*(Unidad\s+\d+)[.:]?\s*(.*)$", titulo_unidad, re.I)
        if m:
            cabeza, resto = m.group(1), m.group(2)
            out.append('<div class="subtitle-section">'
                       '<h3><strong>%s.</strong> %s</h3></div>'
                       % (esc(cabeza), md_inline(resto)))
        else:
            out.append('<div class="subtitle-section"><h3>%s</h3></div>'
                       % md_inline(titulo_unidad))

    intro = estructura.get("intro_bloques") or []
    if intro:
        out.append('<div data-origen="introduccion" data-unidad="%s">' % esc(str(unidad_acad or 1)))
        for b in intro:
            out.append(render_bloque(b, mapa, canvas_url, curso, mapa_imagenes))
        out.append('</div>')

    subtemas = estructura.get("subtemas") or []
    if subtemas:
        numeros = ["%s.%d" % (unidad_acad or 1, offset_subtema + i + 1)
                   for i in range(len(subtemas))]
        ids = ["ctab-u%s-%s" % (unidad_acad or 1, n.replace(".", "-")) for n in numeros]

        out.append('<div class="content">')
        out.append('<div id="topics-u%s" class="ctab">' % esc(str(unidad_acad or 1)))
        out.append('<ul class="ctab__nav">')
        for i, (sub, sid, num) in enumerate(zip(subtemas, ids, numeros)):
            activa = " is-active" if i == 0 else ""
            out.append('<li class="ctab__tab%s" data-target="%s">%s. %s</li>'
                       % (activa, esc(sid), esc(num), esc(sub["titulo"])))
        out.append('</ul>')

        for i, (sub, sid, num) in enumerate(zip(subtemas, ids, numeros)):
            activa = " is-active" if i == 0 else ""
            out.append('<div id="%s" class="ctab__panel%s" data-codigo="%s">'
                       % (esc(sid), activa, esc(num)))
            out.append('<h4><strong>%s. %s</strong></h4>' % (esc(num), md_inline(sub["titulo"])))
            for b in sub.get("bloques_propios") or []:
                out.append(render_bloque(b, mapa, canvas_url, curso, mapa_imagenes))
            for j, ss in enumerate(sub.get("sub_subtemas") or [], 1):
                out.append('<h5><strong>%s.%d. %s</strong></h5>'
                           % (esc(num), j, md_inline(ss["titulo"])))
                for b in ss.get("bloques") or []:
                    out.append(render_bloque(b, mapa, canvas_url, curso, mapa_imagenes))
            out.append('</div>')

        out.append('</div></div>')

    out.append('</section>')
    return "\n".join(out)


def render_zona_practica(actividades, mapa, canvas_url, curso,
                         mostrar_autoeval, unidad_num, base_recursos,
                         mapa_imagenes=None):
    """section#sources_resources.preliminary-tabs — tres pestañas.

    La de Autoevaluación solo se emite en la ULTIMA semana de la unidad. Cada
    etiqueta lleva DOS iconos (normal y hover); el tema alterna entre ellos
    con CSS, no con JavaScript.
    """
    def etiqueta(destino, titulo, icono_logico, activa=False):
        ico = _img(mapa, canvas_url, curso, "iconos/%s" % icono_logico, 30, 30)
        ico_mo = _img(mapa, canvas_url, curso, "iconos/hover/%s" % icono_logico, 30, 30)
        return ('<a class="preliminary-tabs__label%s" role="tab" href="#%s" '
                'aria-selected="%s" aria-controls="%s" data-tab="%s">%s %s '
                '<span>%s</span></a>'
                % (" is-active" if activa else "", destino,
                   "true" if activa else "false", destino, destino,
                   ico_mo, ico, esc(titulo)))

    nav = [etiqueta("recommended_activities", "Actividades recomendadas",
                    "actividades_recomendadas", activa=True)]
    if mostrar_autoeval:
        nav.append(etiqueta("self_assessment", "Autoevaluación", "autoevaluacion"))
    nav.append(etiqueta("activities_evaluated", "Actividad evaluada",
                        "actividad_evaluada"))

    ico_zp = _img(mapa, canvas_url, curso, "iconos/zona_practica", 30, 30)
    out = ['<div class="title-section bg-color">',
           '<p style="text-align: center;">%s</p>' % ico_zp,
           '<h2>Zona de práctica</h2>',
           '</div>',
           '<section id="sources_resources" class="preliminary-tabs">',
           '<div class="preliminary-tabs__nav" role="tablist">%s</div>' % "".join(nav)]

    # Actividades recomendadas
    out.append('<div id="recommended_activities" class="preliminary-tabs__content '
               'is-active" role="tabpanel">')
    out.append('<p>Continuemos con el aprendizaje mediante su participación en las '
               'actividades que se describen a continuación:</p>')
    if actividades:
        out.append('<ol type="1">')
        for act in actividades:
            out.append('<li>')
            for b in act.get("contenido") or []:
                out.append(render_bloque(b, mapa, canvas_url, curso, mapa_imagenes))
            out.append('</li>')
        out.append('</ol>')
    else:
        out.append('<p><em>Aún no se han definido actividades recomendadas '
                   'para esta semana.</em></p>')
    out.append('</div>')

    if mostrar_autoeval:
        url = "%s/autoevaluacion_%s.html" % (base_recursos.rstrip("/"), unidad_num)
        out.append('<div id="self_assessment" class="preliminary-tabs__content" '
                   'role="tabpanel">')
        out.append('<p>Estimado estudiante, para evaluar los aprendizajes adquiridos '
                   'sobre la unidad %s, le invito a desarrollar la autoevaluación que '
                   'a continuación se presenta.</p>' % esc(str(unidad_num)))
        out.append('<div class="container-resources" style="max-width: 800px;">'
                   '<div style="position: relative; padding-bottom: 56.25%%; '
                   'padding-top: 0; height: 0;">'
                   '<iframe style="position: absolute; top: 0; left: 0; width: 100%%; '
                   'height: 100%%;" title="Autoevaluación %s" src="%s" width="1200" '
                   'height="675" loading="lazy" allowfullscreen="allowfullscreen">'
                   '</iframe></div></div>'
                   % (esc(str(unidad_num)), esc(url)))
        out.append('</div>')

    out.append('<div id="activities_evaluated" class="preliminary-tabs__content" '
               'role="tabpanel">')
    out.append('<p>La actividad evaluada de esta semana se gestiona desde el libro '
               'de calificaciones del curso.</p>')
    out.append('</div>')

    out.append('</section>')
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Pagina completa
# ---------------------------------------------------------------------------

def html_semana_utpl(data, semana_idx, mapa, canvas_url, curso,
                     base_recursos=None, mapa_imagenes=None, mapa_urls=None):
    base_recursos = base_recursos or base.BASE_RECURSOS_DEFAULT
    semanas = base.obtener_semanas(data)
    u = semanas[semana_idx - 1]
    unidad_num = u.get("numero")
    est = base.estructurar_semana(u.get("bloques", []))

    ult_de_unidad = base.es_ultima_semana_de_unidad(semanas, semana_idx)
    autoeval = base.autoeval_por_unidad(data, unidad_num)
    mostrar_autoeval = ult_de_unidad and (autoeval is not None)

    plan = base.plan_outcomes_por_semana(data)
    info_ra = plan.get(semana_idx, {}) or {}

    titulo_unidad = est.get("titulo_unidad")
    if not titulo_unidad:
        try:
            import render_ed
            titulo_unidad = render_ed.titulo_unidad_de(semanas, unidad_num)
        except Exception:
            titulo_unidad = None

    # Cuántos subtemas hubo antes en semanas previas de la misma unidad, para
    # que la numeración 1.x sea continua a lo largo de la unidad.
    offset = 0
    for i in range(1, semana_idx):
        previa = semanas[i - 1]
        if previa.get("numero") == unidad_num:
            offset += len(base.estructurar_semana(previa.get("bloques", [])).get("subtemas") or [])

    total_semanas = len(semanas)

    out = ['<div class="ed-container">']
    out.append(render_cabecera(titulo_unidad))
    out.append(render_nav_semanas(total_semanas, semana_idx, mapa, canvas_url,
                                  curso, mapa_urls))
    out.append(render_outcome(info_ra.get("ra"), info_ra.get("ctx") or [],
                              mapa, canvas_url, curso,
                              mostrar_ctx=info_ra.get("mostrar_ctx", True)))
    out.append(render_contenido(est, mapa, canvas_url, curso, unidad_num,
                                offset, titulo_unidad, mapa_imagenes))
    out.append('<div id="final_content"><p>Con esto concluye el estudio de los temas '
               'propuestos. Le invitamos a repasar los contenidos revisados y a '
               'resolver las actividades planteadas, ya que la práctica constante '
               'consolida el aprendizaje.</p></div>')
    out.append(render_zona_practica(est.get("actividades_recomendadas") or [],
                                    mapa, canvas_url, curso, mostrar_autoeval,
                                    unidad_num, base_recursos, mapa_imagenes))
    out.append('<footer class="ed-footer"><span>UTPL</span></footer>')
    out.append('</div>')
    return "\n".join(x for x in out if x)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("entrada", help="JSON canónico")
    ap.add_argument("--curso", required=True)
    ap.add_argument("--semana", type=int, required=True)
    ap.add_argument("--mapa-plantilla", default="mapa_plantilla.json")
    ap.add_argument("--mapa-imagenes", default="mapa_imagenes.json")
    ap.add_argument("--canvas-url", default="https://utpl.test.instructure.com")
    ap.add_argument("-o", "--salida", default=None)
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)

    try:
        with open(args.mapa_plantilla, encoding="utf-8") as f:
            mapa = json.load(f)
    except OSError:
        print("⚠ Sin mapa de plantilla: los iconos saldrán vacíos.", file=sys.stderr)
        mapa = {}

    try:
        with open(args.mapa_imagenes, encoding="utf-8") as f:
            mapa_img = json.load(f)
    except OSError:
        mapa_img = None

    html = html_semana_utpl(data, args.semana, mapa, args.canvas_url,
                            args.curso, mapa_imagenes=mapa_img)

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as f:
            f.write(html)
        print("Semana %d -> %s (%d caracteres)" % (args.semana, args.salida, len(html)))
    else:
        print(html)


if __name__ == "__main__":
    main()
