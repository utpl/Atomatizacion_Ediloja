#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_fuentes_ed.py — Página única "Fuentes y recursos" (theme ed-*), que
reemplaza a las dos páginas antiguas "Referencias Bibliográficas" y "Glosario".

Tres tabs, llenados SOLO con lo que trae el JSON:
  - Bibliografía : sección 'referencias' -> entradas APA.
  - Glosario     : sección 'glosario'    -> términos + definición.
  - Créditos     : placeholder (el JSON no trae créditos).

En modo Canvas crea/reusa la página "Fuentes y recursos", la llena y la publica;
opcionalmente la agrega a un módulo (--modulo) y despublica/borra las páginas
viejas (--limpiar). El botón de Inicio ya apunta a esta página vía mapa_paginas.

Uso:
  python render_fuentes_ed.py salida_curada.json --mapa-plantilla mapa_plantilla.json -o fuentes.html
  python render_fuentes_ed.py salida_curada.json --curso 89935 \
      --mapa-plantilla mapa_plantilla.json --subir --publicar \
      --modulo "Referencias" --limpiar
"""

import argparse
import json
import sys

import render_ed as red
import canvas_llenar_inicio as ib
import canvas_llenar_semanas as base

TITULO_PAGINA = "Fuentes y recursos"
PAGINAS_VIEJAS = ["Referencias Bibliográficas", "Referencias bibliográficas", "Glosario"]


def _seccion(data, tipo):
    for s in data.get("secciones", []):
        if s.get("tipo") == tipo:
            return s
    return None


def _tab(mapa, cu, curso, control, etiqueta, activo):
    n = red.img_tag(mapa, cu, curso, "iconos/fuentes_recursos", 30, 30)
    hv = red.img_tag(mapa, cu, curso, "iconos/hover/fuentes_recursos", 30, 30)
    sel = "true" if activo else "false"
    cls = "preliminary-tabs__label is-active" if activo else "preliminary-tabs__label"
    return ('<a class="%s" role="tab" href="#%s" aria-selected="%s" '
            'aria-controls="%s" data-tab="%s"> %s %s <span>%s</span> </a>'
            % (cls, control, sel, control, control, n, hv, etiqueta))


def _bibliografia(data):
    sec = _seccion(data, "referencias")
    entradas = (sec or {}).get("entradas", []) or []
    if not entradas:
        return "<p><em>No se registran referencias bibliográficas.</em></p>"
    # Referencias APA: un párrafo por entrada (sangría francesa la da el theme)
    return "\n".join("<p>%s</p>" % ib.md_inline(e) for e in entradas)


def _glosario(data):
    sec = _seccion(data, "glosario")
    terminos = (sec or {}).get("terminos", []) or []
    if not terminos:
        return "<p><em>No se registran términos de glosario.</em></p>"
    filas = []
    for t in terminos:
        term = t.get("termino", "")
        defi = t.get("definicion", "")
        filas.append("<dt><strong>%s</strong></dt><dd>%s</dd>"
                     % (ib.md_inline(term), ib.md_inline(defi)))
    return "<dl>%s</dl>" % "".join(filas)


def _creditos(data):
    sec = _seccion(data, "creditos")
    if sec and sec.get("contenido"):
        return "\n".join(h for h in (red.render_bloque_ed(b, {}, "", "")
                                     for b in sec["contenido"]) if h)
    return ("<p><em>Créditos pendientes de definir por el equipo de DI.</em></p>")


def html_fuentes_ed(data, mapa, canvas_url, curso, mapa_urls=None):
    cu = canvas_url
    home = red.img_tag(mapa, cu, curso, "iconos/home", 30, 30)
    home_h = red.img_tag(mapa, cu, curso, "iconos/hover/home", 30, 30)
    href_inicio = red.url_pagina(mapa_urls, "Inicio", "#")
    ic_sec = red.img_tag(mapa, cu, curso, "iconos/fuentes_recursos", 30, 30)

    out = ['<div class="ed-container">']
    # Botón inicio
    out.append('<div class="container-homepage-bnt">'
               '<a class="homepage-btn" title="Inicio" href="%s"> %s %s </a> '
               '<span class="block">&nbsp;</span></div>'
               % (ib.esc(href_inicio), home, home_h))
    # Título
    out.append('<div class="title-section bg-color">'
               '<p style="text-align: center;">%s</p><h2>Fuentes y recursos</h2></div>' % ic_sec)
    # Tabs
    out.append('<div class="indentation-3">'
               '<section id="sources_resources" class="preliminary-tabs">')
    out.append('<div class="preliminary-tabs__nav" role="tablist">%s%s%s</div>'
               % (_tab(mapa, cu, curso, "bibliography", "Bibliografía", True),
                  _tab(mapa, cu, curso, "glossary", "Glosario", False),
                  _tab(mapa, cu, curso, "credits", "Créditos", False)))
    out.append('<div id="bibliography" class="preliminary-tabs__content is-active" '
               'role="tabpanel">%s</div>' % _bibliografia(data))
    out.append('<div id="glossary" class="preliminary-tabs__content" role="tabpanel">%s</div>'
               % _glosario(data))
    out.append('<div id="credits" class="preliminary-tabs__content" role="tabpanel">%s</div>'
               % _creditos(data))
    out.append('</section></div></div>')
    return "\n".join(out)


# ----------------- main -----------------

def main():
    ap = argparse.ArgumentParser(description="Página única 'Fuentes y recursos' (ed-*).")
    ap.add_argument("entrada")
    ap.add_argument("--curso", type=int, default=None)
    ap.add_argument("--mapa-plantilla", default="mapa_plantilla.json")
    ap.add_argument("--modulo", default=None,
                    help="nombre del módulo donde agregar la página (ej: Referencias)")
    ap.add_argument("--limpiar", action="store_true",
                    help="despublica las páginas viejas (Referencias Bibliográficas, Glosario)")
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
    mapa_urls = red.cargar_mapa_paginas()

    if not args.subir:
        body = html_fuentes_ed(data, mapa, canvas_url, curso, mapa_urls=mapa_urls)
        salida = args.salida or "muestra_fuentes.html"
        with open(salida, "w", encoding="utf-8") as f:
            f.write(body)
        print("Fuentes y recursos -> %s (%d caracteres)" % (salida, len(body)))
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

    # URLs vivas para el botón de Inicio
    existentes = {pg.title: pg for pg in curso_obj.get_pages()}
    for titulo, pg in existentes.items():
        if titulo not in mapa_urls and getattr(pg, "html_url", ""):
            mapa_urls[titulo] = pg.html_url

    body = html_fuentes_ed(data, mapa, canvas_url, curso, mapa_urls=mapa_urls)

    if args.dry_run:
        print("PÁGINA: %s (%d caracteres)\nDRY-RUN: no se tocó Canvas." % (TITULO_PAGINA, len(body)))
        return

    # Crear o reusar la página
    pg = existentes.get(TITULO_PAGINA)
    cambios = {"title": TITULO_PAGINA, "body": body}
    if args.publicar:
        cambios["published"] = True
    if pg:
        pg.edit(wiki_page=cambios)
        print("✓ Página '%s' actualizada (%d caracteres)" % (TITULO_PAGINA, len(body)))
    else:
        pg = curso_obj.create_page(wiki_page=cambios)
        print("✓ Página '%s' creada (%d caracteres)" % (TITULO_PAGINA, len(body)))

    # Agregar al módulo (si se pidió y no está ya)
    if args.modulo:
        try:
            modulo = next((m for m in curso_obj.get_modules() if m.name == args.modulo), None)
            if not modulo:
                modulo = curso_obj.create_module(module={"name": args.modulo, "published": True})
                print("  + módulo '%s' creado" % args.modulo)
            items = list(modulo.get_module_items())
            ya = any(getattr(it, "title", "") == TITULO_PAGINA for it in items)
            if not ya:
                modulo.create_module_item(module_item={
                    "type": "Page", "page_url": pg.url, "published": True})
                print("  + agregada al módulo '%s'" % args.modulo)
            else:
                print("  = ya estaba en el módulo '%s'" % args.modulo)
        except Exception as e:
            print("  ⚠ No se pudo agregar al módulo: %s" % e)

    # Limpiar las páginas viejas (despublicar, no borrar por seguridad)
    if args.limpiar:
        for viejo in PAGINAS_VIEJAS:
            p = existentes.get(viejo)
            if p:
                try:
                    p.edit(wiki_page={"published": False})
                    print("  - '%s' despublicada" % viejo)
                except Exception as e:
                    print("  ⚠ No se pudo despublicar '%s': %s" % (viejo, e))


if __name__ == "__main__":
    main()
