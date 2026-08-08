"""Único punto del sistema que habla con el proveedor del modelo.

Todo lo demás del agente llama a `llamar_modelo()` y no sabe (ni debe saber) si
detrás hay Anthropic, OpenAI, Gemini o un modelo alojado en la UTPL.

**Este es el archivo a cambiar si el proveedor no es Claude.** El resto del
agente no se toca: `generador.py`, `ensamblado.py` y `contexto.py` no importan
la librería del proveedor por ninguna parte.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Se carga aqui y no solo en main.py: el worker de RQ es otro proceso y no
# pasa por el arranque de la API. Sin esto lee los valores por defecto del
# codigo en vez de los del .env, y el sintoma es desconcertante -- la API
# funciona bien y el worker se comporta distinto con la misma configuracion.
load_dotenv()

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

# ---------------------------------------------------------------------------
# Modo simulado
# ---------------------------------------------------------------------------
# Con AGENTE_SIMULADO=1 no se llama a ninguna API. Sirve para probar el flujo
# completo -- encolar, worker, progreso, ensamblado, validacion -- sin gastar
# tokens y sin depender de que la clave este configurada.
#
# Devuelve JSON con la forma canonica del curso.json, no texto: si devolviera
# prosa, el generador la rechazaria y no probariamos nada.



def _simulado(instrucciones: str, contenido: str) -> RespuestaModelo:
    if "estructura la planificacion" in instrucciones or "reparto por semanas" in instrucciones:
        total = 8
        for linea in contenido.splitlines():
            if "semanas:" in linea.lower():
                try:
                    total = int("".join(c for c in linea if c.isdigit()))
                except ValueError:
                    pass
                break
        mitad = max(1, total // 2)
        datos = {"unidades": [
            {"numero": 1, "titulo": "Unidad 1 (simulada)",
             "semana_inicio": 1, "semana_fin": mitad},
            {"numero": 2, "titulo": "Unidad 2 (simulada)",
             "semana_inicio": mitad + 1, "semana_fin": total},
        ]}
        return RespuestaModelo(texto=json.dumps(datos, ensure_ascii=False),
                               tokens_entrada=300, tokens_salida=120)

    semana = 1
    for linea in contenido.splitlines():
        if linea.lower().startswith("genera la semana"):
            try:
                semana = int(linea.split()[3])
            except (IndexError, ValueError):
                pass
            break

    pagina = {
        "titulo": f"Semana {semana}: contenidos",
        "bloques": [
            {"tipo": "encabezado", "nivel": 2, "texto": "Contextualizacion"},
            {"tipo": "parrafo",
             "texto": "Texto <strong>simulado</strong> de la semana "
                      f"{semana}. No se llamo a ningun modelo."},
            {"tipo": "focalizador", "focalizador": "recuerde",
             "bloques": [{"tipo": "parrafo", "texto": "Repase antes de continuar."}]},
            {"tipo": "lista", "ordenada": False,
             "items": [{"texto": "Primer punto"}, {"texto": "Segundo punto"}]},
        ],
    }

    # Si la semana cierra unidad, el modelo real incluye autoevaluacion de diez
    # preguntas (regla institucional 10). Sin esto el simulado siempre da
    # semaforo rojo y no sirve para probar el camino completo.
    if "cierra unidad" in contenido.lower() or "autoevaluacion" in contenido.lower():
        pagina["bloques"].append({
            "tipo": "autoevaluacion",
            "preguntas": [
                {"id": f"q{i}", "numero": i,
                 "enunciado": f"Pregunta {i} simulada sobre el contenido de la unidad",
                 "opciones": [{"letra": "a", "texto": "Opcion A"},
                              {"letra": "b", "texto": "Opcion B"},
                              {"letra": "c", "texto": "Opcion C"}],
                 "correcta": "a",
                 "retroalimentacion": "Retroalimentacion simulada."}
                for i in range(1, 11)
            ],
        })
    return RespuestaModelo(texto=json.dumps(pagina, ensure_ascii=False),
                           tokens_entrada=1200, tokens_salida=900)


if os.getenv("AGENTE_SIMULADO") == "1":
    _real = llamar_modelo

    def llamar_modelo(instrucciones: str, contenido: str) -> RespuestaModelo:  # noqa: F811
        return _simulado(instrucciones, contenido)
