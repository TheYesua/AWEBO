"""Registro de qué alternativa eligió el docente y de dónde venía cada una.

Esta tabla no hace falta para que la funcionalidad *funcione*: el docente
elegiría igual sin ella. Existe por una razón distinta.

Lo que la aplicación ofrece es una **interfaz de elección**: dos redacciones,
el docente se queda con una. Un **test A/B** es otra cosa: un experimento que
mide qué prompt gana. Son compatibles, pero solo si se registra cada elección
junto con la variante que la produjo — qué prompt, qué versión, qué proveedor,
qué modelo.

Ese dato es casi gratis de guardar mientras se construye la funcionalidad, e
**imposible de reconstruir después**. Añadir esta tabla dentro de seis meses
significaría tirar seis meses de señal sobre qué prompts funcionan. Es la única
parte de la tarea que no admite aplazamiento, y por eso se implementa primero.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class EleccionPropuesta(db.Model):
    """Una elección entre dos redacciones de una misma sección.

    Se guarda la procedencia de **ambas** candidatas, no solo de la ganadora:
    saber que se eligió ``descripcion_v2`` no dice nada si no se sabe contra
    qué competía.
    """

    __tablename__ = "eleccion_propuesta"
    __table_args__ = (
        # Las consultas útiles son «qué variante gana en esta sección» y
        # «qué eligió este usuario»: se indexan las dos.
        Index("ix_eleccion_seccion_variante", "seccion", "variante_elegida"),
        Index("ix_eleccion_usuario", "id_usuario"),
    )

    id_eleccion: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Las DOS claves ajenas van con ``SET NULL``, no con ``CASCADE``.
    #
    # Un registro de elección no contiene contenido del docente: solo el
    # nombre de la sección, las versiones de prompt que competían y qué
    # proveedor y modelo produjo cada una. Es señal anónima sobre qué prompt
    # redacta mejor, y esa señal se acumula durante meses.
    #
    # Con ``CASCADE`` bastaría con que alguien borrase una situación —o su
    # cuenta— para perder todo lo que enseñó. Con ``SET NULL``, el registro
    # sobrevive huérfano, que es exactamente lo que se quiere: ya no se puede
    # saber de quién era, y sigue sirviendo para lo único que importa aquí.
    id_situacion: Mapped[int | None] = mapped_column(
        ForeignKey("situacion_aprendizaje.id_situacion", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    id_usuario: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario", ondelete="SET NULL"), nullable=True
    )

    seccion: Mapped[str] = mapped_column(String(40), nullable=False)

    #: Versión de prompt de la candidata que ganó, p. ej. ``"v1"``.
    variante_elegida: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Versión de prompt de la que perdió.
    variante_descartada: Mapped[str] = mapped_column(String(20), nullable=False)

    #: ``"actual"`` si ganó la redacción que ya estaba, ``"alternativa"`` si
    #: ganó la nueva. Distinguirlo importa: una alternativa que casi nunca se
    #: elige indica que el prompt no aporta, aunque su variante sea distinta.
    posicion_elegida: Mapped[str] = mapped_column(String(15), nullable=False)

    #: Proveedor y modelo de cada candidata. Un prompt puede rendir distinto
    #: según el modelo, así que sin esto la señal queda confundida.
    meta_elegida: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    meta_descartada: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Eleccion {self.seccion}: {self.variante_elegida} sobre "
            f"{self.variante_descartada} ({self.posicion_elegida})>"
        )
