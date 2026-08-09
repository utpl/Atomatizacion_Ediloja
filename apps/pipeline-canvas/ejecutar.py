#!/usr/bin/env python3
"""Lanzador de los scripts del pipeline con el .env ya cargado.

Los 13 scripts heredados leen la configuración con os.getenv, y fallan con
"Define CANVAS_URL y CANVAS_TOKEN" cuando nadie exportó las variables. Este
lanzador las pone y ejecuta el script pedido.

Se hace así y no reescribiendo cada script porque son código heredado que
funciona: el beneficio no compensa el riesgo de tocarlos.

Uso:
    python ejecutar.py render_inicio_ed.py entrada.json --curso 90020 --subir
"""
import os
import runpy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ENV = RAIZ / ".env"

if ENV.exists():
    for linea in ENV.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave, valor = clave.strip(), valor.strip().strip("'\"")
        # Una variable exportada y VACÍA no gana sobre el .env: es el fallo
        # más desconcertante que da esto, porque no se ve al mirar el entorno.
        if valor and not os.environ.get(clave):
            os.environ[clave] = valor

if len(sys.argv) < 2:
    print("uso: python ejecutar.py <script.py> [argumentos...]")
    raise SystemExit(2)

script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
