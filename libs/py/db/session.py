"""Conexión a la base de datos y gestión de sesiones."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from libs.py.config.settings import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # comprueba la conexión antes de usarla
    echo=False,  # ponlo en True mientras aprendes: verás el SQL generado
)

SesionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Clase base de todos los modelos."""


def obtener_sesion() -> Generator[Session]:
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar."""
    sesion = SesionLocal()
    try:
        yield sesion
    finally:
        sesion.close()
