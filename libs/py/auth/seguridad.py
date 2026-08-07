"""Cifrado de contraseñas y tokens de sesión."""

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from libs.py.config.settings import settings

# Argon2: ganó la competición de hashing de contraseñas.
# Para contraseñas queremos un algoritmo DELIBERADAMENTE LENTO: a ti no te
# molesta que tarde 0,1 s, a un atacante probando millones le arruina el ataque.
_contexto = CryptContext(schemes=["argon2"], deprecated="auto")


def cifrar_contrasena(contrasena: str) -> str:
    """Convierte una contraseña en un hash irreversible, con sal aleatoria."""
    return _contexto.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    """Comprueba si una contraseña corresponde a un hash."""
    try:
        return _contexto.verify(contrasena, hash_guardado)
    except ValueError:
        return False


def crear_token(usuario_id: int, roles: list[str]) -> str:
    """Genera un JWT firmado con la identidad y los roles del usuario."""
    ahora = datetime.now(UTC)
    carga = {
        "sub": str(usuario_id),
        "roles": roles,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.jwt_expira_minutos),
    }
    return jwt.encode(carga, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def leer_token(token: str) -> dict:
    """Verifica firma y caducidad. Lanza excepción si no es válido."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
