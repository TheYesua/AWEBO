"""Tests de la doble propuesta: dos redacciones y el docente elige.

Lo que distingue esta operación de las otras tres: **no sustituye**. Deja la
candidata junto a la actual, bajo `_alternativa`, y espera. Casi todos los
tests de aquí giran sobre eso.

Y sobre el registro: la elección se anota en `eleccion_propuesta` con la
procedencia de **ambas** candidatas. Sin ese dato no hay forma de saber después
qué prompt produce mejores redacciones, y no se puede reconstruir a posteriori.
"""
from __future__ import annotations

import json

import pytest

from app.ai import FakeProvider
from app.ai.factory import _cache, reset_cache
from app.models import EleccionPropuesta
from app.prompts import operaciones as ops


CLAVE_FAKE = ("fake", "fake")

SA_BASE = {"titulo": "Situación de prueba", "curso": "2º ESO", "materia": "Matemáticas"}

ACTUAL = {
    "texto": "Redacción original de la situación.",
    "producto_final": "Una maqueta",
    "pregunta_guia": "¿Cómo lo harías?",
    "_meta": {"proveedor": "gemini", "modelo": "m1", "version_prompt": "v1"},
}
OTRA_REDACCION = {
    "texto": "La misma idea contada de otra manera.",
    "producto_final": "Una maqueta explicada",
    "pregunta_guia": "¿De qué modo lo abordarías?",
}


@pytest.fixture(autouse=True)
def _curriculo_disponible(sembrar_curriculo):
    sembrar_curriculo()


@pytest.fixture(autouse=True)
def _provider_limpio():
    reset_cache()
    yield
    reset_cache()


def _fijar_respuesta(texto: str) -> None:
    reset_cache()
    _cache[CLAVE_FAKE] = FakeProvider(tabla_respuestas={"": texto})


@pytest.fixture()
def sa(client, db):
    alta = client.post(
        "/auth/register",
        json={
            "correo": "prop@test.com",
            "contrasena": "ContraSegura1!",
            "nombre": "Docente Propuestas",
        },
    )
    assert alta.status_code in (200, 201), alta.get_data(as_text=True)

    creada = client.post("/api/situaciones", json=SA_BASE)
    assert creada.status_code == 201, creada.get_data(as_text=True)
    id_sa = creada.get_json()["id_situacion"]

    from app.extensions import db as _db
    from app.models import SituacionAprendizaje

    obj = _db.session.get(SituacionAprendizaje, id_sa)
    obj.contenido = {"descripcion": dict(ACTUAL)}
    obj.estado = SituacionAprendizaje.GENERADA
    _db.session.commit()
    return id_sa


def _pedir_alternativa(client, id_sa: int, seccion: str = "descripcion"):
    return client.post(f"/api/situaciones/{id_sa}/secciones/{seccion}/alternativa")


def _contenido(client, id_sa: int) -> dict:
    return client.get(f"/api/situaciones/{id_sa}").get_json()["contenido"]


# ---------------------------------------------------------------------------
# Generar la alternativa
# ---------------------------------------------------------------------------


class TestGenerarAlternativa:
    def test_no_sustituye_la_version_actual(self, client, sa):
        """La diferencia de fondo con resumir, expandir y traducir."""
        _fijar_respuesta(json.dumps(OTRA_REDACCION, ensure_ascii=False))
        assert _pedir_alternativa(client, sa).status_code == 202

        bloque = _contenido(client, sa)["descripcion"]
        assert bloque["texto"] == ACTUAL["texto"], (
            "pedir una alternativa no debe tocar lo que ya había"
        )

    def test_la_candidata_queda_dentro_del_bloque(self, client, sa):
        _fijar_respuesta(json.dumps(OTRA_REDACCION, ensure_ascii=False))
        _pedir_alternativa(client, sa)

        bloque = _contenido(client, sa)["descripcion"]
        assert bloque["_alternativa"]["texto"] == OTRA_REDACCION["texto"]

    def test_una_alternativa_nueva_reemplaza_a_la_anterior(self, client, sa):
        """No se acumulan candidatas: siempre hay como mucho una pendiente."""
        _fijar_respuesta(json.dumps(OTRA_REDACCION, ensure_ascii=False))
        _pedir_alternativa(client, sa)

        segunda = {**OTRA_REDACCION, "texto": "Una tercera forma de decirlo."}
        _fijar_respuesta(json.dumps(segunda, ensure_ascii=False))
        _pedir_alternativa(client, sa)

        bloque = _contenido(client, sa)["descripcion"]
        assert bloque["_alternativa"]["texto"] == segunda["texto"]
        assert "_alternativa" not in bloque["_alternativa"]

    def test_la_candidata_previa_no_se_envia_al_modelo(self, client, sa):
        """Mandarla invitaría al modelo a copiarla o a reescribirla."""
        _fijar_respuesta(json.dumps(OTRA_REDACCION, ensure_ascii=False))
        _pedir_alternativa(client, sa)
        _pedir_alternativa(client, sa)

        enviado = _cache[CLAVE_FAKE].llamadas[-1].user
        assert "_alternativa" not in enviado
        assert "_meta" not in enviado

    def test_la_conexion_curricular_no_admite_alternativa(self, client, sa):
        assert not ops.aplicable(ops.ALTERNATIVA, "conexion_curricular")
        res = client.post(
            f"/api/situaciones/{sa}/secciones/conexion_curricular/alternativa"
        )
        assert res.status_code == 422


class TestPromptAlternativa:
    def test_pide_otra_redaccion_del_mismo_alcance(self):
        peticion = ops.build(
            operacion=ops.ALTERNATIVA, seccion="descripcion", contenido=ACTUAL
        )
        assert "OTRA MANERA" in peticion.user
        assert "mismo alcance" in peticion.user

    def test_usa_temperatura_alta(self):
        """Con la temperatura de las otras operaciones saldría casi el mismo
        texto, y entonces la elección no tendría objeto."""
        alt = ops.build(operacion=ops.ALTERNATIVA, seccion="descripcion", contenido=ACTUAL)
        res = ops.build(operacion=ops.RESUMIR, seccion="descripcion", contenido=ACTUAL)
        assert alt.temperature > res.temperature


# ---------------------------------------------------------------------------
# Elegir
# ---------------------------------------------------------------------------


def _elegir(client, id_sa: int, cual: str, seccion: str = "descripcion"):
    return client.post(
        f"/api/situaciones/{id_sa}/secciones/{seccion}/elegir/{cual}"
    )


class TestElegir:
    @pytest.fixture(autouse=True)
    def _con_alternativa(self, client, sa):
        _fijar_respuesta(json.dumps(OTRA_REDACCION, ensure_ascii=False))
        _pedir_alternativa(client, sa)

    def test_quedarse_con_la_alternativa(self, client, sa):
        res = _elegir(client, sa, "alternativa")
        assert res.status_code == 200

        bloque = _contenido(client, sa)["descripcion"]
        assert bloque["texto"] == OTRA_REDACCION["texto"]
        assert "_alternativa" not in bloque, "la elección debe quedar resuelta"

    def test_quedarse_con_la_actual(self, client, sa):
        assert _elegir(client, sa, "actual").status_code == 200

        bloque = _contenido(client, sa)["descripcion"]
        assert bloque["texto"] == ACTUAL["texto"]
        assert "_alternativa" not in bloque

    def test_elegir_sin_alternativa_pendiente_devuelve_404(self, client, sa):
        _elegir(client, sa, "actual")
        res = _elegir(client, sa, "alternativa")
        assert res.status_code == 404
        assert res.get_json()["error"] == "sin_alternativa"

    def test_valor_invalido_devuelve_400(self, client, sa):
        res = _elegir(client, sa, "la-de-la-izquierda")
        assert res.status_code == 400
        assert res.get_json()["error"] == "eleccion_invalida"

    def test_la_descartada_sigue_recuperable(self, client, sa):
        """Se guarda una versión con las DOS candidatas antes de resolver."""
        _elegir(client, sa, "alternativa")

        versiones = client.get(f"/api/situaciones/{sa}/versiones").get_json()
        ultima = versiones[0]["contenido"]["contenido"]["descripcion"]
        assert ultima["texto"] == ACTUAL["texto"]
        assert ultima["_alternativa"]["texto"] == OTRA_REDACCION["texto"]


# ---------------------------------------------------------------------------
# El registro: lo que no se puede reconstruir después
# ---------------------------------------------------------------------------


class TestRegistroDeElecciones:
    @pytest.fixture(autouse=True)
    def _con_alternativa(self, client, sa):
        _fijar_respuesta(json.dumps(OTRA_REDACCION, ensure_ascii=False))
        _pedir_alternativa(client, sa)

    def test_elegir_deja_registro(self, client, db, sa):
        _elegir(client, sa, "alternativa")

        registros = db.session.query(EleccionPropuesta).all()
        assert len(registros) == 1
        assert registros[0].seccion == "descripcion"

    def test_se_registra_que_posicion_gano(self, client, db, sa):
        """Una alternativa que casi nunca gana indica que el prompt no aporta,
        aunque su variante sea distinta."""
        _elegir(client, sa, "actual")
        assert db.session.query(EleccionPropuesta).one().posicion_elegida == "actual"

    def test_se_registra_la_procedencia_de_ambas(self, client, db, sa):
        """Saber cuál ganó no dice nada sin saber contra qué competía."""
        _elegir(client, sa, "alternativa")

        reg = db.session.query(EleccionPropuesta).one()
        assert reg.meta_descartada["proveedor"] == "gemini"
        assert reg.meta_elegida["proveedor"] == "fake"
        assert reg.variante_descartada == "v1"

    def test_el_registro_sobrevive_al_borrado_de_la_situacion(self, client, db, sa):
        """La señal se acumula durante meses y no debe morir con una SA.

        Un registro no contiene contenido del docente: sección, versiones de
        prompt y proveedor de cada candidata. Queda huérfano y anónimo, que es
        justo lo que se quiere.
        """
        _elegir(client, sa, "alternativa")
        assert client.delete(f"/api/situaciones/{sa}").status_code == 204

        db.session.expire_all()
        registros = db.session.query(EleccionPropuesta).all()
        assert len(registros) == 1, "borrar una SA no debe borrar lo que enseñó"
        assert registros[0].id_situacion is None
        assert registros[0].seccion == "descripcion"

    def test_el_registro_sobrevive_al_borrado_del_usuario(self, client, db, sa):
        """Mismo motivo, y aquí se comprueba la cadena entera: al borrar la
        cuenta se va la SA con ella (CASCADE), y aun así el registro queda."""
        from app.models import SituacionAprendizaje, Usuario

        _elegir(client, sa, "alternativa")

        situacion = db.session.get(SituacionAprendizaje, sa)
        db.session.delete(db.session.get(Usuario, situacion.id_usuario))
        db.session.commit()

        db.session.expire_all()
        assert db.session.get(SituacionAprendizaje, sa) is None
        registros = db.session.query(EleccionPropuesta).all()
        assert len(registros) == 1
        assert registros[0].id_usuario is None
        assert registros[0].id_situacion is None
