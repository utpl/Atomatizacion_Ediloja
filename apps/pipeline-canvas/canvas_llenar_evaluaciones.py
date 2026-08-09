#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
canvas_llenar_evaluaciones.py — Llena la página "Evaluaciones" en Canvas con
TODAS las autoevaluaciones de la guía y sus respectivos solucionarios.

Formato basado en el modelo institucional UTPL:
  - Cada autoevaluación numerada (Autoevaluación 1, 2, 3, ...) con sus
    preguntas en lista ordenada (1, 2, 3...) y opciones (a, b, c...).
  - Botón "Ir al solucionario" debajo de cada autoevaluación.
  - Sección final con las tablas de solucionario (Pregunta | Respuesta |
    Retroalimentación) con ancla para que el botón funcione.
  - Botón "Ir a la autoevaluación" en cada solucionario para volver.

Uso:
    export CANVAS_URL="https://utpl.test.instructure.com"
    export CANVAS_TOKEN="..."
    python canvas_llenar_evaluaciones.py salida_curada_canvas.json --curso 89932

Flags:
    --dry-run    no toca Canvas, imprime el HTML
    --publicar   publica la página tras llenarla
    --titulo X   título de la página (default: "Evaluaciones")
"""

import argparse
import html
import json
import os
import sys


# ============================================================
# Utilidades
# ============================================================

def esc(s):
    return html.escape(s or "", quote=True)


def obtener_autoevaluaciones(data):
    """Devuelve la lista de autoevaluaciones del JSON.

    Solo incluye las que tienen preguntas (las vacías o de placeholder se omiten).
    Las ordena por número de unidad.
    """
    autoevals = []
    for s in data.get("secciones", []):
        if s.get("tipo") == "autoevaluacion":
            preguntas = s.get("preguntas", [])
            if preguntas:
                autoevals.append(s)

    # Ordenar por unidad si está disponible
    autoevals.sort(key=lambda a: a.get("unidad") or 999)
    return autoevals


def obtener_solucionario(data):
    """Devuelve el solucionario consolidado del JSON, si existe."""
    for s in data.get("secciones", []):
        if s.get("tipo") == "solucionario":
            return s.get("soluciones", [])
    return []


# ============================================================
# Render HTML de las autoevaluaciones
# ============================================================

def render_pregunta(pregunta, indice_pregunta):
    """Renderiza UNA pregunta con sus opciones (sin la respuesta correcta visible).

    En el modelo institucional las opciones son una lista ordenada con type="a".
    """
    enunciado = pregunta.get("enunciado", "")
    opciones = pregunta.get("opciones", [])

    opciones_html = []
    for op in opciones:
        texto = op.get("texto", "")
        opciones_html.append(f'      <li>{esc(texto)}</li>')

    opciones_str = "\n".join(opciones_html)

    return f'''  <li>{esc(enunciado)}
    <ol type="a">
{opciones_str}
    </ol>
  </li>'''


def render_autoevaluacion(autoeval, numero_autoeval):
    """Renderiza UNA autoevaluación completa (instrucciones + preguntas + botón al solucionario)."""
    instrucciones = autoeval.get("instrucciones",
        "Lea detenidamente los enunciados de las preguntas y seleccione la respuesta que considere correcta.")
    preguntas = autoeval.get("preguntas", [])

    preguntas_html = []
    for i, p in enumerate(preguntas):
        preguntas_html.append(render_pregunta(p, i))

    preguntas_str = "\n".join(preguntas_html)

    return f'''<div id="autoevaluacion_{numero_autoeval}">
  <h2 style="color:#1F4E79;margin-top:24px;">Autoevaluación {numero_autoeval}</h2>
  <p><strong>{esc(instrucciones)}</strong></p>
  <ol>
{preguntas_str}
  </ol>
  <p style="margin:16px 0;">
    <a href="#solucionario_{numero_autoeval}"
       style="background:#1F4E79;color:white;padding:8px 16px;border-radius:6px;
              text-decoration:none;display:inline-block;font-weight:500;">
      Ir al solucionario
    </a>
  </p>
</div>'''


# ============================================================
# Render HTML de los solucionarios
# ============================================================

def render_solucionario(autoeval, numero_autoeval, solucionario_global=None):
    """Renderiza la tabla de solucionario de UNA autoevaluación.

    Prioridad de fuentes:
      1. autoeval.preguntas (cada pregunta ya tiene respuesta_correcta + retroalimentacion)
      2. solucionario_global (lista compartida con respuestas por unidad)
    """
    preguntas = autoeval.get("preguntas", [])
    unidad = autoeval.get("unidad")

    filas_html = []
    for i, p in enumerate(preguntas):
        numero = i + 1
        respuesta = p.get("respuesta_correcta", "")
        retro = p.get("retroalimentacion", "")

        # Si no hay datos en la pregunta, buscar en el solucionario global
        if (not respuesta or not retro) and solucionario_global:
            for sol in solucionario_global:
                if sol.get("unidad") == unidad and sol.get("pregunta") == numero:
                    respuesta = respuesta or sol.get("respuesta", "")
                    retro = retro or sol.get("retroalimentacion", "")
                    break

        filas_html.append(f'''      <tr>
        <td style="text-align:center;padding:8px;border:1px solid #d4dae6;">{numero}</td>
        <td style="text-align:center;padding:8px;border:1px solid #d4dae6;font-weight:600;">{esc(respuesta)}</td>
        <td style="padding:8px;border:1px solid #d4dae6;">{esc(retro)}</td>
      </tr>''')

    filas_str = "\n".join(filas_html)

    return f'''<div style="margin-top:32px;">
  <h3 id="solucionario_{numero_autoeval}" style="color:#1F4E79;text-align:center;">
    Autoevaluación {numero_autoeval}
  </h3>
  <table style="border-collapse:collapse;margin:0 auto;width:100%;max-width:900px;border:1px solid #d4dae6;">
    <thead style="background:#1F4E79;color:white;">
      <tr>
        <th style="padding:10px;border:1px solid #d4dae6;width:80px;">Pregunta</th>
        <th style="padding:10px;border:1px solid #d4dae6;width:100px;">Respuesta</th>
        <th style="padding:10px;border:1px solid #d4dae6;">Retroalimentación</th>
      </tr>
    </thead>
    <tbody>
{filas_str}
      <tr>
        <td colspan="3" style="text-align:center;padding:12px;border:1px solid #d4dae6;background:#f9fafc;">
          <a href="#autoevaluacion_{numero_autoeval}"
             style="background:#1F4E79;color:white;padding:8px 16px;border-radius:6px;
                    text-decoration:none;display:inline-block;font-weight:500;">
            Ir a la autoevaluación
          </a>
        </td>
      </tr>
    </tbody>
  </table>
</div>'''


# ============================================================
# HTML completo de la página
# ============================================================

def build_html(data, asignatura):
    autoevals = obtener_autoevaluaciones(data)
    solucionario_global = obtener_solucionario(data)

    if not autoevals:
        return '''<div style="padding:24px;background:#fef2f2;border-radius:8px;color:#dc2626;">
  <p><strong>⚠ No se encontraron autoevaluaciones en el JSON.</strong></p>
  <p>Verifica que hayas corrido <code>curar_autoevaluaciones.py</code> antes.</p>
</div>'''

    # Cabecera
    cabecera = f'''<div style="background:linear-gradient(135deg,#1F4E79 0%,#0D7D7D 100%);
                  color:white;padding:24px 32px;border-radius:8px;margin-bottom:24px;">
  <h1 style="margin:0;font-size:24px;">Evaluaciones de la asignatura</h1>
  <p style="margin:8px 0 0;opacity:.9;font-size:14px;">
    Asignatura: <strong>{esc(asignatura)}</strong> ·
    Total de autoevaluaciones: <strong>{len(autoevals)}</strong>
  </p>
  <p style="margin:12px 0 0;font-size:13px;opacity:.85;">
    Esta página es de uso interno del equipo de Diseño Web para revisar y validar
    las autoevaluaciones generadas/curadas por el agente de IA antes de su publicación.
  </p>
</div>'''

    # Índice/navegación rápida
    indice_items = []
    for i, a in enumerate(autoevals):
        n = i + 1
        unidad = a.get("unidad", "?")
        # estado_previo = estado original antes de curar (más informativo que estado_curacion)
        estado = a.get("estado_previo") or a.get("estado_curacion", "")
        badge_color = {
            "curar": "#0d7d7d",
            "completar_a_diez": "#f59e0b",
            "generar_desde_cero": "#ef4444",
            "curado_por_agente": "#0d7d7d",
        }.get(estado, "#6b7280")
        badge_label = {
            "curar": "Revisada del docente",
            "completar_a_diez": "Completada por IA",
            "generar_desde_cero": "Generada por IA",
            "curado_por_agente": "Curada",
        }.get(estado, estado.replace("_", " ").title() if estado else "")
        indice_items.append(f'''  <li style="margin:6px 0;">
    <a href="#autoevaluacion_{n}" style="color:#1F4E79;text-decoration:none;font-weight:500;">
      Autoevaluación {n}
    </a>
    <span style="color:#6b7280;font-size:13px;"> (Unidad {unidad})</span>
    {f'<span style="background:{badge_color};color:white;font-size:11px;padding:2px 8px;border-radius:10px;margin-left:8px;font-weight:600;">{esc(badge_label)}</span>' if badge_label else ''}
  </li>''')

    indice = f'''<div style="background:white;padding:20px 24px;border-radius:8px;
                  border-left:4px solid #1F4E79;margin-bottom:24px;">
  <h2 style="margin:0 0 12px;color:#1F4E79;font-size:18px;">Índice de autoevaluaciones</h2>
  <ul style="list-style:none;padding:0;margin:0;">
{chr(10).join(indice_items)}
  </ul>
</div>'''

    # Cuerpo de autoevaluaciones
    autoevals_html = []
    for i, a in enumerate(autoevals):
        autoevals_html.append(render_autoevaluacion(a, i + 1))
    autoevals_str = "\n<hr style=\"margin:32px 0;border:none;border-top:1px solid #e5e9f2;\">\n".join(autoevals_html)

    # Sección de solucionarios
    soluc_html = []
    for i, a in enumerate(autoevals):
        soluc_html.append(render_solucionario(a, i + 1, solucionario_global))
    soluc_str = "\n".join(soluc_html)

    solucionarios_seccion = f'''<div style="margin-top:48px;padding-top:32px;border-top:3px solid #1F4E79;">
  <h2 style="color:#1F4E79;text-align:center;">Solucionarios</h2>
  <p style="text-align:center;color:#6b7280;font-size:14px;margin-bottom:24px;">
    Respuestas correctas y retroalimentación de cada autoevaluación.
  </p>
{soluc_str}
</div>'''

    # Pie
    pie = '''<div style="margin-top:48px;padding:16px;text-align:center;color:#9ca3af;font-size:12px;">
  Página generada automáticamente · Proyecto Automatización EdiLoja · UTPL
</div>'''

    return cabecera + indice + '<div class="autoevaluaciones-cuerpo">' + autoevals_str + '</div>' + solucionarios_seccion + pie


# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser(
        description="Llena la página 'Evaluaciones' en Canvas con autoevaluaciones + solucionarios."
    )
    ap.add_argument("entrada", help="JSON canónico (recomendado: salida_curada_canvas.json)")
    ap.add_argument("--curso", type=int, required=True, help="ID del curso en Canvas")
    ap.add_argument("--titulo", default="Evaluaciones", help="Título de la página")
    ap.add_argument("--dry-run", action="store_true", help="No toca Canvas, imprime el HTML")
    ap.add_argument("--publicar", action="store_true", help="Publica la página tras actualizar")
    args = ap.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)

    asignatura = data.get("metadata", {}).get("asignatura") \
        or data.get("metadata", {}).get("titulo") \
        or "Asignatura"

    body = build_html(data, asignatura)

    if args.dry_run:
        print("=" * 70)
        print(f"DRY-RUN: HTML generado para la página '{args.titulo}'")
        print(f"Asignatura: {asignatura}")
        print(f"Tamaño del HTML: {len(body)} caracteres")
        print("=" * 70)
        print(body[:3000])
        if len(body) > 3000:
            print(f"\n... [{len(body) - 3000} caracteres más]")
        print("\nDRY-RUN: no se tocó Canvas.")
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

    # Buscar la página
    existentes = {pg.title: pg for pg in curso.get_pages()}
    pg = existentes.get(args.titulo)

    if not pg:
        print(f"⚠ La página '{args.titulo}' no existe. Crearla primero con:")
        print(f"  python canvas_crear_pagina_evaluaciones.py --curso {args.curso}")
        sys.exit(1)

    cambios = {"body": body}
    if args.publicar:
        cambios["published"] = True
    pg.edit(wiki_page=cambios)

    estado = " [PUBLICADA]" if args.publicar else ""
    print(f"✓ Página '{args.titulo}' actualizada ({len(body)} caracteres){estado}")
    print(f"  URL: {url}/courses/{args.curso}/pages/{pg.url}")

    # Verificar que NO esté en ningún módulo
    print()
    print("Nota: esta página NO se agrega a ningún módulo (uso interno).")


if __name__ == "__main__":
    main()