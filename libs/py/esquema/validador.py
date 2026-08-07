"""Validación del curso.json.

Dos capas, y la distinción importa:

1. JSON Schema  -> integridad estructural (tipos, campos obligatorios, valores
   permitidos). Si falla, el documento se RECHAZA: no entra al sistema.

2. Reglas de negocio -> normas institucionales de EdiLoja (numeración de
   semanas, citas que existan, autoevaluación al cerrar unidad, texto
   alternativo). Si fallan, se emite una ALERTA con severidad. El documento
   entra y el docente lo corrige.

El semáforo resume el resultado: un solo error -> rojo. Solo avisos -> amarillo.
Nada -> verde.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator

# Ruta al esquema, subiendo desde libs/py/esquema/ hasta la raíz del proyecto.
RUTA_ESQUEMA = (
    Path(__file__).resolve().parents[3] / "packages" / "esquemas" / "curso.schema.json"
)

_esquema = json.loads(RUTA_ESQUEMA.read_text(encoding="utf-8"))
_validador_esquema = Draft202012Validator(_esquema)


@dataclass
class Alerta:
    """Un problema detectado. `nivel` es 'error' o 'aviso'."""

    nivel: str
    codigo: str
    mensaje: str
    pagina_id: str | None = None
    bloque_id: str | None = None
    ruta: str = ""


@dataclass
class Resultado:
    alertas: list[Alerta] = field(default_factory=list)

    @property
    def errores(self) -> list[Alerta]:
        return [a for a in self.alertas if a.nivel == "error"]

    @property
    def avisos(self) -> list[Alerta]:
        return [a for a in self.alertas if a.nivel == "aviso"]

    @property
    def semaforo(self) -> str:
        if self.errores:
            return "rojo"
        if self.alertas:
            return "amarillo"
        return "verde"

    def como_dict(self) -> dict:
        return {
            "semaforo": self.semaforo,
            "alertas": [asdict(a) for a in self.alertas],
        }


def validar(documento: dict) -> Resultado:
    """Valida un curso.json completo. Devuelve el resultado con su semáforo."""
    resultado = Resultado()

    # ── Capa 1: estructura ──
    for error in _validador_esquema.iter_errors(documento):
        resultado.alertas.append(
            Alerta(
                nivel="error",
                codigo="esquema",
                mensaje=error.message,
                ruta="/".join(str(p) for p in error.absolute_path),
            )
        )

    # Sin estructura válida, las reglas de negocio no tienen sentido.
    if resultado.errores:
        return resultado

    # ── Capa 2: reglas de negocio ──
    _regla_numero_de_semanas(documento, resultado)
    _regla_citas_existen(documento, resultado)
    _regla_autoevaluacion_al_cerrar(documento, resultado)
    _regla_texto_alternativo(documento, resultado)

    return resultado


# ─────────────────────────────────────────────────────────────
# Reglas de negocio de EdiLoja
# ─────────────────────────────────────────────────────────────


def _regla_numero_de_semanas(doc: dict, res: Resultado) -> None:
    """El número de páginas debe coincidir con total_semanas, sin saltos."""
    esperadas = doc["info_general"]["total_semanas"]
    paginas = doc["estructura"]["paginas"]
    numeros = sorted(p["semana"] for p in paginas)

    if len(paginas) != esperadas:
        res.alertas.append(
            Alerta(
                "error",
                "semanas_incompletas",
                f"Se esperaban {esperadas} semanas y hay {len(paginas)}",
            )
        )

    if numeros != list(range(1, len(numeros) + 1)):
        res.alertas.append(
            Alerta(
                "error",
                "semanas_desordenadas",
                f"La numeración de semanas tiene saltos o repeticiones: {numeros}",
            )
        )


def _regla_citas_existen(doc: dict, res: Resultado) -> None:
    """Toda cita debe apuntar a una referencia que exista. No inventar fuentes."""
    ids_referencia = {
        r["id"] for r in doc.get("finales", {}).get("referencias", [])
    }

    for pagina in doc["estructura"]["paginas"]:
        for bloque in _todos_los_bloques(pagina["bloques"]):
            if bloque["tipo"] == "cita":
                ref = bloque.get("referencia_id")
                if ref and ref not in ids_referencia:
                    res.alertas.append(
                        Alerta(
                            "error",
                            "cita_sin_referencia",
                            f"La cita apunta a '{ref}', que no existe en las referencias",
                            pagina_id=pagina["id"],
                            bloque_id=bloque["id"],
                            ruta=f"semana {pagina['semana']}",
                        )
                    )


def _regla_autoevaluacion_al_cerrar(doc: dict, res: Resultado) -> None:
    """Una semana que cierra unidad necesita autoevaluación de 10 preguntas."""
    for pagina in doc["estructura"]["paginas"]:
        if not pagina.get("cierra_unidad"):
            continue

        autoevals = [
            b for b in pagina["bloques"] if b["tipo"] == "autoevaluacion"
        ]

        if not autoevals:
            res.alertas.append(
                Alerta(
                    "error",
                    "falta_autoevaluacion",
                    f"La semana {pagina['semana']} cierra unidad y no tiene autoevaluación",
                    pagina_id=pagina["id"],
                    ruta=f"semana {pagina['semana']}",
                )
            )
            continue

        for bloque in autoevals:
            preguntas = bloque.get("preguntas", [])
            if len(preguntas) != 10:
                res.alertas.append(
                    Alerta(
                        "aviso",
                        "autoevaluacion_incompleta",
                        f"Se esperaban 10 preguntas y hay {len(preguntas)}",
                        pagina_id=pagina["id"],
                        bloque_id=bloque["id"],
                        ruta=f"semana {pagina['semana']}",
                    )
                )


def _regla_texto_alternativo(doc: dict, res: Resultado) -> None:
    """Las figuras de contenido (no decorativas) necesitan texto alternativo."""
    for pagina in doc["estructura"]["paginas"]:
        for bloque in _todos_los_bloques(pagina["bloques"]):
            if bloque["tipo"] in ("imagen", "diagrama"):
                if not bloque.get("decorativa") and not bloque.get("alt"):
                    res.alertas.append(
                        Alerta(
                            "aviso",
                            "falta_texto_alternativo",
                            f"El bloque {bloque['id']} necesita texto alternativo",
                            pagina_id=pagina["id"],
                            bloque_id=bloque["id"],
                            ruta=f"semana {pagina['semana']}",
                        )
                    )


def _todos_los_bloques(bloques: list[dict]):
    """Recorre bloques y también los anidados dentro de caja y focalizador."""
    for bloque in bloques:
        yield bloque
        yield from bloque.get("bloques", [])
