"""Tests del endpoint de sugerencia inicial de temáticas.

Se apoyan en ``FakeProvider``: ``TestConfig`` fija ``AI_PROVIDER=fake``, así
que no hay red ni consumo de tokens. Cuando un test necesita una respuesta
concreta del modelo, la inyecta en el caché de la factoría.
"""
from __future__ import annotations

import json

import pytest

from app.ai import FakeProvider
from app.ai.factory import _cache, reset_cache


#: Clave con la que la factoría cachea el proveedor simulado. Desde que la
#: elección de proveedor es por usuario, la clave es la pareja
#: ``(proveedor, modelo)`` y no solo el nombre.
CLAVE_FAKE = ("fake", "fake")


PROPUESTAS_OK = {
    "propuestas": [
        {
            "titulo": "El barrio que queremos",
            "resumen": "Análisis del entorno cercano y propuesta de mejora.",
            "producto_final": "Maqueta y panel explicativo",
            "pregunta_guia": "¿Cómo mejorarías tu barrio con lo que sabes?",
        },
        {
            "titulo": "Energía en el instituto",
            "resumen": "Auditoría del consumo del centro.",
            "producto_final": "Informe de eficiencia",
            "pregunta_guia": "¿Cuánta energía desperdicia nuestro centro?",
        },
    ]
}


def _fijar_respuesta(texto: str) -> None:
    """Sustituye el proveedor cacheado por uno que devuelve ``texto``.

    ``FakeProvider`` compara las claves de ``tabla_respuestas`` con el prompt;
    la cadena vacía está contenida en cualquier texto, así que actúa como
    comodín.
    """
    reset_cache()
    _cache[CLAVE_FAKE] = FakeProvider(tabla_respuestas={"": texto})


@pytest.fixture(autouse=True)
def _limpiar_provider():
    """Ningún test debe heredar el proveedor amañado por otro."""
    reset_cache()
    yield
    reset_cache()


def _registrar_y_login(client, correo="sug@test.com"):
    res = client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "ContraSegura1!",
            "nombre": "Docente Sugerencias", "comunidad_autonoma": "Ceuta",
        },
    )
    assert res.status_code in (200, 201), res.get_data(as_text=True)
    return res


@pytest.fixture()
def docente(client, db):
    return _registrar_y_login(client)


PETICION = {"curso": "3º ESO", "materia": "Tecnología"}


class TestAutenticacion:
    def test_sin_sesion_devuelve_401(self, client, db):
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        assert res.status_code == 401


class TestValidacion:
    def test_falta_materia_devuelve_400(self, client, docente):
        res = client.post("/api/situaciones/sugerencias", json={"curso": "3º ESO"})
        assert res.status_code == 400

    def test_falta_curso_devuelve_400(self, client, docente):
        res = client.post(
            "/api/situaciones/sugerencias", json={"materia": "Tecnología"}
        )
        assert res.status_code == 400

    def test_num_propuestas_fuera_de_rango_devuelve_400(self, client, docente):
        res = client.post(
            "/api/situaciones/sugerencias", json={**PETICION, "num_propuestas": 99}
        )
        assert res.status_code == 400

    def test_campo_desconocido_devuelve_400(self, client, docente):
        """``extra="forbid"`` en el esquema: nada de campos sorpresa."""
        res = client.post(
            "/api/situaciones/sugerencias", json={**PETICION, "colega": "hola"}
        )
        assert res.status_code == 400

    def test_contexto_es_opcional(self, client, docente):
        _fijar_respuesta(json.dumps(PROPUESTAS_OK, ensure_ascii=False))
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        assert res.status_code == 200


class TestRespuesta:
    def test_devuelve_las_propuestas_del_modelo(self, client, docente):
        _fijar_respuesta(json.dumps(PROPUESTAS_OK, ensure_ascii=False))
        res = client.post(
            "/api/situaciones/sugerencias",
            json={**PETICION, "contexto": "algo del barrio"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert len(body["propuestas"]) == 2
        assert body["propuestas"][0]["titulo"] == "El barrio que queremos"

    def test_cada_propuesta_trae_las_cuatro_claves(self, client, docente):
        """El frontend las pinta sin comprobar: deben venir siempre."""
        _fijar_respuesta(json.dumps(PROPUESTAS_OK, ensure_ascii=False))
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        for p in res.get_json()["propuestas"]:
            assert set(p) == {"titulo", "resumen", "producto_final", "pregunta_guia"}

    def test_incluye_metadatos_de_trazabilidad(self, client, docente):
        _fijar_respuesta(json.dumps(PROPUESTAS_OK, ensure_ascii=False))
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        meta = res.get_json()["_meta"]
        assert meta["proveedor"] == "fake"
        assert meta["version_prompt"] == "v1"


class TestRespuestasDegeneradas:
    """El modelo no siempre respeta el esquema pedido."""

    def test_lista_en_la_raiz_se_acepta(self, client, docente):
        _fijar_respuesta(
            json.dumps(PROPUESTAS_OK["propuestas"], ensure_ascii=False)
        )
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        assert res.status_code == 200
        assert len(res.get_json()["propuestas"]) == 2

    def test_clave_alternativa_se_acepta(self, client, docente):
        _fijar_respuesta(
            json.dumps({"sugerencias": PROPUESTAS_OK["propuestas"]}, ensure_ascii=False)
        )
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        assert res.status_code == 200

    def test_propuesta_sin_titulo_se_descarta(self, client, docente):
        _fijar_respuesta(
            json.dumps(
                {
                    "propuestas": [
                        {"resumen": "sin título, inservible"},
                        PROPUESTAS_OK["propuestas"][0],
                    ]
                },
                ensure_ascii=False,
            )
        )
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        assert res.status_code == 200
        assert len(res.get_json()["propuestas"]) == 1

    def test_claves_ausentes_se_rellenan_vacias(self, client, docente):
        """Con título basta; el resto no puede faltar en la salida."""
        _fijar_respuesta(
            json.dumps({"propuestas": [{"titulo": "Solo título"}]}, ensure_ascii=False)
        )
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        p = res.get_json()["propuestas"][0]
        assert p["titulo"] == "Solo título"
        assert p["resumen"] == ""

    def test_texto_no_json_devuelve_502(self, client, docente):
        _fijar_respuesta("Lo siento, no puedo ayudarte con eso.")
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        assert res.status_code == 502
        assert res.get_json()["error"] == "respuesta_ilegible"

    def test_sin_propuestas_utilizables_devuelve_502(self, client, docente):
        _fijar_respuesta(json.dumps({"propuestas": []}))
        res = client.post("/api/situaciones/sugerencias", json=PETICION)
        assert res.status_code == 502
        assert res.get_json()["error"] == "sin_propuestas"


class TestPrompt:
    """El prompt es la pieza que más se toca; conviene fijar sus invariantes."""

    def test_el_contexto_del_docente_llega_al_modelo(self, client, docente):
        _fijar_respuesta(json.dumps(PROPUESTAS_OK, ensure_ascii=False))
        client.post(
            "/api/situaciones/sugerencias",
            json={**PETICION, "contexto": "reciclaje en el patio"},
        )
        enviado = _cache[CLAVE_FAKE].llamadas[-1].user
        assert "reciclaje en el patio" in enviado
        assert "3º ESO" in enviado
        assert "Tecnología" in enviado

    def test_pide_json_al_proveedor(self, client, docente):
        _fijar_respuesta(json.dumps(PROPUESTAS_OK, ensure_ascii=False))
        client.post("/api/situaciones/sugerencias", json=PETICION)
        assert _cache[CLAVE_FAKE].llamadas[-1].response_format == "json"

    def test_prohibe_inventar_codigos_curriculares(self, client, docente):
        """Sin catálogo LOMLOE delante, cualquier código sería inventado."""
        _fijar_respuesta(json.dumps(PROPUESTAS_OK, ensure_ascii=False))
        client.post("/api/situaciones/sugerencias", json=PETICION)
        system = _cache[CLAVE_FAKE].llamadas[-1].system
        assert "NO debes" in system
        assert "criterios de evaluación" in system
