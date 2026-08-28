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
    #: Etapa educativa de la que es esta fila: «ESO», «Bachillerato».
    #:
    #: No es redundante con `cursos_aplicables`. Las competencias específicas
    #: son comunes a toda la etapa, y por eso el seed fusiona sus cursos en vez
    #: de crear una fila por curso; sin este campo, «Matemáticas» de la ESO y
    #: de Bachillerato serían **la misma fila** —mismo código, misma materia,
    #: misma comunidad— y la segunda carga pisaría a la primera en silencio.
    #: Ver la migración `d1a7b4e62c95`.
    etapa: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Lengua en que publica el boletín del que salió esta fila. No es la
    #: preferencia de nadie: es una propiedad del documento oficial. El DOGC
    #: publica en catalán y el BOPV en euskera y castellano.
    idioma: Mapped[str] = mapped_column(String(5), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    #: 120 y no 50 desde el 27/08: cuatro materias del decreto vasco pasan
    #: de 50 caracteres y la más larga llega a 57. Ver la migración
    #: `c9e4f2a10b73`, que explica por qué se amplía en vez de acortarlas.
    materia: Mapped[str | None] = mapped_column(String(120), nullable=True)
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
    #: Ver el comentario en `Competencia.etapa`.
    etapa: Mapped[str] = mapped_column(String(20), nullable=False)
    idioma: Mapped[str] = mapped_column(String(5), nullable=False)
    id_competencia: Mapped[int] = mapped_column(
        ForeignKey("competencia.id_competencia", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    materia: Mapped[str] = mapped_column(String(120), nullable=False)
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
        Index("ix_saber_comunidad_etapa_materia", "comunidad", "etapa", "materia"),
    )

    id_saber: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    comunidad: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Ver el comentario en `Competencia.etapa`.
    etapa: Mapped[str] = mapped_column(String(20), nullable=False)
    idioma: Mapped[str] = mapped_column(String(5), nullable=False)
    bloque: Mapped[str] = mapped_column(String(200), nullable=False)
    materia: Mapped[str] = mapped_column(String(120), nullable=False)
    cursos_aplicables: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Saber {self.codigo} {self.comunidad}/{self.materia}/{self.cursos_aplicables}>"
