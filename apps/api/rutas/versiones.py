"""Rutas de versiones de guía: leer el contenido, congelar y devolver.

Estas rutas son la puerta del editor. La edición en sí vive en
`apps/api/rutas/edicion.py`; aquí está todo lo demás que el editor necesita
para funcionar: cargar el `curso.json`, saber cuál es la versión vigente, y
mover la versión entre "se puede tocar" y "está en revisión".
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from libs.py.auth.alcance import puede_ver_guia
from libs.py.auth.dependencias import exigir_roles, usuario_actual
from libs.py.db.modelos_auth import Usuario
from libs.py.db.modelos_contenido import VersionGuia
from libs.py.db.modelos_dominio import Guia
from libs.py.db.session import obtener_sesion

router = APIRouter(prefix="/api/versiones", tags=["versiones"])


class VersionResumen(BaseModel):
    """Ficha de una versión, sin el contenido.

    Sin el `curso.json` a propósito: listar diez versiones con su contenido
    serían varios megas de respuesta para pintar una lista de fechas.
    """

    id: int
    guia_id: int
    numero: int
    origen: str
    semaforo: str | None
    congelada: bool
    es_actual: bool
    creada_en: datetime

    model_config = {"from_attributes": True}


class VersionCompleta(BaseModel):
    """La versión con su contenido. Esto es lo que carga el editor."""

    id: int
    guia_id: int
    numero: int
    origen: str
    version_esquema: str
    sha256: str
    semaforo: str | None
    alertas: list | None
    congelada: bool
    es_actual: bool
    creada_en: datetime
    contenido: dict

    model_config = {"from_attributes": True}


def _version_visible(version_id: int, usuario: Usuario, sesion: Session) -> VersionGuia:
    """Trae la versión comprobando el alcance, o lanza 404.

    404 y no 403 cuando existe pero no le corresponde: un 403 confirmaría que
    esa versión existe. Mismo criterio que en /guias.
    """
    version = sesion.get(VersionGuia, version_id)
    if version is None or not puede_ver_guia(usuario, version.guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versión no encontrada")
    return version


@router.get("/{version_id}", response_model=VersionCompleta)
def detalle(
    version_id: int,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> VersionGuia:
    """Devuelve el `curso.json` completo. Es lo que abre el editor.

    El `sha256` que va aquí es el que el frontend debe devolver al editar: así
    el servidor detecta si alguien tocó la versión por en medio.
    """
    return _version_visible(version_id, usuario, sesion)


@router.post("/{version_id}/enviar-revision", response_model=VersionResumen)
def enviar_a_revision(
    version_id: int,
    usuario: Usuario = Depends(exigir_roles("docente")),
    sesion: Session = Depends(obtener_sesion),
) -> VersionGuia:
    """Congela la versión: a partir de aquí la edición devuelve 409.

    Congelar y no copiar es deliberado: la versión que revisa el revisor tiene
    que ser exactamente la que aprobó el docente. Si el docente pudiera seguir
    tocándola, el revisor estaría revisando un documento que cambia bajo sus
    pies.
    """
    version = _version_visible(version_id, usuario, sesion)

    if version.congelada:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La versión ya está en revisión."
        )

    # Un rojo son errores de esquema o de reglas duras. Dejar pasar eso
    # significa que el revisor gasta su tiempo en fallos que detecta una
    # máquina. Los avisos (amarillo) sí pasan: son criterio editorial.
    if version.semaforo == "rojo":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La guía tiene errores que hay que corregir antes de enviarla a "
            "revisión. Revisa el semáforo.",
        )

    version.congelada = True
    version.guia.estado = "en_revision"
    sesion.commit()
    sesion.refresh(version)
    return version


@router.post("/{version_id}/devolver", response_model=VersionResumen)
def devolver_a_edicion(
    version_id: int,
    usuario: Usuario = Depends(exigir_roles("revisor_di", "qa", "coordinador")),
    sesion: Session = Depends(obtener_sesion),
) -> VersionGuia:
    """Descongela: el revisor devuelve la guía al docente para que corrija.

    Solo el revisor puede hacerlo. Si pudiera el docente, la congelación no
    serviría de nada: bastaría con descongelar para saltársela.
    """
    version = _version_visible(version_id, usuario, sesion)

    if not version.congelada:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La versión no está en revisión."
        )

    version.congelada = False
    version.guia.estado = "en_edicion"
    sesion.commit()
    sesion.refresh(version)
    return version


router_guias = APIRouter(prefix="/api/guias", tags=["versiones"])


@router_guias.get("/{guia_id}/versiones", response_model=list[VersionResumen])
def listar_de_guia(
    guia_id: int,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> list[VersionGuia]:
    """Historial de versiones de una guía, de la más reciente a la más antigua."""
    guia = sesion.get(Guia, guia_id)
    if guia is None or not puede_ver_guia(usuario, guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guía no encontrada")

    consulta = (
        select(VersionGuia)
        .where(VersionGuia.guia_id == guia_id)
        .order_by(VersionGuia.numero.desc())
    )
    return list(sesion.scalars(consulta).all())


@router_guias.get("/{guia_id}/version-actual", response_model=VersionCompleta)
def version_actual(
    guia_id: int,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> VersionGuia:
    """La versión vigente de una guía, con contenido.

    Existe para que el editor pueda abrir una guía sin saberse el id de la
    versión: el frontend navega por guías, no por versiones.
    """
    guia = sesion.get(Guia, guia_id)
    if guia is None or not puede_ver_guia(usuario, guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guía no encontrada")

    consulta = select(VersionGuia).where(
        VersionGuia.guia_id == guia_id, VersionGuia.es_actual.is_(True)
    )
    version = sesion.scalars(consulta).first()
    if version is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "La guía todavía no tiene contenido generado.",
        )
    return version
