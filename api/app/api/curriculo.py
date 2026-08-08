"""Endpoints de consulta del catálogo curricular LOMLOE.

Sirven los datos que alimentan los desplegables del frontend al construir
o editar una situación de aprendizaje: materias disponibles, competencias
específicas, criterios de evaluación y saberes básicos, siempre filtrables
por ``materia`` y ``curso``.

Estos endpoints son de sólo lectura y requieren sesión activa para evitar
scraping anónimo, pero no exponen información privada del usuario.

Filtrado por curso
------------------
El campo ``cursos_aplicables`` es un array JSONB; usamos el operador
``?`` de PostgreSQL (``jsonb ? text``) para comprobar la pertenencia,
lo que aprovecha un índice GIN si se añadiera en el futuro.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import func, select

from ..extensions import db
from ..models import Competencia, CriterioEvaluacion, SaberBasico


bp = Blueprint("curriculo", __name__, url_prefix="/api/curriculo")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filtro_curso(columna, curso: str | None):
    """Devuelve un predicado ``cursos_aplicables ? curso`` o ``None``."""
    if not curso:
        return None
    # ``jsonb ? text`` devuelve true si el array contiene ese string.
    return columna.op("?")(curso)


def _parse_params() -> tuple[str | None, str | None]:
    """Extrae ``materia`` y ``curso`` del querystring, normalizados."""
    materia = (request.args.get("materia") or "").strip() or None
    curso = (request.args.get("curso") or "").strip() or None
    return materia, curso


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@bp.get("/materias")
@login_required
def listar_materias():
    """Lista distinta de materias con competencias cargadas en el catálogo."""
    filas = db.session.scalars(
        select(Competencia.materia).where(Competencia.materia.is_not(None)).distinct()
    ).all()
    return jsonify(sorted(filas)), 200


@bp.get("/cobertura")
@login_required
def cobertura():
    """Parejas materia/curso con currículo **completo** en el catálogo.

    Existe porque ``/materias`` devuelve materias sueltas y el formulario no
    tenía forma de saber a qué cursos llega cada una. Los dos desplegables
    eran independientes, así que se podía elegir «Matemáticas · 4º ESO», que
    no existe: en 4.º la materia se desdobla en los itinerarios A y B. La SA
    se generaba con un listado curricular vacío y el modelo, obedeciendo la
    instrucción de no inventar códigos, devolvía secciones vacías.

    «Completo» significa las tres cosas: competencias, criterios y saberes.
    Con dos de las tres, la conexión curricular saldría coja igualmente, así
    que la pareja no debe ofrecerse.
    """
    def _pares(modelo) -> set[tuple[str, str]]:
        filas = db.session.execute(
            select(
                modelo.materia,
                func.jsonb_array_elements_text(modelo.cursos_aplicables).label("curso"),
            ).where(modelo.materia.is_not(None))
        ).all()
        return {(m, c) for m, c in filas}

    completos = _pares(Competencia) & _pares(CriterioEvaluacion) & _pares(SaberBasico)

    por_materia: dict[str, list[str]] = {}
    for materia, curso in completos:
        por_materia.setdefault(materia, []).append(curso)

    return (
        jsonify(
            [
                {"materia": m, "cursos": sorted(cursos)}
                for m, cursos in sorted(por_materia.items())
            ]
        ),
        200,
    )


@bp.get("/competencias")
@login_required
def listar_competencias():
    """Competencias específicas. Filtros opcionales: ``materia``, ``curso``."""
    materia, curso = _parse_params()

    stmt = select(Competencia).order_by(Competencia.materia, Competencia.codigo)
    if materia:
        stmt = stmt.where(Competencia.materia == materia)
    if (filtro := _filtro_curso(Competencia.cursos_aplicables, curso)) is not None:
        stmt = stmt.where(filtro)

    return (
        jsonify(
            [
                {
                    "id": c.id_competencia,
                    "codigo": c.codigo,
                    "tipo": c.tipo,
                    "materia": c.materia,
                    "cursos_aplicables": c.cursos_aplicables,
                    "descriptores": c.descriptores,
                    "descripcion": c.descripcion,
                }
                for c in db.session.scalars(stmt).all()
            ]
        ),
        200,
    )


@bp.get("/criterios")
@login_required
def listar_criterios():
    """Criterios de evaluación. Filtros: ``materia``, ``curso``, ``competencia_id``."""
    materia, curso = _parse_params()
    competencia_id = request.args.get("competencia_id", type=int)

    stmt = select(CriterioEvaluacion).order_by(
        CriterioEvaluacion.materia, CriterioEvaluacion.codigo
    )
    if materia:
        stmt = stmt.where(CriterioEvaluacion.materia == materia)
    if (filtro := _filtro_curso(CriterioEvaluacion.cursos_aplicables, curso)) is not None:
        stmt = stmt.where(filtro)
    if competencia_id is not None:
        stmt = stmt.where(CriterioEvaluacion.id_competencia == competencia_id)

    return (
        jsonify(
            [
                {
                    "id": cr.id_criterio,
                    "codigo": cr.codigo,
                    "id_competencia": cr.id_competencia,
                    "materia": cr.materia,
                    "cursos_aplicables": cr.cursos_aplicables,
                    "descripcion": cr.descripcion,
                }
                for cr in db.session.scalars(stmt).all()
            ]
        ),
        200,
    )


@bp.get("/saberes")
@login_required
def listar_saberes():
    """Saberes básicos (items). Filtros: ``materia``, ``curso``, ``bloque``."""
    materia, curso = _parse_params()
    bloque = (request.args.get("bloque") or "").strip() or None

    stmt = select(SaberBasico).order_by(
        SaberBasico.materia, SaberBasico.codigo
    )
    if materia:
        stmt = stmt.where(SaberBasico.materia == materia)
    if (filtro := _filtro_curso(SaberBasico.cursos_aplicables, curso)) is not None:
        stmt = stmt.where(filtro)
    if bloque:
        stmt = stmt.where(SaberBasico.bloque == bloque)

    return (
        jsonify(
            [
                {
                    "id": s.id_saber,
                    "codigo": s.codigo,
                    "bloque": s.bloque,
                    "materia": s.materia,
                    "cursos_aplicables": s.cursos_aplicables,
                    "descripcion": s.descripcion,
                }
                for s in db.session.scalars(stmt).all()
            ]
        ),
        200,
    )
