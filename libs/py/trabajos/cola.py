"""Configuración de la cola de trabajos.

El agente tarda minutos: ocho llamadas a un modelo, con reintentos. Eso no
cabe en una petición HTTP. El navegador cortaría, el proxy cortaría, y un
reintento del usuario dispararía una segunda generación en paralelo pagando
tokens dos veces.

Así que la API encola y devuelve 202 con un identificador, y el frontend
pregunta por el estado.
"""

from __future__ import annotations

import os

from redis import Redis
from rq import Queue

NOMBRE_COLA = "generacion"

# Media hora: ocho semanas con reintentos, con holgura. Si un trabajo supera
# esto, algo va mal y es mejor que muera a que se quede colgado ocupando un
# worker para siempre.
TIEMPO_MAXIMO = 1800

# El resultado se conserva un día para poder consultarlo tras terminar.
TTL_RESULTADO = 86400


def conexion() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))


def cola(*, sincrona: bool = False) -> Queue:
    """Devuelve la cola.

    `sincrona=True` ejecuta el trabajo en el momento, sin worker. Es lo que
    usan las pruebas: permite probar la tarea entera sin levantar Redis ni un
    proceso aparte.
    """
    return Queue(
        NOMBRE_COLA,
        connection=conexion(),
        is_async=not sincrona,
        default_timeout=TIEMPO_MAXIMO,
        result_ttl=TTL_RESULTADO,
    )
