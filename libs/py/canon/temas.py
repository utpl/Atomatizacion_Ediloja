"""Temas visuales disponibles.

Cada tema es una COPIA del CSS que está subido como tema global en Canvas.
El editor la carga para previsualizar; al publicar no se enlaza nada, porque
Canvas ya aplica el suyo a nivel de cuenta.

Se registra aquí y no en la plantilla porque va a haber varios: cuando la
guía lleve su propio tema, se lee de la base y esta lista es el catálogo.
"""
from __future__ import annotations

TEMAS: dict[str, dict[str, str]] = {
    "metacurso_2026": {
        "nombre": "Metacurso UTPL 2026",
        "hojas": ["style.css", "style_app.css"],
    },
}

TEMA_POR_DEFECTO = "metacurso_2026"


def hojas_de(tema: str | None = None) -> list[str]:
    """Rutas de las hojas del tema, listas para el atributo href."""
    clave = tema if tema in TEMAS else TEMA_POR_DEFECTO
    return [f"/estatico/temas/{clave}/{h}" for h in TEMAS[clave]["hojas"]]
