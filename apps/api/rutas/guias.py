"""Rutas de guías, con alcance por rol."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from libs.py.auth.alcance import guias_visibles, puede_ver_guia
from libs.py.auth.dependencias import exigir_roles, usuario_actual
from libs.py.db.modelos_auth import Usuario
from libs.py.db.modelos_dominio import Guia
from libs.py.db.session import obtener_sesion

router = APIRouter(prefix="/guias", tags=["guías"])


class GuiaPublica(BaseModel):
    id: int
    codigo_banner: str
    nombre_asignatura: str
    periodo: str
    total_semanas: int
    estado: str

    model_config = {"from_attributes": True}


class GuiaNueva(BaseModel):
    codigo_banner: str
    nombre_asignatura: str
    periodo: str
    total_semanas: int = 8


@router.get("", response_model=list[GuiaPublica])
def listar(
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> list[Guia]:
    """Lista las guías que este usuario puede ver, según su rol."""
    return list(sesion.scalars(guias_visibles(usuario)).all())


@router.post("", response_model=GuiaPublica, status_code=status.HTTP_201_CREATED)
def crear(
    datos: GuiaNueva,
    usuario: Usuario = Depends(exigir_roles("docente")),
    sesion: Session = Depends(obtener_sesion),
) -> Guia:
    guia = Guia(
        codigo_banner=datos.codigo_banner,
        nombre_asignatura=datos.nombre_asignatura,
        periodo=datos.periodo,
        total_semanas=datos.total_semanas,
        autor_id=usuario.id,
    )
    sesion.add(guia)
    sesion.commit()
    sesion.refresh(guia)
    return guia


@router.get("/{guia_id}", response_model=GuiaPublica)
def detalle(
    guia_id: int,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> Guia:
    guia = sesion.get(Guia, guia_id)
    # 404 y no 403 cuando existe pero no le corresponde: un 403 confirmaría
    # que esa guía existe, y eso ya es información.
    if guia is None or not puede_ver_guia(usuario, guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guía no encontrada")
    return guia


@router.post("/{guia_id}/aprobar", response_model=GuiaPublica)
def aprobar(
    guia_id: int,
    usuario: Usuario = Depends(exigir_roles("qa", "coordinador")),
    sesion: Session = Depends(obtener_sesion),
) -> Guia:
    guia = sesion.get(Guia, guia_id)
    if guia is None or not puede_ver_guia(usuario, guia):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guía no encontrada")
    guia.estado = "aprobada"
    sesion.commit()
    sesion.refresh(guia)
    return guia
