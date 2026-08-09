#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_subir_imagenes.py — Sube las imágenes locales a Files de Canvas y
actualiza el JSON con las URLs reales, listas para usar en el HTML de páginas.

Flujo:
  1. Recorre la carpeta 'imagenes/' (o la que se pase con --carpeta).
  2. Por cada imagen (PNG/JPG/SVG/GIF/WEBP), la sube a Files del curso, dentro
     de la carpeta '--carpeta-canvas' (por defecto 'pipeline_ediloja').
  3. Recibe el file_id y construye la URL embebible para HTML.
  4. Actualiza el JSON: reemplaza cada `imagen.src` de ruta local por la URL
     real de Canvas. Guarda como '<entrada>_canvas.json' (o --salida).
  5. Genera 'mapa_imagenes.json' con {archivo: {file_id, preview_url, download_url}}.

Si una imagen con el mismo nombre ya existe en la carpeta de Canvas:
  - por defecto la respeta (no re-sube, reusa su file_id).
  - con --recrear, la borra y la vuelve a subir.

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="tu-token"
    python canvas_subir_imagenes.py salida.json --curso 89932 --carpeta imagenes/

Flags útiles:
    --limite N            sube solo N imágenes (prueba rápida)
    --solo FILES          sube solo archivos específicos (separados por coma)
    --dry-run             lista qué subiría, sin tocar Canvas
    --recrear             si una imagen ya existe en Canvas, la borra y re-sube
    --carpeta-canvas NOM  carpeta dentro de Files (def: pipeline_ediloja)
"""

import argparse
import json
import os
import sys


EXTENSIONES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def listar_imagenes_locales(carpeta):
    """Lista todas las imágenes en la carpeta (no entra a subcarpetas)."""
    if not os.path.isdir(carpeta):
        return []
    out = []
    for nombre in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, nombre)
        if not os.path.isfile(ruta):
            continue
        ext = os.path.splitext(nombre)[1].lower()
        if ext in EXTENSIONES:
            out.append((nombre, ruta))
    return out


def iter_figuras(obj):
    """Recorre el JSON y devuelve cada bloque figura con imagen."""
    if isinstance(obj, dict):
        if obj.get("tipo") == "figura" and obj.get("imagen", {}).get("src"):
            yield obj
        for v in obj.values():
            yield from iter_figuras(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_figuras(v)


def main():
    ap = argparse.ArgumentParser(description="Sube imágenes a Canvas y actualiza el JSON.")
    ap.add_argument("entrada", help="JSON canónico (p.ej. salida.json)")
    ap.add_argument("--curso", type=int, required=True, help="ID del curso en Canvas")
    ap.add_argument("--carpeta", default="imagenes",
                    help="carpeta local con las imágenes (def: imagenes)")
    ap.add_argument("--carpeta-canvas", default="pipeline_ediloja",
                    help="carpeta destino en Files (def: pipeline_ediloja)")
    ap.add_argument("-o", "--salida", default=None,
                    help="JSON de salida con URLs (def: <entrada>_canvas.json)")
    ap.add_argument("--limite", type=int, default=None,
                    help="sube solo las primeras N imágenes (prueba)")
    ap.add_argument("--solo", default=None,
                    help="solo estos archivos (separados por coma)")
    ap.add_argument("--dry-run", action="store_true",
                    help="lista qué subiría, sin tocar Canvas")
    ap.add_argument("--recrear", action="store_true",
                    help="si una imagen ya existe en Canvas, borrarla y re-subir")
    args = ap.parse_args()

    # Cargar JSON
    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)

    # Listar imágenes locales
    imagenes = listar_imagenes_locales(args.carpeta)
    if args.solo:
        permitidos = {x.strip() for x in args.solo.split(",")}
        imagenes = [(n, r) for n, r in imagenes if n in permitidos]
    if args.limite:
        imagenes = imagenes[:args.limite]

    print("=== Plan de subida ===")
    print("  Curso destino:          %d" % args.curso)
    print("  Carpeta local:          %s" % args.carpeta)
    print("  Carpeta en Canvas:      %s" % args.carpeta_canvas)
    print("  Imágenes a subir:       %d" % len(imagenes))
    print()
    for nombre, ruta in imagenes[:15]:
        tam_kb = os.path.getsize(ruta) / 1024
        print("    • %s (%.1f KB)" % (nombre, tam_kb))
    if len(imagenes) > 15:
        print("    ... y %d más" % (len(imagenes) - 15))

    if args.dry_run:
        print("\nDRY-RUN: no se subió nada. Quita --dry-run para subir.")
        return

    if not imagenes:
        print("\nNo hay imágenes para subir.")
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
        print("\nConectado al curso: %s" % curso.name)
    except Exception as e:
        sys.exit("No pude acceder al curso %d: %s" % (args.curso, e))

    # Asegurar que la carpeta destino existe en Canvas
    try:
        carpetas_existentes = {f.name: f for f in curso.get_folders()}
        if args.carpeta_canvas in carpetas_existentes:
            folder = carpetas_existentes[args.carpeta_canvas]
            print("Carpeta '%s' ya existe en Files." % args.carpeta_canvas)
        else:
            folder = curso.create_folder(args.carpeta_canvas,
                                         parent_folder_path="")
            print("Carpeta '%s' creada en Files." % args.carpeta_canvas)
    except Exception as e:
        sys.exit("Error preparando la carpeta en Canvas: %s" % e)

    # Indexar archivos ya existentes en esa carpeta (para no duplicar)
    existentes = {}
    try:
        for f in folder.get_files():
            existentes[f.display_name] = f
    except Exception:
        pass

    base_url = url.rstrip("/")
    mapa = {}                                # nombre_local -> {file_id, urls}
    subidas, reusadas, recreadas, fallidas = 0, 0, 0, 0

    print("\nSubiendo...\n")
    for nombre, ruta in imagenes:
        try:
            f_existente = existentes.get(nombre)
            if f_existente:
                if args.recrear:
                    print("  · '%s' existe — borrando para re-subir..." % nombre)
                    f_existente.delete()
                    f_existente = None
                    recreadas += 1
                else:
                    print("  · '%s' ya existe en Canvas (file_id=%s) — se reusa"
                          % (nombre, f_existente.id))
                    file_obj = f_existente
                    reusadas += 1

            if not f_existente:
                # canvasapi: Folder.upload(file) o Course.upload(file, parent_folder_path=...)
                ok, resp = folder.upload(ruta)
                if not ok:
                    raise RuntimeError("upload devolvió False: %s" % resp)
                file_id = resp.get("id") if isinstance(resp, dict) else resp.id
                # Obtener objeto File completo para asegurar todos los campos
                file_obj = canvas.get_file(file_id)
                print("  ✓ '%s' subida (file_id=%s)" % (nombre, file_id))
                subidas += 1

            # IMPORTANTE: publicar el archivo y quitar restricciones para que
            # se vea embebido en las páginas (sin esto, los <img> salen rotos
            # aunque la URL sea correcta).
            try:
                file_obj.update(hidden=False, locked=False)
            except Exception as e:
                print("  ⚠ No pude publicar '%s': %s" % (nombre, str(e)[:80]),
                      file=sys.stderr)

            preview = "%s/courses/%d/files/%d/preview" % (base_url, args.curso, file_obj.id)
            download = "%s/courses/%d/files/%d/download" % (base_url, args.curso, file_obj.id)
            mapa[nombre] = {
                "file_id": file_obj.id,
                "preview_url": preview,
                "download_url": download,
            }
        except Exception as e:
            fallidas += 1
            print("  ⚠ Falló '%s': %s" % (nombre, str(e)[:140]), file=sys.stderr)

    # Actualizar el JSON: reemplazar cada imagen.src de ruta local -> preview URL
    actualizadas = 0
    for fig in iter_figuras(data):
        src = fig["imagen"]["src"]
        nombre = os.path.basename(src)
        if nombre in mapa:
            fig["imagen"]["src"] = mapa[nombre]["preview_url"]
            fig["imagen"]["canvas_file_id"] = mapa[nombre]["file_id"]
            actualizadas += 1

    salida = args.salida or (os.path.splitext(args.entrada)[0] + "_canvas.json")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Mapa de imágenes para auditoría
    mapa_path = os.path.join(os.path.dirname(salida) or ".", "mapa_imagenes.json")
    with open(mapa_path, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2)

    print("\n=========== RESUMEN ===========")
    print("  Subidas nuevas:        %d" % subidas)
    print("  Reusadas (ya estaban): %d" % reusadas)
    print("  Re-subidas (--recrear): %d" % recreadas)
    print("  Fallidas:              %d" % fallidas)
    print("  Referencias en JSON actualizadas: %d" % actualizadas)
    print("  JSON con URLs:         %s" % salida)
    print("  Mapa de imágenes:      %s" % mapa_path)
    print("================================")
    if subidas + reusadas:
        print("\nUna URL típica para revisar manualmente en el navegador:")
        primer = next(iter(mapa.values()))
        print("  " + primer["preview_url"])


if __name__ == "__main__":
    main()