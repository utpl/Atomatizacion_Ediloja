"""Traduce las variantes que produce el modelo a las claves del esquema.

Por que existe
--------------
El prompt pide las claves canonicas y el modelo, aun asi, escribe a veces
`contenido` en vez de `bloques`, listas de cadenas en vez de objetos, o
`pregunta` en vez de `enunciado`. Son sinonimos obvios para una persona y
rechazos duros para `additionalProperties: false`.

Afinar el prompt reduce la frecuencia pero no la elimina: los modelos cambian
entre versiones y el fallo aparece 25 minutos y varios centavos despues. Esta
capa es la red de seguridad, y el prompt es la primera linea.

Solo se traducen equivalencias INEQUIVOCAS. Si algo es ambiguo se deja tal
cual y que lo rechace el validador: normalizar de mas esconderia errores
reales del modelo.
"""
from __future__ import annotations

from typing import Any

# Claves que el modelo usa como sinonimo de la canonica.
SINONIMOS_HIJOS = ("contenido", "children", "elementos_hijos")
SINONIMOS_ITEMS = ("elementos", "puntos")

# Claves que no existen en el esquema y no aportan nada: se descartan.
# `estilo` es sugerencia de formato; el estilo lo decide el CSS, no el modelo.
CLAVES_DESCARTADAS = ("estilo", "descripcion", "clase", "css")

CONTENEDORES = ("caja", "focalizador")


def _items_a_objetos(valor: Any) -> Any:
    """`["a", "b"]` → `[{"texto": "a"}, {"texto": "b"}]`.

    El esquema exige objetos porque un item puede llevar sublista. El modelo
    escribe cadenas cuando no la necesita.
    """
    if not isinstance(valor, list):
        return valor
    salida = []
    for it in valor:
        if isinstance(it, str):
            salida.append({"texto": it})
        elif isinstance(it, dict):
            nuevo = {"texto": it.get("texto", it.get("text", ""))}
            if isinstance(it.get("items"), list):
                nuevo["items"] = [
                    {"texto": s} if isinstance(s, str) else {"texto": s.get("texto", "")}
                    for s in it["items"]
                ]
            salida.append(nuevo)
        else:
            salida.append(it)
    return salida


def _normalizar_pregunta(p: dict[str, Any]) -> dict[str, Any]:
    """Los nombres alternativos de la autoevaluacion."""
    q = dict(p)
    if "enunciado" not in q:
        for alt in ("pregunta", "texto", "question"):
            if alt in q:
                q["enunciado"] = q.pop(alt)
                break
    if "correcta" not in q:
        for alt in ("respuestaCorrecta", "respuesta_correcta", "correct"):
            if alt in q:
                q["correcta"] = q.pop(alt)
                break

    # La letra correcta debe ser a-e. Si el modelo devolvio el texto de la
    # opcion en vez de la letra, se busca a que opcion corresponde.
    opciones = q.get("opciones") or []
    if isinstance(opciones, list):
        nuevas = []
        for i, o in enumerate(opciones):
            letra = "abcde"[i] if i < 5 else "e"
            if isinstance(o, str):
                nuevas.append({"letra": letra, "texto": o})
            elif isinstance(o, dict):
                nuevas.append({
                    "letra": str(o.get("letra", letra))[:1].lower(),
                    "texto": o.get("texto", o.get("text", "")),
                })
        q["opciones"] = nuevas

        correcta = str(q.get("correcta", "")).strip()
        if correcta.isdigit():
            # El modelo devolvio el indice de la opcion. Puede ser base 0 o
            # base 1; se prueba base 1 primero porque es lo que escribe cuando
            # las opciones vienen numeradas para una persona.
            i = int(correcta)
            indice = i - 1 if 1 <= i <= len(nuevas) else i
            if 0 <= indice < len(nuevas):
                q["correcta"] = nuevas[indice]["letra"]
        elif len(correcta) == 1:
            q["correcta"] = correcta.lower()
        else:
            for o in nuevas:
                if o["texto"].strip() == correcta:
                    q["correcta"] = o["letra"]
                    break

    if "retroalimentacion" not in q:
        for alt in ("feedback", "explicacion"):
            if alt in q:
                q["retroalimentacion"] = q.pop(alt)
                break

    return {k: v for k, v in q.items() if k in
            ("id", "numero", "enunciado", "opciones", "correcta", "retroalimentacion")}


def normalizar_bloque(bloque: Any, profundidad: int = 1) -> dict[str, Any]:
    if not isinstance(bloque, dict):
        return bloque

    b = {k: v for k, v in bloque.items() if k not in CLAVES_DESCARTADAS}
    tipo = b.get("tipo")

    # Hijos: `contenido` → `bloques`, solo en contenedores.
    for alt in SINONIMOS_HIJOS:
        if alt in b:
            valor = b.pop(alt)
            if tipo in CONTENEDORES and isinstance(valor, list):
                b["bloques"] = valor
            elif isinstance(valor, str) and "texto" not in b:
                # Un no-contenedor con `contenido` de texto: era el `texto`.
                b["texto"] = valor

    if tipo in CONTENEDORES and isinstance(b.get("bloques"), list):
        b["bloques"] = [normalizar_bloque(h, profundidad + 1) for h in b["bloques"]]

    if tipo == "lista":
        for alt in SINONIMOS_ITEMS:
            if alt in b and "items" not in b:
                b["items"] = b.pop(alt)
        b["items"] = _items_a_objetos(b.get("items", []))

    if tipo == "encabezado":
        # El esquema admite h1-h4. Un nivel 5 se recorta en vez de rechazar la
        # semana entera: la jerarquia se mantiene, solo se aplana el ultimo.
        try:
            b["nivel"] = max(1, min(4, int(b.get("nivel", 2))))
        except (TypeError, ValueError):
            b["nivel"] = 2

    if tipo == "recurso_ediloja" and "url" not in b:
        # Sin url el bloque no valida y no hay forma de inventarla.
        # Se degrada a parrafo para no perder el contenido.
        texto = b.get("texto") or b.get("titulo") or ""
        return {"tipo": "parrafo", "texto": texto, **({"origen": b["origen"]} if "origen" in b else {})}

    if tipo == "autoevaluacion" and isinstance(b.get("preguntas"), list):
        b["preguntas"] = [
            _normalizar_pregunta(p) for p in b["preguntas"] if isinstance(p, dict)
        ]
        for i, p in enumerate(b["preguntas"], start=1):
            p.setdefault("id", f"q{i}")
            p.setdefault("numero", i)

    return b


def normalizar_pagina(pagina: dict[str, Any]) -> dict[str, Any]:
    p = dict(pagina)
    if isinstance(p.get("bloques"), list):
        p["bloques"] = [normalizar_bloque(b) for b in p["bloques"]]
    return p
