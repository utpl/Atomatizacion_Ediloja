#!/usr/bin/env python3
"""Borra las guías de prueba y deja la base lista para la demo.

A diferencia de los usuarios, las guías SÍ se borran: no hay historial que
proteger en algo que nunca salió de un entorno de pruebas. El cascade se lleva
sus versiones, solicitudes, ediciones y cuotas.

    python tools/limpiar_pruebas.py --dry-run --vacias
    python tools/limpiar_pruebas.py --ids 1,2,3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs.py.db.modelos_dominio import Guia  # noqa: E402
from libs.py.db.session import SesionLocal  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", help="ids separados por coma")
    ap.add_argument("--vacias", action="store_true",
                    help="las que no tienen ninguna version")
    ap.add_argument("--todo", action="store_true",
                    help="TODAS, incluidas las publicadas")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sesion = SesionLocal()
    try:
        todas = sesion.query(Guia).order_by(Guia.id).all()

        if args.ids:
            pedidos = {int(x) for x in args.ids.split(",")}
            candidatas = [g for g in todas if g.id in pedidos]
        elif args.vacias:
            candidatas = [g for g in todas if not g.versiones]
        elif args.todo:
            candidatas = todas
        else:
            ap.error("indica --ids, --vacias o --todo")

        if not candidatas:
            print("No hay nada que borrar.")
            return

        print(f"Se borrarian {len(candidatas)} guias:\n")
        for g in candidatas:
            print(f"  {g.id:>3} · {g.codigo_banner:<14} · "
                  f"{g.nombre_asignatura[:30]:<30} · {g.estado:<12} · "
                  f"{len(g.versiones)} version(es)")

        if args.dry_run:
            print("\nDRY-RUN: no se borro nada.")
            return

        print("\nEsto NO se puede deshacer. Escribe BORRAR para confirmar: ", end="")
        if input().strip() != "BORRAR":
            print("Cancelado.")
            return

        for g in candidatas:
            sesion.delete(g)
        sesion.commit()
        print(f"\n{len(candidatas)} guias borradas.")
    finally:
        sesion.close()


if __name__ == "__main__":
    main()
