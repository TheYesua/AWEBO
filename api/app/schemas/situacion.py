"""Schemas Pydantic de la entidad Situación de Aprendizaje y sus Versiones."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import SituacionAprendizaje as SAModel


# ---------------------------------------------------------------------------
# Constantes / Literales de validación
# ---------------------------------------------------------------------------

EstadoLiteral = Literal[
    "borrador", "generando", "generada", "error_generacion", "finalizada"
]
TipoAdaptacionLiteral = Literal["no_significativa", "significativa"]
# Se escribe a mano y no se deriva de ``SituacionAprendizaje.IDIOMAS`` porque
# ``Literal`` necesita valores literales: construirlo en tiempo de ejecución
# funcionaría pero dejaría el esquema ilegible y sin ayuda del editor.
#
# El riesgo de tenerlo por duplicado —que alguien añada un idioma al modelo y
# el validador lo rechace— lo cubre un test que compara las dos listas.
IdiomaLiteral = Literal["es", "ca", "gl", "eu", "en", "fr", "ar"]


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


class SituacionCreateIn(BaseModel):
    """Datos para crear una situación de aprendizaje."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    titulo: str = Field(min_length=2, max_length=255)
    curso: str = Field(min_length=1, max_length=20)
    materia: str = Field(min_length=1, max_length=50)

    comunidad_autonoma: str | None = Field(default=None, max_length=50)
    descripcion: str | None = Field(default=None, max_length=4000)
    metodologia: str | None = Field(default=None, max_length=100)
    num_sesiones: int | None = Field(default=None, ge=1, le=200)
    duracion_sesion_minutos: int | None = Field(default=None, ge=15, le=240)
    idioma: IdiomaLiteral = "es"
    perfil_aula: str | None = Field(default=None, max_length=4000)
    materiales_contexto: str | None = Field(default=None, max_length=10000)
    contenido: dict[str, Any] = Field(default_factory=dict)


class SituacionUpdateIn(BaseModel):
    """Campos modificables de una situación. Todos opcionales (PATCH-style)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    titulo: str | None = Field(default=None, min_length=2, max_length=255)
    curso: str | None = Field(default=None, min_length=1, max_length=20)
    materia: str | None = Field(default=None, min_length=1, max_length=50)
    comunidad_autonoma: str | None = Field(default=None, max_length=50)
    descripcion: str | None = Field(default=None, max_length=4000)
    metodologia: str | None = Field(default=None, max_length=100)
    num_sesiones: int | None = Field(default=None, ge=1, le=200)
    duracion_sesion_minutos: int | None = Field(default=None, ge=15, le=240)
    idioma: IdiomaLiteral | None = None
    perfil_aula: str | None = Field(default=None, max_length=4000)
    materiales_contexto: str | None = Field(default=None, max_length=10000)
    contenido: dict[str, Any] | None = None
    estado: EstadoLiteral | None = None

    descripcion_cambio: str | None = Field(
        default=None,
        max_length=255,
        description="Texto libre que se guarda en la nueva versión histórica.",
    )


class AdaptacionCreateIn(BaseModel):
    """Datos para crear una adaptación curricular de una SA existente (CU-10)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tipo_adaptacion: TipoAdaptacionLiteral
    perfil_alumnado: str = Field(
        min_length=10,
        max_length=4000,
        description="Descripción del perfil del alumnado que necesita la adaptación.",
    )
    titulo: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
        description="Título de la SA adaptada. Si no se indica, se genera automáticamente.",
    )


class DuplicarIn(BaseModel):
    """Datos opcionales al duplicar una situación."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    titulo: str | None = Field(default=None, min_length=2, max_length=255)


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------


class SituacionListItemOut(BaseModel):
    """Vista resumida para listados."""

    model_config = ConfigDict(from_attributes=True)

    id_situacion: int
    titulo: str
    curso: str
    materia: str
    estado: EstadoLiteral
    es_adaptacion: bool
    origen_desaparecido: bool
    fecha_creacion: datetime
    fecha_modificacion: datetime

    @classmethod
    def from_model(cls, sa: SAModel) -> "SituacionListItemOut":
        return cls(
            id_situacion=sa.id_situacion,
            titulo=sa.titulo,
            curso=sa.curso,
            materia=sa.materia,
            estado=sa.estado,
            es_adaptacion=sa.es_adaptacion,
            origen_desaparecido=sa.origen_desaparecido,
            fecha_creacion=sa.fecha_creacion,
            fecha_modificacion=sa.fecha_modificacion,
        )


class SituacionOut(BaseModel):
    """Vista completa de una situación de aprendizaje."""

    model_config = ConfigDict(from_attributes=True)

    id_situacion: int
    id_usuario: int
    titulo: str
    curso: str
    materia: str
    comunidad_autonoma: str | None
    descripcion: str | None
    metodologia: str | None
    num_sesiones: int | None
    duracion_sesion_minutos: int | None
    idioma: str
    perfil_aula: str | None
    materiales_contexto: str | None
    contenido: dict[str, Any]
    estado: EstadoLiteral

    id_situacion_origen: int | None
    tipo_adaptacion: TipoAdaptacionLiteral | None
    perfil_alumnado: str | None

    # Los dos, y no solo el primero: `es_adaptacion` dice qué es esta SA y
    # `origen_desaparecido` si su original sigue existiendo. Con solo
    # `id_situacion_origen` la interfaz no puede distinguir «no es una
    # adaptación» de «lo es y su original ya no está», que es justo el caso que
    # hay que explicar.
    es_adaptacion: bool
    origen_desaparecido: bool

    fecha_creacion: datetime
    fecha_modificacion: datetime

    @classmethod
    def from_model(cls, sa: SAModel) -> "SituacionOut":
        return cls.model_validate(sa, from_attributes=True)


class VersionOut(BaseModel):
    """Snapshot de versión histórica."""

    model_config = ConfigDict(from_attributes=True)

    id_version: int
    id_situacion: int
    numero_version: int
    contenido: dict[str, Any]
    descripcion_cambio: str | None
    fecha: datetime


class AudioIn(BaseModel):
    """Petición de audio para una sección.

    EL TEXTO LO MANDA EL CLIENTE, Y ESO ES DELIBERADO
    -------------------------------------------------
    La alternativa era extraerlo en el servidor desde el JSONB `contenido`.
    Se descartó por lo mismo que la tarea 8a decidió leer del DOM y no del
    JSON: **lo que se escucha tiene que ser lo que se ve**. Con dos extractores
    —uno en JavaScript para pintar y otro en Python para el audio— la
    divergencia es cuestión de tiempo, y se manifestaría como un audio que
    narra algo distinto de lo que hay en pantalla, que es el peor fallo posible
    para una función de accesibilidad.

    El precio es que alguien podría mandar texto arbitrario y usar AWEBO de
    sintetizador. Se acota con lo de siempre: hace falta sesión, hay que ser
    propietario de la situación, hay límite de peticiones y hay tope de
    longitud. Y el coste es tiempo de CPU propio, no una factura.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    #: Solo letras, números y guion bajo: este valor acaba formando parte de un
    #: nombre de fichero. Sin restringirlo, una sección `../../algo` escribiría
    #: fuera del volumen.
    seccion: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    texto: str = Field(min_length=1, max_length=20000)

