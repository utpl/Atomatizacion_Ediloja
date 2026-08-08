"""Dependencias de FastAPI para identificar y autorizar al usuario."""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
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


# ---------------------------------------------------------------------------
# Variante para las vistas HTML
# ---------------------------------------------------------------------------
# El navegador, al pinchar un enlace, no manda la cabecera Authorization:
# manda cookies. usuario_actual() corta con 401 antes de llegar aquí porque
# OAuth2PasswordBearer solo mira esa cabecera.
#
# Esta versión mira en las dos fuentes, con la cabecera por delante. Así la
# API sigue funcionando igual para Postman, los tests y el agente de la UTPL,
# y además funciona el navegador. No se modifica nada de lo anterior.
#
# La cookie se emite HttpOnly (ver rutas/vistas.py): JavaScript no puede
# leerla. Importa en este proyecto, que publica HTML generado por IA en
# Canvas: si algún día se cuela un script, no podrá robar sesiones.

NOMBRE_COOKIE = "ediloja_sesion"


def token_de_peticion(request: Request) -> str | None:
    """Saca el token de la cabecera o, en su defecto, de la cookie."""
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip()
    return request.cookies.get(NOMBRE_COOKIE)


def usuario_web_opcional(
    request: Request,
    sesion: Session = Depends(obtener_sesion),
) -> Usuario | None:
    """Devuelve el usuario, o None si no hay sesión. NO lanza 401.

    Las vistas HTML no deben devolver 401: deben redirigir al login. Por eso
    esta versión no lanza y la ruta decide qué hacer.
    """
    token = token_de_peticion(request)
    if not token:
        return None
    try:
        carga = leer_token(token)
        usuario_id = int(carga["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    usuario = sesion.get(Usuario, usuario_id)
    return usuario if usuario is not None and usuario.activo else None
