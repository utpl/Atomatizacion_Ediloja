#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_crear_pagina_evaluaciones.py — Crea la página "Evaluaciones" en Canvas
SIN asignarla a ningún módulo.

Esta página es de uso interno (preview/auditoría) del equipo de Diseño Web.
Contiene TODAS las autoevaluaciones de la guía con sus solucionarios.
NO debe aparecer en la navegación de módulos del estudiante; se accede
únicamente por URL directa.

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="..."
    python canvas_crear_pagina_evaluaciones.py --curso 89932

Flags:
    --dry-run      no llama a Canvas, solo simula
    --publicar     publica la página (por defecto queda como borrador)
    --titulo X     título personalizado (default: "Evaluaciones")
"""

import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser(
        description="Crea la página 'Evaluaciones' en Canvas (sin módulo)."
    )
    ap.add_argument("--curso", type=int, required=True, help="ID del curso")
    ap.add_argument("--titulo", default="Evaluaciones",
                    help="Título de la página (default: Evaluaciones)")
    ap.add_argument("--dry-run", action="store_true",
                    help="No llama a Canvas, solo simula")
    ap.add_argument("--publicar", action="store_true",
                    help="Publica la página tras crearla (default: borrador)")
    args = ap.parse_args()

    if args.dry_run:
        print(f"DRY-RUN: se crearía la página '{args.titulo}' en el curso {args.curso}")
        print(f"         publicada: {args.publicar}")
        print(f"         body: vacío (la llena canvas_llenar_evaluaciones.py)")
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
        print(f"Conectado al curso: {curso.name}")
    except Exception as e:
        sys.exit(f"Error: {e}")

    # Verificar si ya existe la página
    existentes = {pg.title: pg for pg in curso.get_pages()}
    pg_existente = existentes.get(args.titulo)

    if pg_existente:
        # También buscar por slug por si quedó una huérfana con nombre similar
        slug_deseado = args.titulo.lower().replace(" ", "-")
        if pg_existente.url != slug_deseado:
            print(f"⚠ Página '{args.titulo}' existe con slug distinto: {pg_existente.url}")
            print(f"  Borrando para crear limpia con slug correcto...")
            pg_existente.delete()
            pg_existente = None
        else:
            print(f"✓ Página '{args.titulo}' ya existe (slug: {pg_existente.url}). No se crea de nuevo.")
            print(f"  URL: {url}/courses/{args.curso}/pages/{pg_existente.url}")
            return

    # Crear la página
    body_inicial = (
        f'<div style="padding:20px;background:#f3f5f9;border-radius:8px;'
        f'text-align:center;color:#6b7280;">'
        f'<p><em>Esta página será llenada por <code>canvas_llenar_evaluaciones.py</code></em></p>'
        f'</div>'
    )

    nueva = curso.create_page(wiki_page={
        "title": args.titulo,
        "body": body_inicial,
        "published": args.publicar,
        # IMPORTANTE: NO asignamos a ningún módulo. Queda como página huérfana
        # accesible solo por URL directa.
    })

    estado = "PUBLICADA" if args.publicar else "BORRADOR"
    print(f"✓ Página '{args.titulo}' creada como {estado}")
    print(f"  Slug:    {nueva.url}")
    print(f"  URL:     {url}/courses/{args.curso}/pages/{nueva.url}")
    print()
    print(f"Siguiente paso:")
    print(f"  python canvas_llenar_evaluaciones.py salida_curada_canvas.json --curso {args.curso}")


if __name__ == "__main__":
    main()