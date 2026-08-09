"""Configuración del proyecto, leída del .env con validación de tipos."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anclado al ARCHIVO, no al directorio de trabajo. Con env_file=".env" a secas,
# cualquier proceso que arranque desde otra carpeta -- el worker desde
# apps/pipeline-canvas, un comando suelto -- no encuentra el .env y lee los
# valores por defecto. El sintoma es un 401 de Canvas o una URL vacia, que no
# se parecen en nada a un problema de rutas.
RAIZ = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Base de datos ───
    database_url: str = "postgresql+psycopg://ediloja:ediloja_local@localhost:5432/ediloja"
    redis_url: str = "redis://localhost:6379/0"

    # ─── Seguridad ───
    jwt_secret: str = "cambiame"
    jwt_algorithm: str = "HS256"
    jwt_expira_minutos: int = 480

    # ─── Canvas ───
    canvas_url: str = ""
    canvas_token: str = ""
    canvas_account_id: int = 1

    # ─── IA ───
    anthropic_api_key: str = ""

    # ─── Rutas ───
    ruta_almacen: str = "./almacen"


settings = Settings()
