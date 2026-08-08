"""Entidad ODS — Objetivos de Desarrollo Sostenible de la ONU."""
from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class ODS(db.Model):
    """Objetivo de Desarrollo Sostenible (ONU, Agenda 2030).

    Catálogo precargado y no modificable por el usuario.
    """

    __tablename__ = "ods"

    id_ods: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ODS {self.numero}: {self.nombre!r}>"
