"""Entidad Rol — perfiles de usuario y permisos asociados."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    from .usuario import Usuario


class Rol(db.Model):
    """Rol del usuario en el sistema (docente, administrador, ...)."""

    __tablename__ = "rol"

    # Constantes de roles del sistema
    DOCENTE = "docente"
    ADMINISTRADOR = "administrador"

    id_rol: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    permisos: Mapped[list | dict] = mapped_column(
        JSONB, nullable=False, default=list
    )

    usuarios: Mapped[list["Usuario"]] = relationship(
        back_populates="rol", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rol id={self.id_rol} nombre={self.nombre!r}>"
