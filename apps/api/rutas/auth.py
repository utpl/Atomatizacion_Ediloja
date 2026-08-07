"""Rutas de autenticación."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from libs.py.auth.dependencias import usuario_actual
from libs.py.auth.seguridad import crear_token, verificar_contrasena
from libs.py.db.modelos_auth import Usuario
from libs.py.db.session import obtener_sesion

router = APIRouter(prefix="/auth", tags=["autenticación"])


class RespuestaToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioPublico(BaseModel):
    id: int
    correo: str
    nombre_completo: str
    roles: list[str]


@router.post("/login", response_model=RespuestaToken)
def login(
    datos: OAuth2PasswordRequestForm = Depends(),
    sesion: Session = Depends(obtener_sesion),
) -> RespuestaToken:
    usuario = sesion.scalar(select(Usuario).where(Usuario.correo == datos.username.lower()))

    # Mensaje deliberadamente ambiguo: decir "ese correo no existe" regalaría
    # a un atacante la lista de correos válidos de la institución.
    if usuario is None or not verificar_contrasena(datos.password, usuario.hash_contrasena):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )
    if not usuario.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta desactivada")

    usuario.ultimo_acceso = datetime.now(UTC)
    sesion.commit()

    return RespuestaToken(access_token=crear_token(usuario.id, sorted(usuario.codigos_de_rol())))


@router.get("/yo", response_model=UsuarioPublico)
def quien_soy(usuario: Usuario = Depends(usuario_actual)) -> UsuarioPublico:
    return UsuarioPublico(
        id=usuario.id,
        correo=usuario.correo,
        nombre_completo=usuario.nombre_completo,
        roles=sorted(usuario.codigos_de_rol()),
    )
