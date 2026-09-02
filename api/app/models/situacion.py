"""Entidades Situación de Aprendizaje y Versión, con sus tablas intermedias."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    from .curriculo import Competencia, CriterioEvaluacion, SaberBasico
    from .ods import ODS
    from .usuario import Usuario


#: Etapas conocidas, de la más antigua a la más reciente. El orden importa
#: poco aquí; la lista está para que añadir una no obligue a tocar la función.
_ETAPAS_EN_EL_CURSO = ("Bachillerato",)


def _etapa_del_curso(curso: str | None) -> str:
    """Etapa deducida de la cadena del curso. **Es la red, no la regla.**

    La regla es `situacion_service.etapa_de`, que la lee del catálogo. Esto
    solo se usa como `default` del ORM, cuando se construye una
    `SituacionAprendizaje` sin pasar por el servicio: tests, scripts y
    cualquier camino futuro que se olvide del campo.

    Deducir de texto libre es frágil —por eso no manda— pero aquí el coste de
    equivocarse es que una fila creada a mano diga «ESO» cuando no lo es, y el
    de no tenerlo era que ochenta ficheros de test no pudieran insertar nada.
    """
    for etapa in _ETAPAS_EN_EL_CURSO:
        if curso and etapa.lower() in curso.lower():
            return etapa
    return "ESO"


# =============================================================================
# Tablas de asociación (muchos a muchos)
# =============================================================================

situacion_competencia = Table(
    "situacion_competencia",
    db.metadata,
    Column(
        "id_situacion",
        Integer,
        ForeignKey("situacion_aprendizaje.id_situacion", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "id_competencia",
        Integer,
        ForeignKey("competencia.id_competencia", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

situacion_criterio = Table(
    "situacion_criterio",
    db.metadata,
    Column(
        "id_situacion",
        Integer,
        ForeignKey("situacion_aprendizaje.id_situacion", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "id_criterio",
        Integer,
        ForeignKey("criterio_evaluacion.id_criterio", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

situacion_saber = Table(
    "situacion_saber",
    db.metadata,
    Column(
        "id_situacion",
        Integer,
        ForeignKey("situacion_aprendizaje.id_situacion", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "id_saber",
        Integer,
        ForeignKey("saber_basico.id_saber", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

situacion_ods = Table(
    "situacion_ods",
    db.metadata,
    Column(
        "id_situacion",
        Integer,
        ForeignKey("situacion_aprendizaje.id_situacion", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "id_ods",
        Integer,
        ForeignKey("ods.id_ods", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


# =============================================================================
# Entidades principales
# =============================================================================


class SituacionAprendizaje(db.Model):
    """Situación de aprendizaje LOMLOE generada y editable por el docente."""

    __tablename__ = "situacion_aprendizaje"

    # Estados del ciclo de vida
    BORRADOR = "borrador"            # creada sin contenido generado
    GENERANDO = "generando"          # tarea Celery en curso
    GENERADA = "generada"            # contenido generado, editable
    ERROR_GENERACION = "error_generacion"  # fallo en la última generación
    FINALIZADA = "finalizada"        # el docente la da por terminada

    #: Los estados en el orden en que se presentan. Es la definición canónica:
    #: los servicios que cuentan o listan por estado iteran esta tupla en vez
    #: de repetir la lista, para que añadir un estado nuevo no deje a ninguno
    #: contando de menos en silencio.
    #:
    #: Ordenada, al contrario que ``_ESTADOS``: un conjunto no garantiza orden
    #: y las tarjetas del panel saldrían barajadas entre recargas.
    ESTADOS = (BORRADOR, GENERANDO, GENERADA, ERROR_GENERACION, FINALIZADA)

    #: Para comprobaciones de pertenencia. Se deriva de la tupla, no se
    #: escribe aparte.
    _ESTADOS = set(ESTADOS)

    #: Idiomas en los que se puede **redactar** una situación, con su nombre en
    #: castellano. Es la definición canónica: el esquema de validación, el
    #: prompt de traducción y los desplegables salen de aquí. Estaba repetida
    #: en cuatro sitios, que es como se acaba pudiendo elegir en el formulario
    #: un idioma que el validador rechaza.
    #:
    #: No confundir con ``app.i18n.IDIOMAS``, que son los de la **interfaz**.
    #: Son dos cosas distintas: la interfaz puede estar en catalán mientras el
    #: documento se redacta en inglés, y al revés.
    #:
    #: Primero las lenguas cooficiales del Estado, que son el caso de uso
    #: principal, y después las extranjeras.
    IDIOMAS: dict[str, str] = {
        "es": "español",
        "ca": "catalán",
        "gl": "gallego",
        "eu": "euskera",
        "en": "inglés",
        "fr": "francés",
        "ar": "árabe",
    }

    # Tipos de adaptación curricular
    ADAPTACION_NO_SIGNIFICATIVA = "no_significativa"
    ADAPTACION_SIGNIFICATIVA = "significativa"

    id_situacion: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identificación
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    comunidad_autonoma: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Provincia de esta SdA. Se hereda del perfil al crearla y se puede
    #: cambiar por situación: un docente puede preparar material para otra.
    provincia: Mapped[str | None] = mapped_column(String(30), nullable=True)
    curso: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    #: Etapa educativa: «ESO» o «Bachillerato». Ver la migración
    #: `e5b93c47da10`.
    #:
    #: QUIÉN LA PONE, Y POR QUÉ HAY UNA RED DEBAJO
    #: --------------------------------------------
    #: La pone el servicio, leyéndola del catálogo
    #: (`situacion_service.etapa_de`): esa es la fuente de verdad y es la que
    #: distingue «Matematika · 1º ESO» de «Matematika · 1º Bachillerato».
    #:
    #: El `default` de aquí **no compite con eso**: solo actúa cuando alguien
    #: construye el modelo a mano sin pasar por el servicio, y entonces deriva
    #: la etapa del curso igual que hace el backfill de la migración con las
    #: filas antiguas.
    #:
    #: Nació sin default y NOT NULL, razonando que «una SdA sin etapa debe
    #: fallar». El resultado fueron **doscientos tests rotos**: hay ochenta
    #: ficheros que instancian este modelo directamente, y ninguno tenía por
    #: qué saber de un campo nuevo. Una columna obligatoria sin forma de
    #: rellenarse sola no protege de nada: obliga a repetir el mismo dato en
    #: cada sitio, que es justo donde se cuelan las incoherencias.
    etapa: Mapped[str] = mapped_column(
        String(20), nullable=False,
        default=lambda ctx: _etapa_del_curso(ctx.get_current_parameters().get("curso")),
    )
    #: 120 por lo mismo que en el catálogo (migración `c9e4f2a10b73`). Esta
    #: es la que de verdad importaba: aquí se guarda la materia que elige el
    #: docente, así que el límite corto habría fallado al guardar su trabajo.
    materia: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # Contexto y configuración
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    metodologia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    num_sesiones: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duracion_sesion_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idioma: Mapped[str] = mapped_column(String(10), nullable=False, default="es")
    perfil_aula: Mapped[str | None] = mapped_column(Text, nullable=True)
    materiales_contexto: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contenido generado
    contenido: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BORRADOR, index=True
    )

    # Atención a la diversidad (adaptaciones curriculares)
    id_situacion_origen: Mapped[int | None] = mapped_column(
        ForeignKey("situacion_aprendizaje.id_situacion", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tipo_adaptacion: Mapped[str | None] = mapped_column(String(30), nullable=True)
    perfil_alumnado: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Auditoría temporal
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_modificacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ---------- Relaciones ----------
    usuario: Mapped["Usuario"] = relationship(back_populates="situaciones")

    # Adaptaciones (recursiva)
    situacion_origen: Mapped["SituacionAprendizaje | None"] = relationship(
        "SituacionAprendizaje",
        remote_side="SituacionAprendizaje.id_situacion",
        back_populates="adaptaciones",
    )
    adaptaciones: Mapped[list["SituacionAprendizaje"]] = relationship(
        "SituacionAprendizaje",
        back_populates="situacion_origen",
        cascade="save-update, merge",
    )

    # Versiones
    versiones: Mapped[list["Version"]] = relationship(
        back_populates="situacion",
        cascade="all, delete-orphan",
        order_by="Version.numero_version",
    )

    # Currículo
    competencias: Mapped[list["Competencia"]] = relationship(
        secondary=situacion_competencia, lazy="selectin"
    )
    criterios: Mapped[list["CriterioEvaluacion"]] = relationship(
        secondary=situacion_criterio, lazy="selectin"
    )
    saberes: Mapped[list["SaberBasico"]] = relationship(
        secondary=situacion_saber, lazy="selectin"
    )
    # ODS: SIN relación, a propósito.
    #
    # La tabla `situacion_ods` y el catálogo de la ONU se quedan donde están,
    # pero aquí no hay `relationship`. Motivo: **ningún prompt pide ODS** —se
    # comprobó recorriendo `app/prompts/` entero el 11/08/2026—, así que el
    # JSONB nunca los trae y no hay nada con lo que poblarla. Mantener la
    # relación con `lazy="selectin"` era una consulta garantizada a vacío en
    # cada carga de cada SdA.
    #
    # Cuando haya una sección que los pida, esto vuelve en dos líneas y
    # `enlaces_curriculares._MAPA` gana una entrada.

    # ---------- Helpers ----------
    @property
    def es_adaptacion(self) -> bool:
        """True si la situación se creó como adaptación curricular.

        Mira ``tipo_adaptacion`` y **no** ``id_situacion_origen``. La clave
        ajena es ``ON DELETE SET NULL``, así que si el original desaparece
        —porque su autor se dio de baja en modo total— se queda en NULL. Con la
        definición anterior, la adaptación dejaba de considerarse adaptación en
        ese momento: pasaba a mostrarse como una SA normal y, peor,
        ``construir_contexto`` perdía la marca, de modo que al regenerar
        cualquier sección se caía el bloque de atención a la diversidad sin que
        nadie lo notara —el texto salía bien escrito, solo que sin adaptar—.

        ``tipo_adaptacion`` es el dato que sobrevive y el que dice la verdad:
        haber sido adaptada es un hecho del pasado que no deshace el borrado de
        otra cuenta.
        """
        return self.tipo_adaptacion is not None

    @property
    def origen_desaparecido(self) -> bool:
        """True si es una adaptación cuyo original ya no existe.

        Es lo que permite a la interfaz explicar el caso en vez de mostrar una
        adaptación sin enlace y sin motivo aparente. Se decidió que la
        adaptación sobreviva: el trabajo de adaptar es de quien lo hizo, y
        perderlo porque otra persona se marcha sería un castigo por algo ajeno.
        """
        return self.tipo_adaptacion is not None and self.id_situacion_origen is None

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SA id={self.id_situacion} {self.materia}/{self.curso} "
            f"titulo={self.titulo!r}>"
        )


class Version(db.Model):
    """Snapshot histórico de una situación de aprendizaje."""

    __tablename__ = "version"

    id_version: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_situacion: Mapped[int] = mapped_column(
        ForeignKey("situacion_aprendizaje.id_situacion", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    numero_version: Mapped[int] = mapped_column(Integer, nullable=False)
    contenido: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    descripcion_cambio: Mapped[str | None] = mapped_column(String(255), nullable=True)

    situacion: Mapped["SituacionAprendizaje"] = relationship(back_populates="versiones")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Version {self.numero_version} de SA {self.id_situacion}>"
