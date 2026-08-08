"""Único punto del sistema que habla con el proveedor del modelo.

Todo lo demás del agente llama a `llamar_modelo()` y no sabe (ni debe saber) si
detrás hay Anthropic, OpenAI, Gemini o un modelo alojado en la UTPL.

**Este es el archivo a cambiar si el proveedor no es Claude.** El resto del
agente no se toca: `generador.py`, `ensamblado.py` y `contexto.py` no importan
la librería del proveedor por ninguna parte.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Ajustar al modelo real que confirme la UTPL.
MODELO = os.getenv("MODELO_AGENTE", "claude-sonnet-4-5")
MAX_TOKENS = int(os.getenv("MAX_TOKENS_AGENTE", "8000"))
TEMPERATURA = float(os.getenv("TEMPERATURA_AGENTE", "0.3"))


@dataclass(frozen=True)
class RespuestaModelo:
    """Lo que devuelve el proveedor, ya despegado de su formato propio."""

    texto: str
    tokens_entrada: int = 0
    tokens_salida: int = 0

    @property
    def tokens_totales(self) -> int:
        return self.tokens_entrada + self.tokens_salida


# Cliente perezoso: no se crea al importar el módulo, sino en la primera
# llamada. Así los tests y el arranque de la API no exigen que exista la clave
# de API en el entorno.
_cliente = None


def _obtener_cliente():
    global _cliente
    if _cliente is None:
        import anthropic  # import local: solo se necesita si se llama de verdad

        clave = os.getenv("ANTHROPIC_API_KEY")
        if not clave:
            raise RuntimeError(
                "Falta ANTHROPIC_API_KEY en el entorno. "
                "Revisa el .env o las variables del contenedor."
            )
        _cliente = anthropic.Anthropic(api_key=clave)
    return _cliente


def llamar_modelo(instrucciones: str, contenido: str) -> RespuestaModelo:
    """Manda una petición al modelo y devuelve el texto crudo de la respuesta.

    `instrucciones` es el prompt de sistema (las dos capas ya unidas).
    `contenido` es la entrada concreta de esta llamada (la semana a generar).

    No intenta parsear el JSON ni validar nada: eso es trabajo de `generador.py`.
    Esta función tiene una sola responsabilidad, que es hablar con la red.
    """
    cliente = _obtener_cliente()
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURA,
        system=instrucciones,
        messages=[{"role": "user", "content": contenido}],
    )

    texto = "".join(
        bloque.text for bloque in respuesta.content if getattr(bloque, "type", "") == "text"
    )
    uso = getattr(respuesta, "usage", None)
    return RespuestaModelo(
        texto=texto,
        tokens_entrada=getattr(uso, "input_tokens", 0) or 0,
        tokens_salida=getattr(uso, "output_tokens", 0) or 0,
    )
