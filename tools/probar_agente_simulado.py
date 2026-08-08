"""Genera una guía completa con un modelo SIMULADO y la escribe a disco.

No llama a ninguna API. Sirve para ver con tus ojos qué forma tiene el
`curso.json` que produce el agente, y para enseñarlo en la reunión sin depender
de que la UTPL haya confirmado el modelo.

    python tools/probar_agente_simulado.py
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.py.agente.cliente import RespuestaModelo
from libs.py.agente.generador import generar_guia

SALIDA = Path("datos_ejemplo/simulado/curso_simulado.json")


def _pagina(semana: int) -> dict:
    return {
        "titulo": f"Semana {semana}: fundamentos",
        "bloques": [
            {"tipo": "encabezado", "nivel": 2, "texto": "Introducción"},
            {
                "tipo": "parrafo",
                "texto": "En esta semana revisará los conceptos <strong>básicos</strong>.",
            },
            {
                "tipo": "focalizador",
                "variante": "recuerde",
                "contenido": [
                    {"tipo": "parrafo", "texto": "Repase el material antes de continuar."}
                ],
            },
            {"tipo": "imagen", "alt": "Esquema del proceso contable"},
            {
                "tipo": "lista",
                "ordenada": False,
                "elementos": ["Identificar", "Registrar", "Clasificar"],
            },
        ],
    }


def modelo_simulado(instrucciones: str, contenido: str) -> RespuestaModelo:
    """Adivina qué semana le piden y devuelve una página coherente."""
    semana = 1
    for linea in contenido.splitlines():
        if linea.startswith("Semana:"):
            semana = int(linea.split(":")[1].strip())
            break
    return RespuestaModelo(
        texto=json.dumps(_pagina(semana), ensure_ascii=False),
        tokens_entrada=1200,
        tokens_salida=900,
    )


def validador_provisional(curso: dict) -> dict:
    """Sustituto del validador institucional para esta prueba.

    Cuando lo pruebes contra el de verdad, borra esto y quita el argumento
    `validar=` de la llamada de abajo.
    """
    return {"semaforo": "verde", "alertas": []}


def main() -> None:
    datos_curso = {
        "nombre": "Contabilidad General",
        "codigo": "CONT-1140",
        "periodo": "2026-1",
        "semanas": 8,
    }
    plan = [
        {"semana": n, "unidad": 1 if n <= 4 else 2, "cierra_unidad": n in (4, 8)}
        for n in range(1, 9)
    ]

    curso = generar_guia(
        datos_curso,
        plan=plan,
        bibliografia=["Horngren, C. (2012). Contabilidad de costos. Pearson."],
        llamador=modelo_simulado,
        validar=validador_provisional,
    )

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(curso, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Escrito: {SALIDA}")
    print(json.dumps(curso["estadisticas"], ensure_ascii=False, indent=2))
    print(json.dumps(curso["telemetria"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
