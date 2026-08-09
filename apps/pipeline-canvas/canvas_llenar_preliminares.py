#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_llenar_preliminares.py — Paso 3 (parcial) de la integración con Canvas.

Llena DOS páginas del módulo Preliminares con el contenido extraído del JSON:

  - 'Visión General'  ← bloques de la página 'Presentación' del JSON (video)
  - 'Planificación'   ← Competencias (de 'Información general')
                       + Metodología (de 'Metodología de aprendizaje')

No toca 'Inicio' ni 'Tu Mentor' (esos contenidos aún no se han definido).

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="el-token-de-canvas"
    python canvas_llenar_preliminares.py salida.json --curso 89932

Flags:
    --dry-run    muestra el HTML que generaría, sin tocar Canvas
    --publicar   además de actualizar, publica las páginas
"""

import argparse
import json
import os
import re
import sys
import html


# ----------------- Utilidades de HTML -----------------

def esc(s):
    return html.escape(s or "", quote=True)


def md_inline(s):
    """Convierte el markdown inline del JSON a HTML.
    Maneja **negrita**, *cursiva* e [texto](url) como hipervínculos."""
    s = esc(s or "")
    # enlaces [texto](url)
    s = re.sub(
        r"\[([^\]]+)\]\((https?:[^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        s,
    )
    # negrita+cursiva, negrita, cursiva
    s = re.sub(r"\*\*\*([^*]+)\*\*\*", r"<strong><em>\1</em></strong>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


def youtube_id(url):
    """Devuelve el ID del video de YouTube si la URL es de YouTube; si no, None."""
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)"
                  r"([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


def render_video(b):
    url = b.get("url") or ""
    titulo = b.get("titulo") or "Video"
    vid = youtube_id(url)
    if vid:
        emb = "https://www.youtube.com/embed/%s" % vid
        return (
            '<p><iframe src="%s" width="640" height="360" '
            'allowfullscreen allow="accelerometer; autoplay; clipboard-write; '
            'encrypted-media; gyroscope; picture-in-picture" '
            'title="%s" style="max-width:100%%;"></iframe></p>'
            % (esc(emb), esc(titulo))
        )
    # fallback: enlace
    return '<p>🎬 <a href="%s" target="_blank" rel="noopener">%s</a></p>' % (
        esc(url), esc(titulo))


def render_bloque(b):
    t = b.get("tipo")
    if t == "parrafo":
        return "<p>%s</p>" % md_inline(b.get("texto", ""))
    if t == "subtitulo":
        nivel = b.get("nivel", 2)
        tag = "h%d" % min(max(nivel + 1, 2), 5)        # subt nivel 1 -> h2
        return "<%s>%s</%s>" % (tag, md_inline(b.get("texto", "")), tag)
    if t == "lista":
        tag = "ol" if b.get("estilo") == "numerada" else "ul"
        items = "".join("<li>%s</li>" % md_inline(i) for i in b.get("items", []))
        return "<%s>%s</%s>" % (tag, items, tag)
    if t == "video":
        return render_video(b)
    if t == "enlace":
        return '<p>🔗 <a href="%s" target="_blank" rel="noopener">%s</a></p>' % (
            esc(b.get("url", "")), esc(b.get("texto", "") or b.get("url", "")))
    if t == "idea_clave":
        return '<blockquote><strong>Idea clave:</strong> %s</blockquote>' % md_inline(b.get("texto", ""))
    if t == "cita":
        fuente = b.get("fuente")
        cuerpo = md_inline(b.get("texto", ""))
        if fuente:
            cuerpo += '<br><cite>— %s</cite>' % esc(fuente)
        return '<blockquote>%s</blockquote>' % cuerpo
    if t == "recurso":
        return '<p><em>%s</em></p>' % md_inline(b.get("descripcion", ""))
    # cualquier otro tipo: omitirlo silenciosamente
    return ""


# ----------------- Extracción del JSON -----------------

def buscar_pagina(data, *titulos_aceptables):
    """Devuelve los bloques de la primera página cuyo título coincida (case-insensitive)."""
    aceptables = {t.lower().strip() for t in titulos_aceptables}
    for s in data.get("secciones", []):
        if s.get("tipo") == "pagina" and (s.get("titulo") or "").lower().strip() in aceptables:
            return s.get("bloques", [])
    return []


def bloques_competencias(bloques_info_general):
    """Devuelve los bloques que correspondan a competencias dentro de Información general."""
    if not bloques_info_general:
        return []
    inicio = None
    for i, b in enumerate(bloques_info_general):
        if b.get("tipo") == "subtitulo":
            txt = (b.get("texto") or "").lower()
            if "competencia" in txt:
                inicio = i
                break
    return bloques_info_general[inicio:] if inicio is not None else []


# ----------------- Construcción del HTML por página -----------------

def html_vision_general(data):
    """HTML de la página 'Visión General' a partir de la página 'Presentación' del JSON."""
    bloques = buscar_pagina(data, "Presentación", "Presentacion")
    if not bloques:
        return "<p><em>No se encontró la página 'Presentación' en el JSON.</em></p>"
    partes = ["<h2>Visión General</h2>"]
    for b in bloques:
        h = render_bloque(b)
        if h:
            partes.append(h)
    return "\n".join(partes)


def html_planificacion(data):
    """HTML de 'Planificación': Competencias (de Información general) + Metodología."""
    info = buscar_pagina(data, "Información general", "Informacion general")
    comp = bloques_competencias(info)
    met = buscar_pagina(data, "Metodología de aprendizaje", "Metodologia de aprendizaje")

    partes = ["<h2>Planificación</h2>"]
    if comp:
        for b in comp:
            h = render_bloque(b)
            if h:
                partes.append(h)
    else:
        partes.append("<p><em>No se encontraron competencias.</em></p>")

    if met:
        partes.append("<h3>Metodología de aprendizaje</h3>")
        for b in met:
            # No repetir el título 'Metodología' si viene como primer subtítulo
            if b.get("tipo") == "subtitulo" and "metodolog" in (b.get("texto") or "").lower():
                continue
            h = render_bloque(b)
            if h:
                partes.append(h)
    else:
        partes.append("<p><em>No se encontró 'Metodología de aprendizaje'.</em></p>")

    return "\n".join(partes)


# ----------------- Programa principal -----------------

def main():
    ap = argparse.ArgumentParser(description="Llena Visión General y Planificación en Canvas.")
    ap.add_argument("entrada", help="JSON (salida.json)")
    ap.add_argument("--curso", type=int, required=True, help="ID del curso en Canvas")
    ap.add_argument("--dry-run", action="store_true", help="muestra el HTML, sin tocar Canvas")
    ap.add_argument("--publicar", action="store_true", help="publica las páginas tras llenarlas")
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)

    paginas = {
        "Visión General": html_vision_general(data),
        "Planificación":  html_planificacion(data),
    }

    if args.dry_run:
        for titulo, cuerpo in paginas.items():
            print("\n" + "=" * 70)
            print("PÁGINA: %s" % titulo)
            print("=" * 70)
            print(cuerpo)
        print("\nDRY-RUN: no se tocó Canvas. Quita --dry-run para subir.")
        return

    # --- Conexión a Canvas ---
    try:
        from canvasapi import Canvas
    except ImportError:
        sys.exit("Falta la librería. Instala con:  pip install canvasapi")
    url = os.environ.get("CANVAS_URL")
    token = os.environ.get("CANVAS_TOKEN")
    if not url or not token:
        sys.exit("Define CANVAS_URL y CANVAS_TOKEN.")
    canvas = Canvas(url, token)
    try:
        curso = canvas.get_course(args.curso)
        print("Conectado al curso: %s\n" % curso.name)
    except Exception as e:
        sys.exit("No pude acceder al curso %d: %s" % (args.curso, e))

    # Indexar páginas existentes por título
    existentes = {pg.title: pg for pg in curso.get_pages()}

    actualizadas, faltantes = 0, []
    for titulo, cuerpo in paginas.items():
        pg = existentes.get(titulo)
        if not pg:
            faltantes.append(titulo)
            print("  ⚠ No existe la página '%s' en el curso. Créala primero con "
                  "canvas_crear_paginas.py." % titulo)
            continue
        cambios = {"body": cuerpo}
        if args.publicar:
            cambios["published"] = True
        pg.edit(wiki_page=cambios)
        print("  ✓ '%s' actualizada (%d caracteres de HTML)%s"
              % (titulo, len(cuerpo), " [PUBLICADA]" if args.publicar else ""))
        actualizadas += 1

    print("\n=========== RESUMEN ===========")
    print("  Páginas actualizadas:  %d" % actualizadas)
    print("  Páginas no encontradas: %d  %s"
          % (len(faltantes), ("(%s)" % ", ".join(faltantes)) if faltantes else ""))
    print("================================")


if __name__ == "__main__":
    main()
