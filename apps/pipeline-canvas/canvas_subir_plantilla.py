#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_subir_plantilla.py — Sube los assets FIJOS de la plantilla institucional
(iconos, versiones hover y banners) a Canvas Files del curso destino y genera
mapa_plantilla.json para que el render los consuma DESDE ESE curso.

Por qué "desde ese curso": Canvas resuelve permisos por curso. Si una página
referencia un archivo alojado en OTRO curso, los estudiantes que no tengan acceso
a ese curso ven la imagen rota. Por eso cada curso debe tener su propia copia de
los assets, y sobre esa copia se arman las URLs.

Qué hace:
  - Escanea assets/plantilla/ recursivamente.
  - Sube cada archivo a la carpeta 'plantilla/<subruta>' en Canvas Files.
  - Reusa los que ya existen (mismo nombre + misma carpeta), salvo --forzar.
  - Deja los archivos visibles (hidden=False, locked=False).
  - Escribe mapa_plantilla.json:
        nombre_logico -> {"file_id": int, "url": str, "carpeta": str}
    nombre_logico = ruta relativa sin 'assets/plantilla/' ni extensión, con '/'.
        ej: "iconos/resultado_aprendizaje", "iconos/hover/home", "banners/hero_inicio"

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="..."
    python canvas_subir_plantilla.py --curso 89932
    python canvas_subir_plantilla.py --curso 89932 --dry-run
    python canvas_subir_plantilla.py --curso 89932 --forzar   # re-sube todo

Flags:
    --assets DIR   raíz de assets (def: assets/plantilla)
    --salida FILE  mapa de salida (def: mapa_plantilla.json)
    --carpeta X    carpeta raíz en Canvas Files (def: plantilla)
    --dry-run      lista qué haría, sin tocar Canvas
    --forzar       re-sube aunque ya exista
"""

import argparse
import json
import os
import sys
from pathlib import Path


def nombre_logico(ruta_rel):
    """assets/plantilla/iconos/hover/home.svg -> 'iconos/hover/home'"""
    p = ruta_rel.with_suffix("")
    return "/".join(p.parts)


def recolectar_assets(raiz):
    """Devuelve lista de (path_absoluto, nombre_logico, subcarpeta_relativa)."""
    raiz = Path(raiz)
    items = []
    for f in sorted(raiz.rglob("*")):
        if not f.is_file():
            continue
        if f.name.startswith("."):
            continue
        rel = f.relative_to(raiz)
        nl = nombre_logico(rel)
        subcarpeta = "/".join(rel.parts[:-1])  # '' si está en la raíz
        items.append((f, nl, subcarpeta))
    return items


def url_preview(canvas_url, curso_id, file_id):
    return "%s/courses/%s/files/%s/preview" % (
        canvas_url.rstrip("/"), curso_id, file_id)


def main():
    ap = argparse.ArgumentParser(description="Sube la plantilla institucional a Canvas Files.")
    ap.add_argument("--curso", type=int, required=True)
    ap.add_argument("--assets", default="assets/plantilla")
    ap.add_argument("--salida", default="mapa_plantilla.json")
    ap.add_argument("--carpeta", default="plantilla",
                    help="carpeta raíz en Canvas Files (def: plantilla)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--forzar", action="store_true",
                    help="re-sube aunque el archivo ya exista en el curso")
    args = ap.parse_args()

    if not Path(args.assets).exists():
        sys.exit("No existe el directorio de assets: %s" % args.assets)

    assets = recolectar_assets(args.assets)
    if not assets:
        sys.exit("No se encontraron archivos en %s" % args.assets)

    print("Assets a procesar: %d (desde %s)" % (len(assets), args.assets))
    for _, nl, sub in assets:
        print("  %s" % nl)

    # ── Dry-run: solo mostrar plan ───────────────────────────────
    if args.dry_run:
        print("\nDRY-RUN: no se tocó Canvas.")
        print("Carpeta raíz en Canvas Files: %s/" % args.carpeta)
        destinos = sorted({("%s/%s" % (args.carpeta, s)).rstrip("/") for _, _, s in assets})
        print("Carpetas destino:")
        for d in destinos:
            print("  course files/%s" % d)
        return

    # ── Conexión ─────────────────────────────────────────────────
    try:
        from canvasapi import Canvas
    except ImportError:
        sys.exit("Falta canvasapi:  pip install canvasapi")
    canvas_url = os.environ.get("CANVAS_URL")
    token = os.environ.get("CANVAS_TOKEN")
    if not canvas_url or not token:
        sys.exit("Define CANVAS_URL y CANVAS_TOKEN.")
    canvas = Canvas(canvas_url, token)
    try:
        curso = canvas.get_course(args.curso)
        print("\nConectado al curso: %s" % curso.name)
    except Exception as e:
        sys.exit("Error conectando al curso: %s" % e)

    # ── Índice de archivos existentes: (full_name_carpeta, display_name) -> File
    #    full_name de carpeta es tipo 'course files/plantilla/iconos'
    existentes = {}
    try:
        folders_por_id = {fo.id: fo.full_name for fo in curso.get_folders()}
        for fl in curso.get_files():
            carpeta = folders_por_id.get(getattr(fl, "folder_id", None), "")
            existentes[(carpeta, fl.display_name)] = fl
    except Exception as e:
        print("Aviso: no se pudo indexar archivos existentes (%s). Se subirá todo." % e)

    mapa = {}
    subidos = reusados = fallidos = 0

    for path, nl, sub in assets:
        parent_path = ("%s/%s" % (args.carpeta, sub)).rstrip("/")  # p.ej. plantilla/iconos
        full_name = ("course files/%s" % parent_path).rstrip("/")
        display = path.name

        # Reuso: solo si además el tamaño coincide (si cambiaste el archivo
        # local sin pasar --forzar, esto detecta la diferencia y re-sube en
        # vez de servir para siempre la versión vieja de Canvas).
        if not args.forzar and (full_name, display) in existentes:
            fl = existentes[(full_name, display)]
            local_size = path.stat().st_size
            remote_size = getattr(fl, "size", None)
            if remote_size is None or remote_size == local_size:
                mapa[nl] = {"file_id": fl.id,
                            "url": url_preview(canvas_url, args.curso, fl.id),
                            "carpeta": parent_path}
                reusados += 1
                print("  = reuso  %-40s (id %s)" % (nl, fl.id))
                continue
            else:
                print("  ~ cambiado %-40s (local %d B, Canvas %d B); re-subiendo..."
                      % (nl, local_size, remote_size))

        # Subida
        try:
            ok, resp = curso.upload(str(path), parent_folder_path=parent_path)
            if not ok:
                fallidos += 1
                print("  ✗ FALLO  %s -> %s" % (nl, resp))
                continue
            fid = resp["id"]
            # Asegurar visibilidad para estudiantes
            try:
                canvas.get_file(fid).update(locked=False, hidden=False)
            except Exception:
                pass
            mapa[nl] = {"file_id": fid,
                        "url": url_preview(canvas_url, args.curso, fid),
                        "carpeta": parent_path}
            subidos += 1
            print("  ✓ subido %-40s (id %s)" % (nl, fid))
        except Exception as e:
            fallidos += 1
            print("  ✗ ERROR  %s -> %s" % (nl, str(e)[:120]))

    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2)

    print("\n========== RESUMEN ==========")
    print("  Subidos:  %d" % subidos)
    print("  Reusados: %d" % reusados)
    print("  Fallidos: %d" % fallidos)
    print("  Mapa:     %s (%d entradas)" % (args.salida, len(mapa)))
    print("=============================")
    if fallidos:
        sys.exit(1)


if __name__ == "__main__":
    main()