"""Entidades del currículo LOMLOE: Competencia, Criterio de Evaluación y Saber Básico.

Estas entidades constituyen el catálogo precargado a partir de la normativa
oficial. Los usuarios no las modifican, solo las referencian al construir sus
situaciones de aprendizaje.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    pass


class Competencia(db.Model):
    """Competencia LOMLOE (clave/transversal o específica de materia).

    ``cursos_aplicables`` enumera los cursos de ESO en los que la competencia
    es aplicable (p. ej. ``["1º ESO", "2º ESO", "3º ESO", "4º ESO"]`` para
    las competencias específicas que se desarrollan a lo largo de toda la
    etapa). ``descriptores`` contiene los códigos del perfil de salida
    asociados a la competencia (``["CCL3", "STEM2", ...]``).
    """

    __tablename__ = "competencia"
    # El índice era solo por materia, y se queda corto en cuanto conviven dos
    # comunidades: toda consulta real filtra por las dos cosas a la vez.
    __table_args__ = (
        Index("ix_competencia_comunidad_materia", "comunidad", "materia"),
    )

    PRINCIPAL = "principal"
    ESPECIFICA = "especifica"

    id_competencia: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Código canónico de `curriculo.comunidades`, no el nombre. Ver el
    #: docstring de ese módulo: el nombre es texto de interfaz y cambia; el
    #: código es una clave y no.
    comunidad: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Lengua en que publica el boletín del que salió esta fila. No es la
    #: preferencia de nadie: es una propiedad del documento oficial. El DOGC
    #: publica en catalán y el BOPV en euskera y castellano.
    idioma: Mapped[str] = mapped_column(String(5), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    materia: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cursos_aplicables: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    descriptores: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)

    criterios: Mapped[list["CriterioEvaluacion"]] = relationship(
        back_populates="competencia", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Competencia {self.codigo} {self.comunidad} ({self.tipo})>"


class CriterioEvaluacion(db.Model):
    """Criterio de evaluación de una competencia.

    El mismo ``codigo`` (p. ej. ``"1.1"``) puede aparecer en cursos distintos
    con descripciones diferentes — la Orden EFP/754/2022 desarrolla los
    criterios por curso individual para Lengua e Inglés.
    """

    __tablename__ = "criterio_evaluacion"
    __table_args__ = (
        Index("ix_criterio_comunidad_materia", "comunidad", "materia"),
    )

    id_criterio: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    comunidad: Mapped[str] = mapped_column(String(20), nullable=False)
    idioma: Mapped[str] = mapped_column(String(5), nullable=False)
    id_competencia: Mapped[int] = mapped_column(
        ForeignKey("competencia.id_competencia", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    materia: Mapped[str] = mapped_column(String(50), nullable=False)
    cursos_aplicables: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)

    competencia: Mapped["Competencia"] = relationship(back_populates="criterios")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Criterio {self.codigo} {self.comunidad}/{self.materia}/{self.cursos_aplicables}>"


class SaberBasico(db.Model):
    """Saber básico (contenido curricular) de una materia y conjunto de cursos.

    Modela un ÍTEM individual dentro de un bloque. ``codigo`` identifica el
    bloque y la posición dentro del bloque (``"A.1"``, ``"B.3"``); ``bloque``
    guarda el título del bloque (``"Comunicación"``).
    """

    __tablename__ = "saber_basico"
    __table_args__ = (
        Index("ix_saber_comunidad_materia", "comunidad", "materia"),
    )

    id_saber: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    comunidad: Mapped[str] = mapped_column(String(20), nullable=False)
    idioma: Mapped[str] = mapped_column(String(5), nullable=False)
    bloque: Mapped[str] = mapped_column(String(200), nullable=False)
    materia: Mapped[str] = mapped_column(String(50), nullable=False)
    cursos_aplicables: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Saber {self.codigo} {self.comunidad}/{self.materia}/{self.cursos_aplicables}>"
