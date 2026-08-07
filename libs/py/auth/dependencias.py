"""Dependencias de FastAPI para identificar y autorizar al usuario."""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from libs.py.auth.seguridad import leer_token
from libs.py.db.modelos_auth import Usuario
from libs.py.db.session import obtener_sesion

esquema_oauth = OAuth2PasswordBearer(tokenUrl="/auth/login")

# 401 = "no sé quién eres" (token ausente, caducado o inválido)
# 403 = "sé quién eres, pero no puedes hacer esto"
NO_AUTORIZADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales no válidas",
    headers={"WWW-Authenticate": "Bearer"},
)


def usuario_actual(
    token: str = Depends(esquema_oauth),
    sesion: Session = Depends(obtener_sesion),
) -> Usuario:
    """Identifica al usuario a partir del token. Lanza 401 si no es válido."""
    try:
        carga = leer_token(token)
        usuario_id = int(carga["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise NO_AUTORIZADO from exc

    usuario = sesion.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        raise NO_AUTORIZADO
    return usuario


def exigir_roles(*codigos: str) -> Callable:
    """Fábrica de dependencias: exige alguno de estos roles.

    Uso:  usuario: Usuario = Depends(exigir_roles("qa", "coordinador"))

    El rol "admin" siempre pasa, para no repetirlo en cada llamada.
    """

    def comprobar(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if not usuario.tiene_rol(*codigos, "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para esta operación",
            )
        return usuario

    return comprobar
