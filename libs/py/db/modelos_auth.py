"""Modelos de identidad: usuarios, roles y ámbitos de permiso."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.py.db.session import Base


class Usuario(Base):
    """Una persona con acceso al sistema.

    La contraseña NUNCA se guarda en claro: solo su hash Argon2.
    Los usuarios no se borran, se desactivan (`activo = False`), para no
    romper el historial de quién hizo qué.
    """

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    correo: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nombre_completo: Mapped[str] = mapped_column(String(255))
    hash_contrasena: Mapped[str] = mapped_column(String(255))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list[UsuarioRol]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="selectin"
    )

    def codigos_de_rol(self) -> set[str]:
        return {ur.rol.codigo for ur in self.roles}

    def tiene_rol(self, *codigos: str) -> bool:
        return bool(self.codigos_de_rol() & set(codigos))


class Rol(Base):
    """Catálogo de roles del sistema.

    Códigos previstos: docente, revisor_di, qa, operador, coordinador, admin.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str] = mapped_column(String(500), default="")


class UsuarioRol(Base):
    """Asigna un rol a un usuario, opcionalmente limitado a un ámbito.

    Es una tabla intermedia (muchos a muchos) y no una columna `rol` en
    `usuarios` por dos motivos: una persona puede tener varios roles, y cada
    rol puede estar limitado a una facultad o carrera concreta.
    """

    __tablename__ = "usuarios_roles"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            "rol_id",
            "ambito_tipo",
            "ambito_id",
            name="uq_usuario_rol_ambito",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)

    # "global" | "facultad" | "carrera"
    ambito_tipo: Mapped[str] = mapped_column(String(20), default="global")
    ambito_id: Mapped[int | None] = mapped_column(nullable=True)

    usuario: Mapped[Usuario] = relationship(back_populates="roles")
    rol: Mapped[Rol] = relationship(lazy="selectin")
