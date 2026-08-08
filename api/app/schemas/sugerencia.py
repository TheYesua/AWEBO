"""Schemas de la sugerencia inicial de temáticas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..prompts.sugerencias import NUM_PROPUESTAS_DEFECTO, NUM_PROPUESTAS_MAX
from .situacion import IdiomaLiteral


class SugerenciaIn(BaseModel):
    """Datos mínimos para pedir temáticas.

    Solo curso y materia son obligatorios: la funcionalidad existe para el
    docente que aún no sabe sobre qué trabajar, así que exigirle contexto
    sería contradictorio.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    curso: str = Field(min_length=1, max_length=20)
    materia: str = Field(min_length=1, max_length=50)
    contexto: str | None = Field(
        default=None,
        max_length=1000,
        description="Texto libre: qué busca el docente, restricciones, intereses del aula.",
    )
    idioma: IdiomaLiteral = "es"
    num_propuestas: int = Field(
        default=NUM_PROPUESTAS_DEFECTO, ge=1, le=NUM_PROPUESTAS_MAX
    )


class PropuestaOut(BaseModel):
    """Una temática propuesta, lista para volcar al formulario de creación."""

    titulo: str
    resumen: str
    producto_final: str
    pregunta_guia: str


class SugerenciaOut(BaseModel):
    """Respuesta del endpoint de sugerencias."""

    propuestas: list[PropuestaOut]
