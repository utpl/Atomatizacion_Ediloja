"""El contrato de la edición: qué puede pedir el frontend y qué recibe.

Esto es lo que el frontend lee para saber qué mandar. Al ser Pydantic, aparece
solo en `/docs` de FastAPI, así que el contrato se documenta y se valida en el
mismo sitio y no pueden desincronizarse.

**Idea central: operaciones semánticas, no parches de JSON.**

El frontend no manda "cambia la clave `texto` del objeto en `paginas[2].bloques[5]`".
Manda "actualiza el bloque b7f3a9c2". Tres motivos:

1. El docente ve semanas y párrafos, nunca llaves. La API debe hablar su idioma.
2. Un índice se invalida en cuanto otra operación inserta algo antes. Un id, no.
3. Una operación con nombre se puede auditar y deshacer. Un parche por índice,
   no: no sabes qué significaba.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Operaciones sobre bloques
# ---------------------------------------------------------------------------


class ActualizarBloque(BaseModel):
    """Cambia campos de un bloque que ya existe."""

    operacion: Literal["actualizar_bloque"] = "actualizar_bloque"
    bloque_id: str
    campos: dict[str, Any] = Field(
        description="Solo los campos que cambian. Los demás se conservan."
    )


class EliminarBloque(BaseModel):
    """Borra un bloque. Si es contenedor, se lleva sus hijos por delante."""

    operacion: Literal["eliminar_bloque"] = "eliminar_bloque"
    bloque_id: str


class InsertarBloque(BaseModel):
    """Mete un bloque nuevo en una página, opcionalmente dentro de un contenedor."""

    operacion: Literal["insertar_bloque"] = "insertar_bloque"
    pagina_id: str
    indice: int = Field(ge=0, description="Posición. 0 = al principio.")
    bloque: dict[str, Any]
    dentro_de: str | None = Field(
        default=None,
        description="Id de una caja o focalizador. Si va, el bloque entra dentro.",
    )


class MoverBloque(BaseModel):
    """Cambia un bloque de sitio, dentro de la página o a otra."""

    operacion: Literal["mover_bloque"] = "mover_bloque"
    bloque_id: str
    pagina_id: str
    indice: int = Field(ge=0)
    dentro_de: str | None = None


# ---------------------------------------------------------------------------
# Operaciones estructurales
#
# Existen porque el docente PUEDE añadir temas nuevos. Si solo pudiera tocar
# bloques, estaría atado a la estructura que decidió la IA, y eso convierte al
# docente en corrector en vez de autor.
# ---------------------------------------------------------------------------


class InsertarPagina(BaseModel):
    operacion: Literal["insertar_pagina"] = "insertar_pagina"
    indice: int = Field(ge=0)
    titulo: str
    semana: int | None = None
    unidad_id: str | None = None


class EliminarPagina(BaseModel):
    operacion: Literal["eliminar_pagina"] = "eliminar_pagina"
    pagina_id: str


class MoverPagina(BaseModel):
    operacion: Literal["mover_pagina"] = "mover_pagina"
    pagina_id: str
    indice: int = Field(ge=0)


class ActualizarPagina(BaseModel):
    operacion: Literal["actualizar_pagina"] = "actualizar_pagina"
    pagina_id: str
    campos: dict[str, Any]


Operacion = Annotated[
    ActualizarBloque | EliminarBloque | InsertarBloque | MoverBloque | InsertarPagina | EliminarPagina | MoverPagina | ActualizarPagina,
    Field(discriminator="operacion"),
]


# ---------------------------------------------------------------------------
# Petición y respuesta
# ---------------------------------------------------------------------------


class PeticionEdicion(BaseModel):
    """Un lote de operaciones que se aplican en una sola transacción.

    Va en lote a propósito: mover un bloque de una caja a otra son dos
    operaciones y no puede quedarse a medias. O entran todas o no entra ninguna.
    """

    operaciones: list[Operacion] = Field(min_length=1, max_length=50)
    sha256: str | None = Field(
        default=None,
        description=(
            "Huella del contenido que el cliente cree tener. Si no coincide "
            "con la del servidor, se rechaza con 409: alguien editó por en "
            "medio. Se aprovecha la columna sha256 que ya existe en "
            "versiones_guia, así que no hace falta migración."
        ),
    )


class RegistroEdicion(BaseModel):
    """Lo que se guarda en `ediciones_bloque`: sirve para deshacer y auditar."""

    operacion: str
    bloque_id: str | None = None
    pagina_id: str | None = None
    antes: dict[str, Any] | None = None
    despues: dict[str, Any] | None = None


class RespuestaEdicion(BaseModel):
    """Lo que recibe el frontend tras editar."""

    sha256: str
    semaforo: str
    alertas: list[Any] = []
    estadisticas: dict[str, Any] = {}
    ediciones: list[RegistroEdicion] = []
    curso: dict[str, Any] | None = Field(
        default=None,
        description="El curso.json completo ya actualizado. Puede omitirse si pesa.",
    )
