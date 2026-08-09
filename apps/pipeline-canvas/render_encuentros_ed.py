#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_encuentros_ed.py — Crea/llena la página "Encuentros en línea" (theme
ed-*) y la agrega al módulo indicado (por defecto "Preliminares").

El contenido es 100% FICTICIO/QUEMADO (tabla de docentes + horario de
tutorías) porque esa información todavía no está disponible en el JSON
canónico ni tiene una fuente definida. Reemplazar cuando DI defina de dónde
sale (¿otra hoja del Word?, ¿sistema académico?).

Uso (muestra a archivo, sin tocar Canvas):
    python render_encuentros_ed.py --mapa-plantilla mapa_plantilla.json \
        -o muestra_encuentros.html

Uso (sube, publica y la agrega al módulo "Preliminares"):
    python render_encuentros_ed.py --curso 89935 \
        --mapa-plantilla mapa_plantilla.json --modulo Preliminares \
        --subir --publicar
"""

import argparse
import json
import sys

import render_ed as red                 # img_tag, _canvas_y_curso_desde_mapa, url_pagina, cargar_mapa_paginas
import canvas_llenar_inicio as ib        # esc


TITULO_PAGINA = "Encuentros en línea"


# ----------------- helpers de icono (mismo patrón que render_inicio_ed.py) -----------------

def _par(mapa, cu, curso, rol, w=30, h=30):
    """Dos iconos: normal + hover."""
    n = red.img_tag(mapa, cu, curso, "iconos/%s" % rol, w, h)
    hv = red.img_tag(mapa, cu, curso, "iconos/hover/%s" % rol, w, h)
    return "%s %s" % (n, hv)


def _uno(mapa, cu, curso, rol, w=30, h=30):
    """Un solo icono (para el title-section)."""
    return red.img_tag(mapa, cu, curso, "iconos/%s" % rol, w, h)


# ----------------- filas de las tablas (datos quemados) -----------------

def _fila_docente(nombre, correo, paralelo):
    return ('<tr><td style="text-align: center;">%s</td>'
            '<td style="text-align: center;">%s</td>'
            '<td style="text-align: center;">%s</td></tr>'
            % (ib.esc(nombre), ib.esc(correo), ib.esc(paralelo)))


def _fila_horario(paralelo, dia, horario, enlace, telefono):
    return ('<tr><td style="text-align: center;">%s</td>'
            '<td style="text-align: center;">%s</td>'
            '<td style="text-align: center;">%s</td>'
            '<td style="text-align: center;">%s</td>'
            '<td style="text-align: center;">%s</td></tr>'
            % (ib.esc(paralelo), ib.esc(dia), ib.esc(horario), ib.esc(enlace), ib.esc(telefono)))


# ----------------- HTML completo -----------------

def html_encuentros(mapa, cu, curso, mapa_urls=None):
    # Botón para volver a Inicio (si ya existe la página, usa su URL real)
    inicio_href = red.url_pagina(mapa_urls, "Inicio", "#") if mapa_urls is not None else "#"
    homepage = ('<div class="container-homepage-bnt">'
               '<a class="homepage-btn" title="Inicio" href="%s"> %s </a> '
               '<span class="block">&nbsp;</span></div>'
               % (ib.esc(inicio_href), _par(mapa, cu, curso, "home")))

    header = ('<div class="title-section bg-color">'
              '<p style="text-align: center;">%s</p>'
              '<h2>Encuentros en línea</h2></div>'
              % _uno(mapa, cu, curso, "encuentros_en_linea"))

    # ---- TODO: datos ficticios (quemados). DI todavía no define la fuente real. ----
    docentes = [
        ("Nombres completos del docente 1", "usuario@utpl.edu.ec", "###"),
        ("Nombres completos del docente 2", "usuario@utpl.edu.ec", "###"),
        ("Nombres completos del docente n", "usuario@utpl.edu.ec", "###"),
    ]
    horarios = [
        ("123", "Lunes", "20:00 a 21:00", "https://utpl.zoom.us/j/85782702249", "370 1444. ext: 123"),
        ("123", "Lunes", "20:00 a 21:00", "https://utpl.zoom.us/j/85782702249", "370 1444. ext: 123"),
        ("123", "Lunes", "20:00 a 21:00", "https://utpl.zoom.us/j/85782702249", "370 1444. ext: 123"),
    ]

    tabla_docentes = (
        '<table class="table-design"><caption>Detalle</caption>'
        '<thead><tr><th scope="col">Docente</th><th scope="col">Correo</th>'
        '<th scope="col">Paralelo</th></tr></thead><tbody>%s</tbody></table>'
        % "".join(_fila_docente(*d) for d in docentes)
    )
    tabla_horarios = (
        '<table class="table-design"><caption>Detalle</caption>'
        '<thead><tr><th scope="col">Paralelo</th><th scope="col">Día</th>'
        '<th scope="col">Horario</th><th scope="col">Enlace</th>'
        '<th scope="col">Teléfono/extensión</th></tr></thead><tbody>%s</tbody></table>'
        % "".join(_fila_horario(*h) for h in horarios)
    )

    cuerpo = (
        '<div class="indentation-3">'
        '<!-- TODO: datos ficticios (quemados); reemplazar cuando DI defina '
        'la fuente real de docentes/horarios de tutoría. -->'
        '<h3 class="subtitle-section">Información</h3>%s'
        '<h3 class="subtitle-section">Horario de tutorías</h3>%s'
        '</div>' % (tabla_docentes, tabla_horarios)
    )

    return '<div class="ed-container">%s%s%s</div>' % (homepage, header, cuerpo)


# ----------------- main -----------------

def main():
    ap = argparse.ArgumentParser(
        description="Crea/llena la página 'Encuentros en línea' (theme ed-*).")
    ap.add_argument("--curso", type=int, default=None)
    ap.add_argument("--mapa-plantilla", default="mapa_plantilla.json")
    ap.add_argument("--modulo", default="Preliminares",
                    help="Módulo de Canvas donde debe quedar la página (def: Preliminares)")
    ap.add_argument("--subir", action="store_true")
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-o", "--salida", default=None)
    args = ap.parse_args()

    try:
        with open(args.mapa_plantilla, encoding="utf-8") as f:
            mapa = json.load(f)
    except FileNotFoundError:
        sys.exit("No existe %s. Ejecuta antes el paso de subir plantilla." % args.mapa_plantilla)

    canvas_url, curso_mapa = red._canvas_y_curso_desde_mapa(mapa)
    curso = args.curso or curso_mapa

    mapa_urls = red.cargar_mapa_paginas()

    body = html_encuentros(mapa, canvas_url, curso, mapa_urls)

    if not args.subir:
        salida = args.salida or "muestra_encuentros.html"
        with open(salida, "w", encoding="utf-8") as f:
            f.write(body)
        print("Encuentros en línea -> %s (%d caracteres)" % (salida, len(body)))
        return

    if args.dry_run:
        print("PÁGINA: %s (%d caracteres)\nDRY-RUN: no se tocó Canvas." % (TITULO_PAGINA, len(body)))
        return

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

    # ---- Crear o actualizar la página ----
    existentes = {pg.title: pg for pg in curso_obj.get_pages()}
    pg = existentes.get(TITULO_PAGINA)
    cambios = {"body": body}
    if args.publicar:
        cambios["published"] = True
    if pg:
        pg.edit(wiki_page=cambios)
        print("✓ Página '%s' actualizada (%d caracteres)%s"
              % (TITULO_PAGINA, len(body), " [PUBLICADA]" if args.publicar else ""))
    else:
        cambios["title"] = TITULO_PAGINA
        pg = curso_obj.create_page(wiki_page=cambios)
        print("✓ Página '%s' creada (%d caracteres)%s"
              % (TITULO_PAGINA, len(body), " [PUBLICADA]" if args.publicar else ""))

    # ---- Agregarla al módulo indicado (si no está ya) ----
    modulo = next((m for m in curso_obj.get_modules() if m.name == args.modulo), None)
    if not modulo:
        print("⚠ No existe el módulo '%s' en el curso; la página quedó creada "
              "pero sin agregar a ningún módulo. Créalo primero (canvas_crear_modulos.py) "
              "o revisa que el nombre coincida exactamente." % args.modulo)
        return

    ya_esta = any(getattr(it, "page_url", None) == pg.url for it in modulo.get_module_items())
    if not ya_esta:
        modulo.create_module_item(module_item={"type": "Page", "page_url": pg.url})
        print("✓ Página agregada al módulo '%s'." % args.modulo)
    else:
        print("✓ La página ya estaba en el módulo '%s'." % args.modulo)


if __name__ == "__main__":
    main()