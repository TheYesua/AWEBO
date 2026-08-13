"""Contexto de generación: extrae los datos LOMLOE que alimentan los prompts.

Dado un :class:`SituacionAprendizaje`, consulta el catálogo (``Competencia``,
``CriterioEvaluacion``, ``SaberBasico``) filtrado por ``materia`` y
``curso`` del SA y lo empaqueta en un :class:`ContextoGeneracion`
serializable, listo para inyectar en los templates de prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from ..extensions import db
from ..services import geografia
from ..models import Competencia, CriterioEvaluacion, SaberBasico, SituacionAprendizaje


@dataclass
class ContextoGeneracion:
    """Datos consolidados para rellenar los prompts LOMLOE.

    Si la SA es una adaptación curricular (``es_adaptacion=True``), se
    incluyen también el tipo de adaptación y un resumen del contenido
    de la SA origen para que cada sección se genere ya adaptada.
    """

    # --- entrada del docente ----------------------------------------------
    id_situacion: int
    titulo: str
    curso: str
    materia: str
    idioma: str
    descripcion: str | None
    metodologia: str | None
    num_sesiones: int | None
    duracion_sesion_minutos: int | None
    perfil_aula: str | None
    materiales_contexto: str | None

    # --- catálogo curricular filtrado (ya serializable) ------------------
    competencias: list[dict[str, Any]] = field(default_factory=list)
    criterios: list[dict[str, Any]] = field(default_factory=list)
    saberes: list[dict[str, Any]] = field(default_factory=list)

    # --- adaptación curricular (opcional) ---------------------------------
    es_adaptacion: bool = False
    tipo_adaptacion: str | None = None  # "no_significativa" | "significativa"
    perfil_alumnado: str | None = None
    contenido_origen_resumen: str | None = None
    titulo_origen: str | None = None

    def resumen_tecnico(self) -> str:
        """Cabecera breve para depuración."""
        marca = f" · ADAPT[{self.tipo_adaptacion}]" if self.es_adaptacion else ""
        return (
            f"[SA {self.id_situacion} · {self.materia} · {self.curso}{marca}] "
            f"{len(self.competencias)}CE / {len(self.criterios)}CR / "
            f"{len(self.saberes)}SB"
        )

    def tiene_curriculo(self) -> bool:
        """¿Hay catálogo LOMLOE que anclar en esta materia y curso?

        Sin él, las secciones ``objetivos`` y ``conexion_curricular`` piden al
        modelo códigos de un listado vacío. Un modelo que cumpla la
        instrucción de no inventar devolverá listas vacías; uno que no la
        cumpla, códigos falsos. Las dos salidas son inservibles, así que más
        vale detectarlo antes de gastar la llamada.
        """
        return bool(self.competencias and self.criterios and self.saberes)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def construir_contexto(sa: SituacionAprendizaje) -> ContextoGeneracion:
    """Carga de BD el currículo aplicable y empaqueta el contexto.

    Si ``sa`` es una adaptación curricular (``id_situacion_origen`` no
    nulo), también carga el resumen de la SA origen y rellena los campos
    de adaptación para que los prompts puedan generar contenido adaptado.
    """
    # La comunidad de la SdA es texto libre desde el TFG, así que se normaliza
    # aquí y no se compara a pelo: «Andalucia» sin tilde y «ANDALUCÍA» tienen
    # que llegar al mismo currículo.
    #
    # Si no se reconoce, `normalizar` devuelve None y las tres consultas
    # vuelven vacías. Eso es deliberado: `_exigir_curriculo` lo detecta antes
    # de gastar la generación y lo dice. La alternativa —caer a Ceuta— sería
    # anclar el documento a una normativa que no es la de quien lo pide, sin
    # avisar, y eso solo se descubre contrastándolo con el decreto propio.
    comunidad = geografia.comunidad_de(sa)

    competencias = _cargar_competencias(sa.materia, sa.curso, comunidad)
    criterios = _cargar_criterios(sa.materia, sa.curso, comunidad)
    saberes = _cargar_saberes(sa.materia, sa.curso, comunidad)

    # Se pregunta al modelo en lugar de repetir aquí la regla. Cuando estaban
    # duplicadas, arreglar una y olvidar la otra era cuestión de tiempo: de
    # hecho es lo que pasó con las adaptaciones huérfanas.
    es_adaptacion = sa.es_adaptacion
    contenido_origen_resumen: str | None = None
    titulo_origen: str | None = None
    # `and sa.id_situacion_origen` porque desde que `es_adaptacion` mira
    # `tipo_adaptacion`, una adaptación huérfana entra aquí con la clave en
    # NULL. Consultar con ella devuelve None igualmente, pero SQLAlchemy avisa
    # («fully NULL primary key identity cannot load any object») y anuncia que
    # en el futuro será un error.
    if es_adaptacion and sa.id_situacion_origen is not None:
        sa_origen = db.session.get(SituacionAprendizaje, sa.id_situacion_origen)
        if sa_origen is not None:
            titulo_origen = sa_origen.titulo
            contenido_origen_resumen = _resumir_contenido(sa_origen.contenido or {})

    return ContextoGeneracion(
        id_situacion=sa.id_situacion,
        titulo=sa.titulo,
        curso=sa.curso,
        materia=sa.materia,
        idioma=sa.idioma,
        descripcion=sa.descripcion,
        metodologia=sa.metodologia,
        num_sesiones=sa.num_sesiones,
        duracion_sesion_minutos=sa.duracion_sesion_minutos,
        perfil_aula=sa.perfil_aula,
        materiales_contexto=sa.materiales_contexto,
        competencias=[
            {
                "codigo": c.codigo,
                "descripcion": c.descripcion,
                "descriptores": c.descriptores or [],
            }
            for c in competencias
        ],
        criterios=[
            {
                "codigo": cr.codigo,
                "competencia": _competencia_codigo_por_id(competencias, cr.id_competencia),
                "descripcion": cr.descripcion,
            }
            for cr in criterios
        ],
        saberes=[
            {
                "codigo": s.codigo,
                "bloque": s.bloque,
                "descripcion": s.descripcion,
            }
            for s in saberes
        ],
        es_adaptacion=es_adaptacion,
        tipo_adaptacion=sa.tipo_adaptacion,
        perfil_alumnado=sa.perfil_alumnado,
        contenido_origen_resumen=contenido_origen_resumen,
        titulo_origen=titulo_origen,
    )


def _resumir_contenido(contenido: dict[str, Any]) -> str:
    """Convierte el contenido JSON de la SA origen en texto legible."""
    if not contenido:
        return "(sin contenido previo)"
    lineas: list[str] = []
    for clave, valor in contenido.items():
        if clave.startswith("_"):
            continue
        lineas.append(f"### {clave}")
        if isinstance(valor, dict):
            for k, v in valor.items():
                if k == "_meta":
                    continue
                if isinstance(v, (list, dict)):
                    import json as _json
                    lineas.append(f"- {k}: {_json.dumps(v, ensure_ascii=False)[:400]}")
                else:
                    lineas.append(f"- {k}: {v}")
        elif isinstance(valor, list):
            for item in valor[:10]:
                lineas.append(f"- {item}")
        else:
            lineas.append(str(valor))
    return "\n".join(lineas) if lineas else "(sin contenido previo)"



# ---------------------------------------------------------------------------
# Helpers de carga
# ---------------------------------------------------------------------------


def _cargar(modelo, materia: str, curso: str, comunidad: str | None):
    """Filas del catálogo para esa materia, curso y **comunidad**.

    LA COMUNIDAD NO ES UN FILTRO MÁS
    ---------------------------------
    Sin ella, la base de datos guardaba un único currículo —implícitamente el
    de Ceuta— y todo funcionaba por accidente. En cuanto conviven dos, una SdA
    de Ceuta empezaría a citar criterios catalanes sin que nada avisara: los
    códigos se parecen, las descripciones son plausibles, y el documento sale
    completo. Es el peor tipo de error de los que produce esta aplicación,
    porque lo descubre el docente al contrastarlo con su propio decreto.

    ``comunidad`` a ``None`` devuelve **lista vacía**, no «todas». Ver
    ``construir_contexto``: es la diferencia entre no generar y generar algo
    anclado a la normativa equivocada.
    """
    if not comunidad:
        return []
    stmt = (
        select(modelo)
        .where(modelo.comunidad == comunidad)
        .where(modelo.materia == materia)
        .where(modelo.cursos_aplicables.op("?")(curso))
        .order_by(modelo.codigo)
    )
    return list(db.session.scalars(stmt).all())


def _cargar_competencias(materia: str, curso: str, comunidad: str | None) -> list[Competencia]:
    return _cargar(Competencia, materia, curso, comunidad)


def _cargar_criterios(materia: str, curso: str, comunidad: str | None) -> list[CriterioEvaluacion]:
    return _cargar(CriterioEvaluacion, materia, curso, comunidad)


def _cargar_saberes(materia: str, curso: str, comunidad: str | None) -> list[SaberBasico]:
    return _cargar(SaberBasico, materia, curso, comunidad)


def _competencia_codigo_por_id(
    competencias: list[Competencia], id_: int
) -> str:
    for c in competencias:
        if c.id_competencia == id_:
            return c.codigo
    return "?"
