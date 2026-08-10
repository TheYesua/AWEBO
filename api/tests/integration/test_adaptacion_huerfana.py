"""Qué le pasa a una adaptación cuando su original desaparece.

EL ESCENARIO
------------
Una SA puede ser adaptación de otra que pertenece a **otra persona**. Cuando esa
persona se da de baja en modo total, su SA se borra y la clave ajena
``id_situacion_origen`` es ``ON DELETE SET NULL``: la adaptación sobrevive, que
es lo decidido — el trabajo de adaptar es de quien lo hizo, y perderlo porque
otra persona se marcha sería un castigo por algo ajeno.

LO QUE NO ESTABA DECIDIDO Y RESULTÓ ESTAR MAL
----------------------------------------------
``es_adaptacion`` se calculaba como ``id_situacion_origen is not None``. Al
quedar en NULL, la adaptación **dejaba de considerarse adaptación**: en la
interfaz aparecía como una SA normal, y —peor— ``construir_contexto`` repetía
la misma regla por su cuenta, de modo que al regenerar cualquier sección se
perdía el bloque de atención a la diversidad sin avisar. El dato que sí
sobrevive, y que dice la verdad, es ``tipo_adaptacion``.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def pareja(db):
    """Una SA original de una persona y su adaptación, de otra."""
    from app.models import Rol, SituacionAprendizaje, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    autora = Usuario(correo="autora@ejemplo.es", nombre="Autora", id_rol=rol.id_rol)
    autora.set_password("ContrasenaBaja1")
    adaptadora = Usuario(correo="adapta@ejemplo.es", nombre="Adapta", id_rol=rol.id_rol)
    adaptadora.set_password("ContrasenaBaja1")
    db.session.add_all([autora, adaptadora])
    db.session.commit()

    original = SituacionAprendizaje(
        titulo="Original", materia="Matemáticas A", curso="4º ESO",
        id_usuario=autora.id_usuario, contenido={},
    )
    db.session.add(original)
    db.session.commit()

    adaptada = SituacionAprendizaje(
        titulo="Adaptada", materia="Matemáticas A", curso="4º ESO",
        id_usuario=adaptadora.id_usuario, contenido={},
        id_situacion_origen=original.id_situacion,
        tipo_adaptacion="significativa",
        perfil_alumnado="Alumnado con desfase curricular de dos cursos.",
    )
    db.session.add(adaptada)
    db.session.commit()
    return original, adaptada


def _borrar_original(db, original):
    db.session.delete(original)
    db.session.commit()


class TestLaAdaptacionSobrevive:
    def test_no_se_borra_al_borrarse_su_origen(self, db, pareja):
        from app.models import SituacionAprendizaje

        original, adaptada = pareja
        id_adaptada = adaptada.id_situacion
        _borrar_original(db, original)

        superviviente = db.session.get(SituacionAprendizaje, id_adaptada)
        assert superviviente is not None
        assert superviviente.id_situacion_origen is None

    def test_sigue_sabiendo_que_es_una_adaptacion(self, db, pareja):
        """El fallo que motiva este fichero.

        Con `es_adaptacion` atado a `id_situacion_origen`, quedarse huérfana la
        convertía en una SA normal a todos los efectos.
        """
        original, adaptada = pareja
        _borrar_original(db, original)
        db.session.refresh(adaptada)

        assert adaptada.es_adaptacion is True
        assert adaptada.tipo_adaptacion == "significativa"

    def test_y_lo_dice_de_forma_distinguible(self, db, pareja):
        """Ser adaptación y tener origen son dos cosas distintas: la interfaz
        necesita las dos para poder explicar la situación."""
        original, adaptada = pareja
        assert adaptada.origen_desaparecido is False

        _borrar_original(db, original)
        db.session.refresh(adaptada)
        assert adaptada.origen_desaparecido is True

    def test_una_sa_normal_nunca_es_huerfana(self, db, pareja):
        original, _ = pareja
        assert original.es_adaptacion is False
        assert original.origen_desaparecido is False


class TestElPromptNoPierdeLaAdaptacion:
    def test_el_contexto_sigue_marcando_la_adaptacion(self, app, db, pareja):
        """El daño invisible.

        `construir_contexto` repetía la regla por su cuenta. Al quedarse
        huérfana, regenerar cualquier sección dejaba de incluir el bloque de
        atención a la diversidad —y nadie se enteraba, porque el texto salía
        bien escrito, solo que sin adaptar.
        """
        from app.prompts.contexto import construir_contexto

        _, adaptada = pareja
        _borrar_original(db, adaptada.situacion_origen)
        db.session.refresh(adaptada)

        with app.test_request_context():
            ctx = construir_contexto(adaptada)

        assert ctx.es_adaptacion is True
        assert ctx.tipo_adaptacion == "significativa"

    def test_el_bloque_de_diversidad_sigue_en_el_prompt(self, app, db, pareja):
        """No basta con que el contexto lleve la marca: lo que importa es que
        llegue al texto que se le manda al modelo."""
        from app.prompts.contexto import construir_contexto
        from app.prompts.secciones import atencion_diversidad_v1 as diversidad

        _, adaptada = pareja
        _borrar_original(db, adaptada.situacion_origen)
        db.session.refresh(adaptada)

        with app.test_request_context():
            ctx = construir_contexto(adaptada)
            prompt = diversidad.build(ctx).user

        assert prompt.strip(), "el prompt de diversidad salió vacío"


class TestLaApiLoCuenta:
    def test_el_detalle_expone_que_el_origen_ya_no_esta(self, db, client, pareja):
        original, adaptada = pareja
        _borrar_original(db, original)

        client.post(
            "/auth/login",
            json={"correo": "adapta@ejemplo.es", "contrasena": "ContrasenaBaja1"},
        )
        r = client.get(f"/api/situaciones/{adaptada.id_situacion}")

        assert r.status_code == 200, r.get_json()
        cuerpo = r.get_json()
        assert cuerpo["es_adaptacion"] is True
        assert cuerpo["origen_desaparecido"] is True
        assert cuerpo["id_situacion_origen"] is None

    def test_mientras_el_origen_exista_no_dice_nada(self, db, client, pareja):
        _, adaptada = pareja
        client.post(
            "/auth/login",
            json={"correo": "adapta@ejemplo.es", "contrasena": "ContrasenaBaja1"},
        )
        r = client.get(f"/api/situaciones/{adaptada.id_situacion}")

        assert r.get_json()["origen_desaparecido"] is False
