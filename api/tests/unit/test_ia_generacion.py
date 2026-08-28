"""Tests unitarios del sistema de generación (prompts + tareas + provider)."""
from __future__ import annotations

import json

from pathlib import Path

import pytest

from app.ai import FakeProvider, get_provider
from app.ai.provider import LLMRequest
from app.models import Competencia, CriterioEvaluacion, SaberBasico, SituacionAprendizaje, Usuario, Rol
from app.prompts import ORDEN_SECCIONES, SECCIONES, construir_contexto
from app.tasks.generacion import _ejecutar_seccion, generar_situacion_completa


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


@pytest.fixture()
def sa_con_curriculo(db):
    """Crea una SA y un mini-catálogo LOMLOE apuntando a la misma materia/curso."""
    rol = db.session.query(Rol).filter_by(nombre="docente").one()
    user = Usuario(
        id_rol=rol.id_rol, correo="ia@test.com", nombre="IA Test"
    )
    user.set_password("ContraSegura1!")
    db.session.add(user)
    db.session.flush()

    ce = Competencia(
            comunidad="ceuta",
            idioma="es",
            etapa="ESO",
            codigo="CE1",
        tipo=Competencia.ESPECIFICA,
        materia="Matemáticas",
        cursos_aplicables=["2º ESO"],
        descriptores=["STEM1", "STEM2"],
        descripcion="Interpretar situaciones con modelos matemáticos.",
    )
    db.session.add(ce)
    db.session.flush()

    db.session.add_all(
        [
            CriterioEvaluacion(
            comunidad="ceuta",
            idioma="es",
            etapa="ESO",
            codigo="1.1",
                id_competencia=ce.id_competencia,
                materia="Matemáticas",
                cursos_aplicables=["2º ESO"],
                descripcion="Resuelve problemas numéricos en contexto real.",
            ),
            SaberBasico(
            comunidad="ceuta",
            idioma="es",
            etapa="ESO",
            codigo="A.1",
                bloque="Sentido numérico",
                materia="Matemáticas",
                cursos_aplicables=["2º ESO"],
                descripcion="Estrategias de recuento sistemático.",
            ),
        ]
    )

    sa = SituacionAprendizaje(
        id_usuario=user.id_usuario,
        titulo="El mercado local",
        curso="2º ESO",
        materia="Matemáticas",
        # El currículo se filtra por comunidad desde la fase 1 de la tarea 9c:
        # sin ella el contexto sale vacío y este test comprobaría el filtro
        # equivocado.
        comunidad_autonoma="Ceuta",
        num_sesiones=4,
        duracion_sesion_minutos=55,
        metodologia="Aprendizaje Basado en Proyectos",
    )
    db.session.add(sa)
    db.session.commit()
    return sa


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------


def test_construir_contexto_filtra_por_materia_y_curso(app, sa_con_curriculo):
    with app.app_context():
        ctx = construir_contexto(sa_con_curriculo)
    assert ctx.materia == "Matemáticas"
    assert ctx.curso == "2º ESO"
    assert [c["codigo"] for c in ctx.competencias] == ["CE1"]
    assert ctx.competencias[0]["descriptores"] == ["STEM1", "STEM2"]
    assert [cr["codigo"] for cr in ctx.criterios] == ["1.1"]
    assert ctx.criterios[0]["competencia"] == "CE1"
    assert [s["codigo"] for s in ctx.saberes] == ["A.1"]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_todas_las_secciones_construyen_un_llmrequest_valido(app, sa_con_curriculo):
    with app.app_context():
        ctx = construir_contexto(sa_con_curriculo)
    for nombre in ORDEN_SECCIONES:
        _, build = SECCIONES[nombre]
        req = build(ctx)
        assert isinstance(req, LLMRequest)
        assert req.system, f"{nombre} sin system"
        assert "Currículo aplicable" in req.user or nombre == "atencion_diversidad"
        assert ctx.titulo in req.user
        assert ctx.materia in req.user
        assert req.response_format == "json"


def test_conexion_curricular_incluye_saberes_en_el_prompt(app, sa_con_curriculo):
    with app.app_context():
        ctx = construir_contexto(sa_con_curriculo)
    _, build = SECCIONES["conexion_curricular"]
    req = build(ctx)
    assert "Saberes básicos" in req.user
    assert "A.1" in req.user


# ---------------------------------------------------------------------------
# FakeProvider
# ---------------------------------------------------------------------------


def test_fake_provider_es_determinista():
    provider = FakeProvider()
    req = LLMRequest(user="Hola", response_format="json")
    a = provider.generar(req)
    b = provider.generar(req)
    assert a.texto == b.texto
    assert a.proveedor == "fake"
    assert json.loads(a.texto)["generado_por"] == "FakeProvider"


def test_fake_provider_respeta_tabla_de_respuestas():
    provider = FakeProvider(tabla_respuestas={"MAGIA": "resultado fijo"})
    req = LLMRequest(user="esto contiene MAGIA dentro")
    res = provider.generar(req)
    assert res.texto == "resultado fijo"


def test_factory_devuelve_fake_en_tests(app):
    with app.app_context():
        provider = get_provider()
    assert isinstance(provider, FakeProvider)


# ---------------------------------------------------------------------------
# Ejecución de sección (helper interno)
# ---------------------------------------------------------------------------


def test_ejecutar_seccion_agrega_metadatos(app, sa_con_curriculo):
    with app.app_context():
        ctx = construir_contexto(sa_con_curriculo)
        provider = get_provider()
        payload, respuesta = _ejecutar_seccion("descripcion", ctx, provider)

    assert "_meta" in payload
    assert payload["_meta"]["seccion"] == "descripcion"
    assert payload["_meta"]["version_prompt"] == "v1"
    assert payload["_meta"]["proveedor"] == "fake"
    assert respuesta.proveedor == "fake"


# ---------------------------------------------------------------------------
# Tarea Celery en modo eager
# ---------------------------------------------------------------------------


def test_generar_situacion_completa_rellena_todas_las_secciones(app, sa_con_curriculo):
    id_sa = sa_con_curriculo.id_situacion
    with app.app_context():
        # .apply() ejecuta la tarea de forma síncrona pero asignando un
        # task_id real, necesario para que ``self.update_state(...)`` funcione.
        resumen = generar_situacion_completa.apply(args=(id_sa,)).get()

    assert resumen["completadas"] == len(ORDEN_SECCIONES)
    assert [s["nombre"] for s in resumen["secciones"]] == list(ORDEN_SECCIONES)

    with app.app_context():
        from app.extensions import db

        sa = db.session.get(SituacionAprendizaje, id_sa)
        assert sa.estado == SituacionAprendizaje.GENERADA
        for seccion in ORDEN_SECCIONES:
            assert seccion in sa.contenido
            assert sa.contenido[seccion]["_meta"]["seccion"] == seccion


class TestElPromptNoImponeUnFormatoDeCodigo:
    """El ejemplo del prompt enseñaba, sin querer, la convención de Ceuta.

    Llevaba `"CE1"`, `"1.1"` y `"A.3"` como valores de ejemplo. Al cargar
    Cataluña —cuyas competencias se numeran `1`..`9`, sin prefijo— la misma
    situación generada dos veces salió con dos convenciones: la versión en
    catalán citó `1, 2, 5, 7` siguiendo el dato del contexto, y la española
    `CE1, CE2…` siguiendo el ejemplo.

    El prefijo inventado no casa con el catálogo, así que esa SdA no se puede
    anclar. Y no da error: el contenido es correcto y solo falla la referencia.

    Un ejemplo con valores concretos enseña dos cosas a la vez —la forma del
    JSON y el formato de los códigos— y solo queríamos la primera.
    """

    def _prompt(self):
        from app.prompts.secciones import conexion_curricular_v1 as mod

        fuente = Path(mod.__file__).read_text(encoding="utf-8")
        # Solo el texto que se le manda al modelo, no los comentarios que
        # explican por qué: si no, el propio comentario haría pasar el test.
        # Es el mismo fallo del 13/08 con el guardián de `sincronizar`.
        return "\n".join(
            l for l in fuente.splitlines() if not l.strip().startswith("#")
        )

    def test_el_ejemplo_no_lleva_codigos_de_una_comunidad_concreta(self):
        prompt = self._prompt()

        assert '"codigo": "CE1"' not in prompt
        assert '"codigo": "A.3"' not in prompt

    def test_dice_explicitamente_que_no_se_cambie_el_formato(self):
        prompt = self._prompt()

        assert "NO LES CAMBIES EL FORMATO" in prompt
        assert "CE1" in prompt, "hace falta el contraejemplo para que se entienda"
