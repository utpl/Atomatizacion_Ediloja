"""Endpoints de generación: encolar y consultar estado.

Patrón 202 + sondeo, que es lo acordado con el frontend:

    POST /api/guias/{id}/generar   → 202 + solicitud_id
    GET  /api/trabajos/{id}        → estado, progreso, resultado

No se usa SSE. Con htmx el sondeo es una línea (`hx-trigger="every 2s"`) y no
obliga al servidor a mantener conexiones abiertas que cualquier proxy corta.
Para un proceso de minutos, ahorrar dos segundos de latencia no compensa.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from libs.py.auth.alcance import puede_ver_guia
from libs.py.auth.dependencias import usuario_actual
from libs.py.db.modelos_auth import Usuario
from libs.py.db.modelos_dominio import CuotaPagina, Guia, SolicitudGeneracion
from libs.py.db.session import obtener_sesion
from libs.py.trabajos import tareas
from libs.py.trabajos.cola import cola

router = APIRouter(prefix="/api/guias", tags=["generación"])
router_trabajos = APIRouter(prefix="/api/trabajos", tags=["generación"])


class PeticionGenerar(BaseModel):
    requerimientos: dict = Field(
        default_factory=dict,
        description="Datos de entrada del agente: unidades, plan, bibliografía.",
    )


class PeticionRegenerar(BaseModel):
    semana: int = Field(ge=1)
    pagina_id: str
    bibliografia: list[str] | None = None


class TrabajoPublico(BaseModel):
    id: int
    guia_id: int
    alcance: str
    pagina_id: str | None
    estado: str
    progreso: int
    intentos: int
    mensaje_error: str | None
    modelo_usado: str | None
    tokens_entrada: int | None
    tokens_salida: int | None
    encolada_en: datetime
    terminada_en: datetime | None

    model_config = {"from_attributes": True}


def _guia_visible(guia_id: int, usuario: Usuario, sesion: Session) -> Guia:
    guia = sesion.get(Guia, guia_id)
    if guia is None or not puede_ver_guia(usuario, guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guía no encontrada")
    return guia


@router.post(
    "/{guia_id}/generar",
    response_model=TrabajoPublico,
    status_code=status.HTTP_202_ACCEPTED,
)
def generar(
    guia_id: int,
    peticion: PeticionGenerar,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> SolicitudGeneracion:
    """Encola la generación de la guía completa. Devuelve 202, no espera."""
    guia = _guia_visible(guia_id, usuario, sesion)

    # Una sola generación viva por guía. Sin esto, dos clics seguidos en el
    # botón lanzan dos generaciones en paralelo y se paga el doble de tokens.
    en_curso = (
        sesion.query(SolicitudGeneracion)
        .filter(
            SolicitudGeneracion.guia_id == guia_id,
            SolicitudGeneracion.estado.in_(("pendiente", "ejecutando")),
        )
        .first()
    )
    if en_curso is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ya hay una generación en curso para esta guía (trabajo {en_curso.id}).",
        )

    solicitud = SolicitudGeneracion(
        guia_id=guia.id,
        solicitada_por=usuario.id,
        requerimientos=peticion.requerimientos,
        alcance="guia_completa",
        estado="pendiente",
    )
    sesion.add(solicitud)
    sesion.commit()
    sesion.refresh(solicitud)

    cola().enqueue(tareas.generar_guia_completa, solicitud.id)
    return solicitud


@router.post(
    "/{guia_id}/regenerar",
    response_model=TrabajoPublico,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerar(
    guia_id: int,
    peticion: PeticionRegenerar,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> SolicitudGeneracion:
    """Encola la regeneración de una semana. Comprueba la cuota antes."""
    guia = _guia_visible(guia_id, usuario, sesion)

    cuota = (
        sesion.query(CuotaPagina)
        .filter_by(guia_id=guia.id, pagina_id=peticion.pagina_id)
        .first()
    )
    if cuota is not None and cuota.disponibles <= 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Se agotaron las {cuota.maximas} regeneraciones de esta semana. "
            "Un coordinador puede ampliarlas.",
        )

    solicitud = SolicitudGeneracion(
        guia_id=guia.id,
        solicitada_por=usuario.id,
        requerimientos={
            "semana": peticion.semana,
            "bibliografia": peticion.bibliografia,
        },
        alcance="pagina",
        pagina_id=peticion.pagina_id,
        estado="pendiente",
    )
    sesion.add(solicitud)
    sesion.commit()
    sesion.refresh(solicitud)

    cola().enqueue(tareas.regenerar_una_pagina, solicitud.id)
    return solicitud


@router_trabajos.get("/{trabajo_id}", response_model=TrabajoPublico)
def estado(
    trabajo_id: int,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> SolicitudGeneracion:
    """Estado de un trabajo. Es lo que sondea el frontend cada dos segundos."""
    solicitud = sesion.get(SolicitudGeneracion, trabajo_id)
    if solicitud is None or not puede_ver_guia(usuario, solicitud.guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trabajo no encontrado")
    return solicitud
