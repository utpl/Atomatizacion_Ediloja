"""Construcción de las instrucciones que se le mandan al modelo.

Dos capas, deliberadamente separadas:

- PROMPT_INSTITUCIONAL: texto oficial de la UTPL. Va **verbatim**. No se toca
  sin acta. Si mañana el vicerrectorado cambia una coma, se cambia aquí y en
  ningún otro sitio.
- PROMPT_FORMATO: instrucciones técnicas nuestras sobre cómo estructurar el
  JSON. Esto se itera libremente, es código nuestro.

La razón de separarlas no es estética: es que cuando la guía salga mal, hay que
poder decir si falló el encargo institucional o falló nuestra especificación
técnica. Si van mezcladas en un solo string, no se puede.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# CAPA 1 — Institucional (UTPL). VERBATIM. No editar sin acta.
# ---------------------------------------------------------------------------

PROMPT_INSTITUCIONAL = """
[PENDIENTE: pegar aquí el texto institucional de la UTPL tal cual lo entreguen.
No reescribir, no resumir, no "mejorar" la redacción.]
""".strip()


# ---------------------------------------------------------------------------
# Vocabulario controlado: los 18 focalizadores del canon
# ---------------------------------------------------------------------------

FOCALIZADORES: tuple[str, ...] = (
    "informacion_importante",
    "orientacion_actividades",
    "muy_bien",
    "apuntar",
    "avancemos",
    "buscar",
    "caso",
    "ejemplo",
    "ejercicio",
    "enlace",
    "foro",
    "importante",
    "lectura",
    "nota",
    "observe",
    "recuerde",
    "reflexione",
    "video",
)

TIPOS_DE_BLOQUE: tuple[str, ...] = (
    "parrafo",
    "encabezado",
    "lista",
    "tabla",
    "caja",
    "focalizador",
    "cita",
    "imagen",
    "diagrama",
    "recurso_ediloja",
    "autoevaluacion",
    "actividades",
)

# Marcado inline permitido dentro de los campos de texto.
ETIQUETAS_INLINE: tuple[str, ...] = ("strong", "em", "u", "sub", "sup", "a", "br")


# ---------------------------------------------------------------------------
# CAPA 2 — Formato (nuestro). Se itera libremente.
# ---------------------------------------------------------------------------

PROMPT_FORMATO = f"""
## Formato de salida

Devuelve **exclusivamente** un objeto JSON. Sin texto antes ni después, sin
explicaciones, sin vallas de código markdown.

El objeto representa **una página** (una semana) y tiene esta forma:

{{
  "titulo": "string",
  "bloques": [ ... ]
}}

## Tipos de bloque permitidos

Solo estos {len(TIPOS_DE_BLOQUE)}: {", ".join(TIPOS_DE_BLOQUE)}.

Cualquier otro tipo hace que la página se rechace entera.

## Reglas de contenido

1. **No inventes identificadores.** No pongas campos `id`, `numero`, `figura`
   ni referencias tipo "Figura 3". La numeración la asigna nuestro código
   después. Si necesitas referirte a una imagen, descríbela en el `alt`.
2. **Marcado inline:** dentro de los textos solo puedes usar
   {", ".join(f"<{e}>" for e in ETIQUETAS_INLINE)}. Nada más. Nada de <div>,
   <span>, <p> ni atributos de estilo.
3. **Anidamiento:** un bloque puede contener otros bloques únicamente si es de
   tipo `caja` o `focalizador`, y solo un nivel. Los hijos van en un campo
   llamado `bloques`, no `contenido`. Los bloques de dentro no pueden a su vez
   contener bloques.
4. **Focalizadores:** el campo `focalizador` de un bloque de tipo
   `focalizador` debe ser uno de estos exactamente: {", ".join(FOCALIZADORES)}.
5. **Citas:** si citas bibliografía, usa únicamente las obras que se te
   entregan en la entrada. No inventes referencias, autores ni años.
6. **Imágenes y diagramas:** describe qué debe mostrarse en el campo `alt`. No
   generes URLs ni rutas de archivo.

## Estilo

Escribe en español, en segunda persona formal ("usted"), dirigido al
estudiante. Frases claras y cortas. Evita el relleno académico.
""".strip()


def construir_instrucciones(prompt_institucional: str | None = None) -> str:
    """Une las dos capas en el texto de sistema que recibe el modelo.

    El parámetro existe para poder inyectar otro texto institucional en las
    pruebas sin tocar la constante.
    """
    institucional = (
        prompt_institucional if prompt_institucional is not None else PROMPT_INSTITUCIONAL
    )
    return f"{institucional}\n\n---\n\n{PROMPT_FORMATO}"
