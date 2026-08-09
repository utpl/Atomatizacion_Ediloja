"""Modelos del dominio: catálogo académico, guías, solicitudes y revisión."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.py.db.session import Base


class Facultad(Base):
    __tablename__ = "facultades"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))


class Guia(Base):
    """Una guía didáctica de una asignatura en un periodo académico."""

    __tablename__ = "guias"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_banner: Mapped[str] = mapped_column(String(30), index=True)
    codigo_componente: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nombre_asignatura: Mapped[str] = mapped_column(String(300))
    periodo: Mapped[str] = mapped_column(String(20), index=True)
    total_semanas: Mapped[int] = mapped_column(Integer, default=8)

    facultad_id: Mapped[int | None] = mapped_column(ForeignKey("facultades.id"), nullable=True)

    # El docente propietario. Define qué guías ve en su bandeja.
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)

    # borrador | en_revision | cambios_solicitados | aprobada | publicada
    estado: Mapped[str] = mapped_column(String(40), default="borrador", index=True)

    # Curso de Canvas donde se publica. Lo elige el OPERADOR al publicar, no
    # el docente: puede cambiar entre pruebas y producción, y una guía puede
    # publicarse en varios cursos a lo largo del tiempo.
    canvas_curso_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canvas_url: Mapped[str | None] = mapped_column(String(200), nullable=True)

    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    versiones: Mapped[list["VersionGuia"]] = relationship(
        back_populates="guia", cascade="all, delete-orphan"
    )
    solicitudes: Mapped[list[SolicitudGeneracion]] = relationship(
        back_populates="guia", cascade="all, delete-orphan"
    )
    asignaciones: Mapped[list[AsignacionRevision]] = relationship(
        back_populates="guia", cascade="all, delete-orphan", lazy="selectin"
    )


class SolicitudGeneracion(Base):
    """Lo que el docente pide al agente. Es la ENTRADA del sistema."""

    __tablename__ = "solicitudes_generacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    guia_id: Mapped[int] = mapped_column(ForeignKey("guias.id", ondelete="CASCADE"), index=True)
    solicitada_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)

    # Los requerimientos tal como los rellenó el docente.
    # JSONB porque la forma del formulario va a evolucionar.
    requerimientos: Mapped[dict] = mapped_column(JSONB)

    # "guia_completa" | "pagina"
    alcance: Mapped[str] = mapped_column(String(20), default="guia_completa")
    pagina_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # borrador | pendiente | ejecutando | completada | fallida | cancelada
    #
    # "borrador" = el docente guardó los requerimientos pero aún no ha pulsado
    # Generar. No está encolada y el worker nunca la ve. Existe para que pueda
    # revisar los datos, cerrar la pestaña y volver sin perderlos.
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    progreso: Mapped[int] = mapped_column(Integer, default=0)

    intentos: Mapped[int] = mapped_column(Integer, default=0)
    mensaje_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Trazabilidad del agente
    modelo_usado: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version_prompt: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tokens_entrada: Mapped[int | None] = mapped_column(nullable=True)
    tokens_salida: Mapped[int | None] = mapped_column(nullable=True)

    encolada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    iniciada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    guia: Mapped[Guia] = relationship(back_populates="solicitudes")


class CuotaPagina(Base):
    """Contador de regeneraciones por semana. Tres por defecto."""

    __tablename__ = "cuotas_pagina"
    __table_args__ = (UniqueConstraint("guia_id", "pagina_id", name="uq_cuota_guia_pagina"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guia_id: Mapped[int] = mapped_column(ForeignKey("guias.id", ondelete="CASCADE"), index=True)
    pagina_id: Mapped[str] = mapped_column(String(50))

    usadas: Mapped[int] = mapped_column(Integer, default=0)
    maximas: Mapped[int] = mapped_column(Integer, default=3)

    ampliada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    ampliada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_ampliacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def disponibles(self) -> int:
        return max(0, self.maximas - self.usadas)


class AsignacionRevision(Base):
    """A qué revisor le toca esta guía y en qué etapa."""

    __tablename__ = "asignaciones_revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    guia_id: Mapped[int] = mapped_column(ForeignKey("guias.id", ondelete="CASCADE"), index=True)
    revisor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)

    # revision_di | qa | operacion
    etapa: Mapped[str] = mapped_column(String(40))
    # pendiente | aprobada | cambios_solicitados
    estado: Mapped[str] = mapped_column(String(30), default="pendiente")

    asignada_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    asignada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resuelta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)

    guia: Mapped[Guia] = relationship(back_populates="asignaciones")


class RegistroAuditoria(Base):
    """Quién hizo qué y cuándo. No se borra nunca."""

    __tablename__ = "registro_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, index=True
    )
    accion: Mapped[str] = mapped_column(String(100), index=True)
    entidad: Mapped[str] = mapped_column(String(50))
    entidad_id: Mapped[int | None] = mapped_column(nullable=True)
    detalle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
