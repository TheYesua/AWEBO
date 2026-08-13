"""Endpoints de consulta del catálogo curricular LOMLOE.

Sirven los datos que alimentan los desplegables del frontend al construir
o editar una situación de aprendizaje: materias disponibles, competencias
específicas, criterios de evaluación y saberes básicos, siempre filtrables
por ``materia`` y ``curso``.

Filtrado por comunidad
----------------------
Desde que el catálogo guarda más de un currículo, **todo se filtra además por
la comunidad de quien pregunta**, que sale de su perfil. Sin eso, el
desplegable de materias de un docente de Ceuta ofrecería las de Cataluña, y al
elegir una la generación se rechazaría por falta de currículo — un callejón sin
salida servido por la propia interfaz.

Quien no tenga comunidad reconocida en su perfil no ve materias. Es incómodo y
es lo correcto: la alternativa es enseñarle un catálogo que no puede usar.

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
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..curriculo import comunidades
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


def _comunidad_actual() -> str | None:
    """Comunidad para la que se pregunta: la de ``?provincia=`` o la del perfil.

    DECISIÓN REVISADA, Y CONVIENE QUE CONSTE
    -----------------------------------------
    Esto salía **solo** del perfil, con este argumento escrito: «dejar elegir
    la comunidad por parámetro permitiría que el formulario ofreciera materias
    de una comunidad para una SdA que se va a generar contra otra».

    El argumento se cayó en cuanto el formulario ganó su propio selector de
    provincia: ahora una SdA **puede** generarse contra una comunidad distinta
    de la del perfil —quien da clase en dos sitios, o prepara material para
    otra—, y negarle al desplegable la provincia elegida produce exactamente
    el desajuste que la regla quería evitar, pero al revés.

    La otra mitad del argumento —«un explorador de currículos ajenos»— era
    cierta y resulta inofensiva: el currículo es normativa pública publicada en
    boletines oficiales. Aquí no hay nada de nadie que proteger.

    Sigue exigiendo sesión, eso sí, para no servir de fuente de scraping
    anónimo.
    """
    from ..curriculo import provincias
    from ..services import geografia

    pedida = (request.args.get("provincia") or "").strip()
    if pedida:
        return provincias.comunidad_de(pedida)
    return geografia.comunidad_de(current_user)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@bp.get("/materias")
@login_required
def listar_materias():
    """Lista distinta de materias con competencias cargadas en el catálogo."""
    comunidad = _comunidad_actual()
    if comunidad is None:
        return jsonify([]), 200
    filas = db.session.scalars(
        select(Competencia.materia)
        .where(Competencia.comunidad == comunidad)
        .where(Competencia.materia.is_not(None))
        .distinct()
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
    comunidad = _comunidad_actual()
    if comunidad is None:
        return jsonify([]), 200

    def _pares(modelo) -> set[tuple[str, str]]:
        filas = db.session.execute(
            select(
                modelo.materia,
                func.jsonb_array_elements_text(modelo.cursos_aplicables).label("curso"),
            )
            .where(modelo.comunidad == comunidad)
            .where(modelo.materia.is_not(None))
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

    comunidad = _comunidad_actual()
    if comunidad is None:
        return jsonify([]), 200

    stmt = select(Competencia).where(Competencia.comunidad == comunidad).order_by(Competencia.materia, Competencia.codigo)
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

    comunidad = _comunidad_actual()
    if comunidad is None:
        return jsonify([]), 200

    stmt = select(CriterioEvaluacion).where(CriterioEvaluacion.comunidad == comunidad).order_by(
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

    comunidad = _comunidad_actual()
    if comunidad is None:
        return jsonify([]), 200

    stmt = select(SaberBasico).where(SaberBasico.comunidad == comunidad).order_by(
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


@bp.get("/provincias")
@login_required
def listar_provincias():
    """Provincias agrupadas por comunidad, para el desplegable.

    Se sirve desde el servidor y no se escribe en el JavaScript porque la marca
    de «tiene currículo cargado» sale de la base de datos. Una lista fija en el
    frontend se desincronizaría el día que se cargue una comunidad nueva, y el
    formulario seguiría diciendo que no hay currículo cuando ya lo hay.

    **Se devuelven todas, no solo las que tienen currículo.** Un docente de
    Aragón existe aunque AWEBO no tenga su decreto, y esconderle su provincia no
    la hace desaparecer: le deja sin entender qué se espera que elija. Se marcan
    con ``tiene_curriculo`` para que la interfaz pueda decirlo.
    """
    from ..curriculo import provincias as cat

    con_curriculo = set(
        db.session.scalars(select(Competencia.comunidad).distinct()).all()
    )

    return (
        jsonify(
            [
                {
                    "comunidad": etiqueta,
                    "provincias": [
                        {
                            "codigo": codigo,
                            "nombre": nombre_prov,
                            "tiene_curriculo": cat.PROVINCIAS[codigo][1] in con_curriculo,
                        }
                        for codigo, nombre_prov in lista
                    ],
                }
                for etiqueta, lista in cat.agrupadas()
            ]
        ),
        200,
    )
