"""Configuración del proyecto, leída del .env con validación de tipos."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
