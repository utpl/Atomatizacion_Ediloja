#!/usr/bin/env python3
"""
importar_oferta.py — Da de alta docentes y guías desde la hoja de virtualización.

De dónde sale
-------------
La hoja de virtualización de EdiLoja tiene 990 asignaturas del periodo, cada
una con su código Banner, autor del metacurso, facultad, carrera, créditos,
horas y curso de Canvas. Es la fuente de verdad de qué se produce y quién lo
produce.

Qué crea
--------
- Un usuario con rol `docente` por cada correo institucional distinto.
- Una guía por asignatura, con los datos académicos ya rellenos.

Así el docente no escribe a mano lo que la institución ya sabe: solo aporta lo
suyo —resultado de aprendizaje, temario, metodología y bibliografía—, que es
donde está su criterio.

Qué NO hace, a propósito
------------------------
**No guarda el curso de Canvas como destino de publicación.** La hoja apunta a
utpl.instructure.com, que es PRODUCCIÓN. Si ese id acabara en
`guia.canvas_curso_id`, pulsar "Publicar" sobrescribiría un curso real con
cientos de estudiantes. Se guarda como referencia en los requerimientos y el
destino se deja vacío: lo escribe el operador cada vez, mirando.

**No importa cédulas.** Están en la hoja y son dato personal. El sistema no
las necesita para nada.

**No toca lo que ya existe.** Si la guía o el usuario ya están, se saltan. Una
reimportación no debe pisar el trabajo hecho.

Uso:
    python tools/importar_oferta.py hoja.csv --dry-run
    python tools/importar_oferta.py hoja.csv --limite 25
    python tools/importar_oferta.py hoja.csv --facultad "Ciencias Jurídicas"
"""
from __future__ import annotations

import argparse
import csv
import re
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from libs.py.auth.seguridad import cifrar_contrasena  # noqa: E402
from libs.py.db.modelos_auth import Rol, Usuario, UsuarioRol  # noqa: E402
from libs.py.db.modelos_dominio import Guia, SolicitudGeneracion  # noqa: E402
from libs.py.db.session import SesionLocal  # noqa: E402

# La cabecera real está en la fila 5 del CSV: las cuatro primeras son título,
# periodo y fecha del documento.
FILA_CABECERA = 4

COLUMNAS = {
    "codigo_componente": 1,
    "codigo_banner": 2,
    "asignatura": 3,
    "autor": 13,
    "correo": 15,
    "malla": 18,
    "facultad": 19,
    "carrera": 20,
    "creditos": 22,
    "horas": 23,
    "ciclo": 25,
    "url_canvas": 34,
    "modalidad": 38,
}


def _horas(bruto: str) -> dict[str, int]:
    """'Total:144\\nACD:48 APE:32 AA:64' -> {'total':144,'acd':48,...}

    El esquema declara info_general.horas como objeto con esas cuatro claves,
    así que se parsea aquí y no se deja como cadena.
    """
    salida: dict[str, int] = {}
    for clave, patron in [("total", r"total\s*:\s*(\d+)"),
                          ("acd", r"acd\s*:\s*(\d+)"),
                          ("ape", r"ape\s*:\s*(\d+)"),
                          ("aa", r"aa\s*:\s*(\d+)")]:
        m = re.search(patron, bruto or "", re.I)
        if m:
            salida[clave] = int(m.group(1))
    return salida


def _modalidad(bruto: str) -> str:
    """A veces la celda trae la carrera delante:
    'III Pedagogía de las Ciencias... - Modalidad en línea'.
    Se queda con la modalidad, que es lo que consume el prompt.
    """
    texto = (bruto or "").strip()
    m = re.search(r"modalidad\s+(a distancia y en l[ií]nea|en l[ií]nea|"
                  r"a distancia|presencial|h[ií]brida)", texto, re.I)
    return m.group(0).strip() if m else texto[:150]


def _correo(bruto: str) -> str:
    """Una celda puede traer varios correos separados por saltos o comas.
    Se coge el primero: es el autor del metacurso, el que trabaja la guía.
    """
    for trozo in re.split(r"[\s,;]+", bruto or ""):
        if "@" in trozo:
            return trozo.strip().lower()
    return ""


def leer(ruta: Path) -> list[dict[str, str]]:
    with ruta.open(encoding="utf-8") as f:
        filas = list(csv.reader(f))

    salida = []
    for fila in filas[FILA_CABECERA + 1:]:
        if len(fila) <= max(COLUMNAS.values()):
            continue
        registro = {clave: fila[i].strip() for clave, i in COLUMNAS.items()}
        if not registro["codigo_banner"] or not _correo(registro["correo"]):
            continue
        registro["correo"] = _correo(registro["correo"])
        salida.append(registro)
    return salida


def importar(registros, sesion, dry_run=False):
    rol = sesion.query(Rol).filter_by(codigo="docente").first()
    if rol is None:
        rol = Rol(codigo="docente", nombre="Docente")
        sesion.add(rol)
        sesion.flush()

    creados_usuarios: dict[str, str] = {}
    resumen = {"usuarios": 0, "guias": 0, "usuarios_existentes": 0,
               "guias_existentes": 0}

    for r in registros:
        # --- usuario ---
        usuario = sesion.query(Usuario).filter_by(correo=r["correo"]).first()
        if usuario is None:
            # Contraseña temporal aleatoria. Sin correo saliente montado, se
            # imprime al final para entregarla a mano. Cuando llegue el SSO,
            # esto desaparece.
            clave = secrets.token_urlsafe(9)
            usuario = Usuario(correo=r["correo"],
                              nombre_completo=r["autor"] or r["correo"],
                              hash_contrasena=cifrar_contrasena(clave),
                              activo=True)
            sesion.add(usuario)
            sesion.flush()
            sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id,
                                  ambito_tipo="global"))
            creados_usuarios[r["correo"]] = clave
            resumen["usuarios"] += 1
        else:
            resumen["usuarios_existentes"] += 1

        # --- guía ---
        existente = (sesion.query(Guia)
                     .filter_by(codigo_banner=r["codigo_banner"],
                                periodo="2026-1")
                     .first())
        if existente is not None:
            resumen["guias_existentes"] += 1
            continue

        guia = Guia(
            codigo_banner=r["codigo_banner"],
            codigo_componente=r["codigo_componente"] or None,
            nombre_asignatura=r["asignatura"],
            periodo="2026-1",
            total_semanas=8,
            autor_id=usuario.id,
            estado="borrador",
            # canvas_curso_id se deja VACÍO a propósito: la hoja apunta a
            # producción y publicar ahí sobrescribiría un curso con
            # estudiantes. El operador escribe el destino cada vez.
        )
        sesion.add(guia)
        sesion.flush()

        # Los datos académicos van como requerimientos en borrador: el
        # formulario los muestra rellenos y el docente completa los suyos.
        sesion.add(SolicitudGeneracion(
            guia_id=guia.id, solicitada_por=usuario.id,
            alcance="guia_completa", estado="borrador",
            requerimientos={
                "subjectCode": r["codigo_banner"],
                "subjectName": r["asignatura"],
                "academicPeriod": "2026-1",
                "faculty": r["facultad"],
                "program": r["carrera"],
                "credits": r["creditos"],
                "modality": _modalidad(r["modalidad"]),
                "level": "Grado",
                "weeks": 8,
                # Los aporta el docente: son los que llevan su criterio.
                "learningOutcome": "",
                "contents": "",
                "methodology": "",
                "bibliography": "",
                # Referencia, NO destino de publicación.
                "_origen_hoja": {
                    "url_canvas_produccion": r["url_canvas"],
                    "malla": r["malla"],
                    "ciclo": r["ciclo"],
                    "horas": _horas(r["horas"]),
                    "codigo_componente": r["codigo_componente"],
                },
            },
        ))
        resumen["guias"] += 1

    if dry_run:
        sesion.rollback()
    else:
        sesion.commit()

    return resumen, creados_usuarios


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="hoja de virtualización")
    ap.add_argument("--limite", type=int, default=25,
                    help="cuántas asignaturas importar (por defecto 25)")
    ap.add_argument("--facultad", default=None, help="filtra por facultad")
    ap.add_argument("--todo", action="store_true",
                    help="importa las 990: llena la base de guías que nadie tocará")
    ap.add_argument("--dry-run", action="store_true",
                    help="enseña qué haría, sin escribir nada")
    args = ap.parse_args()

    registros = leer(Path(args.csv))
    if args.facultad:
        registros = [r for r in registros
                     if args.facultad.lower() in r["facultad"].lower()]
    if not args.todo:
        registros = registros[:args.limite]

    print(f"Asignaturas a procesar: {len(registros)}")
    print(f"Docentes distintos:     {len({r['correo'] for r in registros})}")
    print()

    sesion = SesionLocal()
    try:
        resumen, claves = importar(registros, sesion, dry_run=args.dry_run)
    finally:
        sesion.close()

    print("=" * 52)
    print(f"  Usuarios creados:   {resumen['usuarios']}")
    print(f"  Usuarios ya había:  {resumen['usuarios_existentes']}")
    print(f"  Guías creadas:      {resumen['guias']}")
    print(f"  Guías ya había:     {resumen['guias_existentes']}")
    print("=" * 52)

    if args.dry_run:
        print("\nDRY-RUN: no se escribió nada.")
        return

    if claves:
        print("\nContraseñas temporales (entregar a mano y pedir que la cambien):")
        for correo, clave in sorted(claves.items()):
            print(f"  {correo:<40} {clave}")
        print("\nNo quedan guardadas en ningún sitio: cópialas ahora.")


if __name__ == "__main__":
    main()
