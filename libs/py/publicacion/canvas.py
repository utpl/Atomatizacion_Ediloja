"""Publicación de una guía en Canvas, orquestando el pipeline.

Cómo se reutiliza el pipeline
-----------------------------
Los scripts de apps/pipeline-canvas tienen toda su lógica dentro de main()
con argparse: no exponen funciones que se puedan importar. Se invocan como
SUBPROCESOS en vez de reescribirlos.

No es elegante, pero es la decisión correcta hoy: son ~2000 líneas probadas
contra Canvas real, y refactorizarlas para poder importarlas es trabajo con
riesgo y sin beneficio inmediato. Cuando haga falta (por ejemplo, para
reintentar un paso suelto), se extraen a funciones una a una.

render_utpl sí expone html_semana_utpl(), así que ese se importa: es el que
más va a cambiar y el que conviene tener bajo prueba.

Orden de los pasos, y por qué
-----------------------------
1. Assets      — los iconos deben existir ANTES de referenciarlos, y van al
                 curso destino: Canvas resuelve permisos por curso, y un
                 archivo alojado en otro curso se ve roto para el estudiante.
2. Módulos     — las páginas se asocian a su módulo al crearse.
3. Páginas     — vacías y SIN PUBLICAR, para que el operador revise.
4. Contenido   — una llamada por semana.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[3]
PIPELINE = RAIZ / "apps" / "pipeline-canvas"


class ErrorDePublicacion(RuntimeError):
    pass


def _ejecutar(argumentos: list[str], paso: str, tiempo_maximo: int = 600) -> str:
    """Lanza un script del pipeline y devuelve su salida.

    Se pasa el entorno tal cual: CANVAS_URL y CANVAS_TOKEN vienen del .env que
    ya cargó el proceso. El worker es otro proceso que la API, así que sin esto
    los scripts leerían valores por defecto.
    """
    try:
        proceso = subprocess.run(
            # Via ejecutar.py: carga el .env antes de correr el script.
            # Los scripts heredados leen con os.getenv y el worker no
            # siempre tiene las variables exportadas.
            [sys.executable, "ejecutar.py", *argumentos],
            cwd=str(PIPELINE),
            capture_output=True,
            text=True,
            timeout=tiempo_maximo,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ErrorDePublicacion(f"{paso}: se agotó el tiempo ({tiempo_maximo}s)") from exc

    if proceso.returncode != 0:
        cola = (proceso.stderr or proceso.stdout or "").strip().splitlines()[-5:]
        raise ErrorDePublicacion(f"{paso} falló: {' | '.join(cola)}")

    return proceso.stdout


def publicar(
    curso: dict[str, Any],
    canvas_curso_id: int,
    canvas_url: str,
    avisar: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """Publica una guía completa. `curso` es el curso.json v1.0.0.

    `avisar(porcentaje, mensaje)` se llama en cada paso. Se pasa una función en
    vez de escribir en la base desde aquí: este módulo no importa SQLAlchemy y
    no debe empezar. El worker le pasa una que hace el commit.
    """
    from libs.py.publicacion.adaptador_canonico import convertir

    def paso(pct: int, msg: str) -> None:
        if avisar is not None:
            avisar(pct, msg)

    canonico = convertir(curso)
    semanas = len(canonico["secciones"][0]["unidades"])

    # El JSON va a un temporal dentro del pipeline: los scripts lo reciben como
    # argumento posicional y resuelven rutas relativas a su propio directorio.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", dir=str(PIPELINE), delete=False, encoding="utf-8"
    ) as f:
        json.dump(canonico, f, ensure_ascii=False)
        ruta_json = Path(f.name)

    try:
        paso(5, "Subiendo los recursos de la plantilla")
        _ejecutar(["canvas_subir_plantilla.py", "--curso", str(canvas_curso_id)],
                  "Subida de la plantilla", tiempo_maximo=900)

        paso(20, "Creando los módulos")
        _ejecutar(["canvas_crear_modulos.py", ruta_json.name,
                   "--curso", str(canvas_curso_id)], "Creación de módulos")

        paso(30, "Creando las páginas")
        _ejecutar(["canvas_crear_paginas.py", ruta_json.name,
                   "--curso", str(canvas_curso_id)], "Creación de páginas")

        # El contenido no pasa por subproceso: render_utpl expone función y la
        # subida es un PUT. Así se reporta el avance semana a semana.
        import os

        import requests

        sys.path.insert(0, str(PIPELINE))
        import render_utpl  # noqa: PLC0415

        mapa = json.loads((PIPELINE / "mapa_plantilla.json").read_text(encoding="utf-8"))
        cabeceras = {"Authorization": f"Bearer {os.getenv('CANVAS_TOKEN', '')}"}
        base = canvas_url.rstrip("/")

        publicadas = []
        for n in range(1, semanas + 1):
            html = render_utpl.html_semana_utpl(
                canonico, n, mapa, base, str(canvas_curso_id))
            r = requests.put(
                f"{base}/api/v1/courses/{canvas_curso_id}/pages/semana-{n}",
                headers=cabeceras, data={"wiki_page[body]": html}, timeout=120)
            if r.status_code >= 400:
                raise ErrorDePublicacion(
                    f"Semana {n}: Canvas devolvió {r.status_code}. "
                    "Comprueba que la página exista y que el token tenga permisos.")
            publicadas.append(n)
            paso(30 + int(65 * n / semanas), f"Semana {n} de {semanas} publicada")

        # La pagina de Inicio es lo primero que ve el estudiante, y ademas
        # se marca como portada para que el curso NO abra en modulos.
        paso(96, "Creando la página de inicio")
        try:
            _ejecutar(["render_inicio_ed.py", ruta_json.name,
                       "--curso", str(canvas_curso_id),
                       "--mapa-plantilla", "mapa_plantilla.json",
                       "--subir", "--publicar"],
                      "Página de inicio", tiempo_maximo=300)
        except ErrorDePublicacion as exc:
            # No tumba la publicación: las semanas ya están subidas y eso es
            # lo que cuesta. La portada se puede rehacer sola.
            paso(96, f"Aviso: la página de inicio falló ({exc})")

        paso(100, "Publicación terminada")
        return {
            "curso_canvas": canvas_curso_id,
            "semanas": publicadas,
            "url": f"{base}/courses/{canvas_curso_id}",
        }
    finally:
        ruta_json.unlink(missing_ok=True)
