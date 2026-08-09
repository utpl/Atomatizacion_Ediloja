#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_crear_modulos.py — Paso 1 de la integración con Canvas LMS.

Crea los módulos vacíos del curso en el orden correcto:
    1. Preliminares
    2. Semana 1
    3. Semana 2
    ... (las que haya en el JSON)

("Referencias" ya no se crea: con la plantilla nueva, "Fuentes y recursos"
y "Encuentros en línea" quedan dentro de "Preliminares".)

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="el-token-de-canvas"
    python canvas_crear_modulos.py salida_con_diagramas.json --curso 89932

Flags:
    --dry-run      lista los módulos que crearía, sin tocar Canvas
    --publicar     publica los módulos (def: quedan sin publicar para revisión)
    --recrear      si un módulo con el mismo nombre ya existe, lo borra y lo recrea
                   (CUIDADO: borra también su contenido. Por defecto, lo deja como está.)

NO sube páginas, NO sube imágenes. Solo crea los contenedores (módulos)
para que el siguiente paso del pipeline tenga dónde colocar el contenido.
"""

import argparse
import json
import os
import sys


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


def plan_modulos(data):
    """Construye el plan: [(nombre, posicion), ...] en orden.

    NOTA: ya no se crea el módulo "Referencias" (plantilla vieja). Con la
    plantilla nueva (ed-*), "Fuentes y recursos" y "Encuentros en línea"
    viven dentro del módulo "Preliminares" (los crea/asocia cada uno su
    propio script: render_fuentes_ed.py y render_encuentros_ed.py).
    """
    plan = [("Preliminares", 1)]
    pos = 2
    for nombre in listar_semanas(data):
        plan.append((nombre, pos))
        pos += 1
    return plan


def main():
    ap = argparse.ArgumentParser(description="Crea los módulos del curso en Canvas.")
    ap.add_argument("entrada", help="JSON con los contenidos (salida_con_diagramas.json)")
    ap.add_argument("--curso", type=int, required=True, help="ID del curso en Canvas")
    ap.add_argument("--dry-run", action="store_true", help="solo listar, sin tocar Canvas")
    ap.add_argument("--publicar", action="store_true", help="publicar los módulos creados")
    ap.add_argument("--recrear", action="store_true",
                    help="si un módulo con el mismo nombre existe, borrarlo y recrearlo")
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)
    plan = plan_modulos(data)

    print("=== Plan de módulos para el curso %d ===" % args.curso)
    for nombre, pos in plan:
        print("  %2d. %s" % (pos, nombre))
    print()

    if args.dry_run:
        print("DRY-RUN: no se creó nada en Canvas. Quita --dry-run para crear de verdad.")
        return

    # --- Conexión a Canvas ---
    try:
        from canvasapi import Canvas
    except ImportError:
        sys.exit("Falta la librería. Instala con:  pip install canvasapi")
    url = os.environ.get("CANVAS_URL")
    token = os.environ.get("CANVAS_TOKEN")
    if not url or not token:
        sys.exit("Define las variables:\n"
                 "  export CANVAS_URL='https://utpl.test.instructure.com'\n"
                 "  export CANVAS_TOKEN='tu-token-de-canvas'")
    canvas = Canvas(url, token)
    try:
        curso = canvas.get_course(args.curso)
        print("Conectado al curso: %s\n" % curso.name)
    except Exception as e:
        sys.exit("No pude acceder al curso %d. ¿Token y ID correctos?\n  %s" % (args.curso, e))

    # --- Módulos existentes ---
    existentes = {m.name: m for m in curso.get_modules()}
    if existentes:
        print("Módulos ya existentes en el curso: %s\n" % ", ".join(existentes.keys()))

    creados, saltados, recreados = 0, 0, 0
    for nombre, pos in plan:
        if nombre in existentes:
            if args.recrear:
                print("  · Recreando '%s'..." % nombre)
                existentes[nombre].delete()
                recreados += 1
            else:
                print("  · '%s' ya existe -> se mantiene (usa --recrear para reemplazar)" % nombre)
                saltados += 1
                continue
        m = curso.create_module(module={
            "name": nombre,
            "position": pos,
            "published": args.publicar,
        })
        print("  ✓ Creado '%s' (id=%s, posición %d)" % (m.name, m.id, pos))
        creados += 1

    print("\n=========== RESUMEN ===========")
    print("  Creados:   %d" % creados)
    print("  Recreados: %d" % recreados)
    print("  Saltados:  %d" % saltados)
    print("  Estado:    %s" % ("publicados" if args.publicar else "SIN PUBLICAR (revisa en Canvas)"))
    print("================================")
    print("\nRevisa los módulos en Canvas. Siguiente paso: subir páginas a cada módulo.")


if __name__ == "__main__":
    main()
