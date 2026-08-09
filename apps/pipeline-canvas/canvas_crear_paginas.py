#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_crear_paginas.py — Paso 2 de la integración con Canvas LMS.

Crea las páginas VACÍAS del curso (sin contenido aún) y las asocia a su módulo,
respetando el orden:

  Preliminares       -> Inicio
  Semana N           -> Semana N             (una página por semana)

("Fuentes y recursos" y "Encuentros en línea" ya NO se crean aquí: cada una
se crea/asocia sola al módulo "Preliminares" al correr render_fuentes_ed.py
y render_encuentros_ed.py respectivamente.)

Las páginas se crean SIN PUBLICAR para revisión. Quita el flag o usa --publicar
si quieres publicarlas. Si una página con el mismo título ya existe en el curso,
se respeta y solo se asegura que esté en el módulo correcto (no se sobrescribe).

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="el-token-de-canvas"
    python canvas_crear_paginas.py salida.json --curso 89932

Flags:
    --dry-run      lista las páginas que crearía, sin tocar Canvas
    --publicar     publica las páginas (def: quedan sin publicar)
    --recrear      si la página existe, la borra y la recrea vacía (CUIDADO: pierde contenido)
"""

import argparse
import json
import os
import sys
import unicodedata
import re


def slugify(texto):
    """Convierte 'Visión General' -> 'vision-general' (slug estable para page_url)."""
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s


def listar_semanas(data):
    """Devuelve los nombres de las semanas presentes en el JSON, en orden."""
    semanas = []
    for sec in data.get("secciones", []):
        if sec.get("tipo") == "contenido":
            for u in sec.get("unidades", []):
                nombre = (u.get("nombre_pagina") or "").strip()
                if nombre and nombre not in semanas:
                    semanas.append(nombre)
    return semanas


def plan_paginas(data):
    """Devuelve [(modulo, [paginas en orden]), ...]
    Nota: Preliminares solo tiene 'Inicio'. Visión General, Planificación
    y Tu Mentor son TABS dentro de la página de Inicio, no páginas separadas.

    "Referencias Bibliográficas" y "Glosario" ya NO se crean aquí (plantilla
    vieja). Con la plantilla nueva, "Fuentes y recursos" (render_fuentes_ed.py)
    y "Encuentros en línea" (render_encuentros_ed.py) se crean y se asocian
    solas al módulo "Preliminares" cuando corren esos pasos."""
    plan = []
    plan.append(("Preliminares", ["Inicio"]))
    for sem in listar_semanas(data):
        plan.append((sem, [sem]))               # 'Semana 1' -> página 'Semana 1'
    return plan


def main():
    ap = argparse.ArgumentParser(description="Crea las páginas vacías del curso en Canvas.")
    ap.add_argument("entrada", help="JSON con los contenidos (salida.json)")
    ap.add_argument("--curso", type=int, required=True, help="ID del curso en Canvas")
    ap.add_argument("--dry-run", action="store_true", help="solo listar, sin tocar Canvas")
    ap.add_argument("--publicar", action="store_true", help="publicar las páginas creadas")
    ap.add_argument("--recrear", action="store_true",
                    help="si una página existe, borrarla y recrearla vacía")
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)
    plan = plan_paginas(data)

    print("=== Plan de páginas para el curso %d ===" % args.curso)
    total = 0
    for modulo, paginas in plan:
        print("  Módulo '%s':" % modulo)
        for i, pg in enumerate(paginas, 1):
            print("    %d) %s" % (i, pg))
            total += 1
    print("\nTotal de páginas a crear: %d\n" % total)

    if args.dry_run:
        print("DRY-RUN: no se creó nada. Quita --dry-run para crear de verdad.")
        return

    # --- Conexión a Canvas ---
    try:
        from canvasapi import Canvas
    except ImportError:
        sys.exit("Falta la librería. Instala con:  pip install canvasapi")
    url = os.environ.get("CANVAS_URL")
    token = os.environ.get("CANVAS_TOKEN")
    if not url or not token:
        sys.exit("Define las variables CANVAS_URL y CANVAS_TOKEN.")
    canvas = Canvas(url, token)
    try:
        curso = canvas.get_course(args.curso)
        print("Conectado al curso: %s\n" % curso.name)
    except Exception as e:
        sys.exit("No pude acceder al curso %d: %s" % (args.curso, e))

    # Mapear módulos por nombre
    modulos = {m.name: m for m in curso.get_modules()}

    # Mapear páginas existentes por título (para evitar duplicados)
    existentes = {}
    for pg in curso.get_pages():
        existentes[pg.title] = pg

    creadas, asociadas, saltadas, recreadas = 0, 0, 0, 0

    for modulo_nombre, paginas in plan:
        mod = modulos.get(modulo_nombre)
        if not mod:
            print("  ⚠ Módulo '%s' no existe en Canvas; sus páginas no se asociarán."
                  % modulo_nombre)
        print("\n→ Módulo: %s" % modulo_nombre)

        for pos, titulo in enumerate(paginas, 1):
            slug_esperado = slugify(titulo)
            pg = existentes.get(titulo)

            # CRÍTICO: aunque exista por título, verificar que el slug sea correcto.
            # Canvas reserva slugs aunque borres páginas, generando "inicio-2",
            # "inicio-3" etc. Si el slug NO coincide con el esperado, BORRAMOS la
            # página actual y dejamos que el sistema use el slug limpio.
            if pg and getattr(pg, "url", None) != slug_esperado:
                try:
                    print("    · '%s' tiene slug '%s' (esperado '%s'); recreando..."
                          % (titulo, pg.url, slug_esperado))
                    pg.delete()
                    # Buscar también páginas "fantasma" (otros slugs con mismo título)
                    # para borrarlas y limpiar el espacio de nombres.
                    for pg_fantasma in list(curso.get_pages()):
                        if (pg_fantasma.title == titulo
                            and pg_fantasma.url != slug_esperado):
                            try:
                                pg_fantasma.delete()
                            except Exception:
                                pass
                    pg = None
                    existentes.pop(titulo, None)
                except Exception as e:
                    print("      ⚠ No pude borrar la página fantasma: %s" % str(e)[:80])

            if pg:
                if args.recrear:
                    print("    · Recreando '%s' (se pierde el contenido anterior)..."
                          % titulo)
                    pg.delete()
                    pg = None
                    recreadas += 1
                else:
                    print("    · '%s' ya existe -> se mantiene" % titulo)
                    saltadas += 1
            if not pg:
                pg = curso.create_page(wiki_page={
                    "title": titulo,
                    "body": "",
                    "published": args.publicar,
                    "editing_roles": "teachers",
                })
                existentes[titulo] = pg
                if pg.url == slug_esperado:
                    print("    ✓ Página creada: '%s' (slug: %s)" % (titulo, pg.url))
                else:
                    print("    ⚠ Página creada: '%s' pero con slug '%s' (esperado '%s')"
                          % (titulo, pg.url, slug_esperado))
                creadas += 1

            # Asociar al módulo (si el módulo existe y la página aún no está en él)
            if mod:
                ya_en_modulo = any(
                    getattr(it, "page_url", None) == getattr(pg, "url", None)
                    for it in mod.get_module_items()
                )
                if not ya_en_modulo:
                    mod.create_module_item(module_item={
                        "type": "Page",
                        "page_url": pg.url,
                        "position": pos,
                        "indent": 0,
                    })
                    print("       → asociada al módulo (posición %d)" % pos)
                    asociadas += 1

    print("\n=========== RESUMEN ===========")
    print("  Páginas creadas:        %d" % creadas)
    print("  Páginas ya existentes:  %d" % saltadas)
    print("  Páginas recreadas:      %d" % recreadas)
    print("  Asociaciones a módulo:  %d" % asociadas)
    print("  Estado:                 %s" % ("publicadas" if args.publicar else "SIN PUBLICAR"))
    print("================================")
    print("\nRevisa el curso en Canvas. Siguiente paso: subir contenido a cada página.")


if __name__ == "__main__":
    main()
