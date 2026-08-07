"""Modelos de contenido: versiones de la guía, sus recursos y las ediciones.

El `curso.json` vive aquí, en una columna JSONB, no solo en disco. Con un
editor de por medio hace falta leer y modificar fragmentos con transacciones,
y un archivo suelto no lo permite.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class VersionGuia(Base):
    """Una versión del contenido de una guía.

    Cada generación crea una versión nueva. Las ediciones del docente
    modifican la versión actual y quedan registradas en `ediciones_bloque`.
    Al enviar a revisión, la versión se congela.
    """

    __tablename__ = "versiones_guia"
    __table_args__ = (UniqueConstraint("guia_id", "numero", name="uq_version_guia_numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guia_id: Mapped[int] = mapped_column(ForeignKey("guias.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)

    # agente_ia | migrado_canvas | edicion_docente
    origen: Mapped[str] = mapped_column(String(30), index=True)

    solicitud_id: Mapped[int | None] = mapped_column(
        ForeignKey("solicitudes_generacion.id"), nullable=True
    )

    # EL CONTENIDO. Consultable, indexable, transaccional.
    contenido: Mapped[dict] = mapped_column(JSONB)
    version_esquema: Mapped[str] = mapped_column(String(20), default="1.0.0")
    sha256: Mapped[str] = mapped_column(String(64))

    # Copia de archivo del paquete original del agente
    ruta_paquete: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Resultado de la validación
    semaforo: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    alertas: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Una versión congelada está en revisión y no admite cambios
    congelada: Mapped[bool] = mapped_column(Boolean, default=False)
    es_actual: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    creada_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    guia: Mapped["Guia"] = relationship(back_populates="versiones")  # noqa: F821
    recursos: Mapped[list[RecursoVersion]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    ediciones: Mapped[list[EdicionBloque]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class RecursoVersion(Base):
    """Cada imagen, diagrama o HTML que acompaña a una versión.

    Los binarios viven en disco o en S3; aquí van los metadatos. Los bloques
    del `curso.json` los referencian por el campo `referencia`.
    """

    __tablename__ = "recursos_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("versiones_guia.id", ondelete="CASCADE"), index=True
    )

    # imagen | diagrama | autoevaluacion_html | anexo
    tipo: Mapped[str] = mapped_column(String(30), index=True)

    # Cómo lo referencia el curso.json, p. ej. "figura_03"
    referencia: Mapped[str] = mapped_column(String(200), index=True)

    nombre_archivo: Mapped[str] = mapped_column(String(255))
    ruta: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(100))
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)

    ancho: Mapped[int | None] = mapped_column(nullable=True)
    alto: Mapped[int | None] = mapped_column(nullable=True)

    # Accesibilidad: obligatorio en figuras de contenido
    texto_alternativo: Mapped[str | None] = mapped_column(Text, nullable=True)
    es_decorativa: Mapped[bool] = mapped_column(Boolean, default=False)

    # Trazabilidad: None | gemini | claude | svg_generado
    generado_por: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Se rellenan al publicar en Canvas
    url_canvas: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_id_canvas: Mapped[int | None] = mapped_column(nullable=True)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    version: Mapped[VersionGuia] = relationship(back_populates="recursos")


class EdicionBloque(Base):
    """Cada operación del docente sobre el contenido.

    Guardar `antes` y `despues` da tres cosas sin trabajo extra: deshacer,
    auditoría legible, y la métrica más útil del sistema — cuánto edita el
    docente lo que generó el agente.
    """

    __tablename__ = "ediciones_bloque"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("versiones_guia.id", ondelete="CASCADE"), index=True
    )

    # actualizar_bloque | eliminar_bloque | insertar_bloque | mover_bloque
    # insertar_unidad | actualizar_unidad | eliminar_unidad | reasignar_pagina
    operacion: Mapped[str] = mapped_column(String(40), index=True)

    bloque_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    pagina_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    antes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    despues: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    realizada_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    realizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    version: Mapped[VersionGuia] = relationship(back_populates="ediciones")
