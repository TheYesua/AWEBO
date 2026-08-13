"""Tests de las operaciones de bloque: resumir, expandir y traducir.

La invariante que gobierna las tres: **la operación cambia el texto, no la
forma**. El frontend pinta cada sección con un renderizador que espera unas
claves concretas; si una operación devuelve otra estructura, la sección deja de
renderizarse y acaba en el volcado JSON.

Se aplican sin previsualizar porque antes de sustituir se guarda una versión, y
deshacer la restaura. Eso hace que el test de deshacer sea tan importante como
el de la propia operación: sin él, aplicar directo sería irreversible.
"""
from __future__ import annotations

import json

import pytest

from app.ai import FakeProvider
from app.ai.factory import _cache, reset_cache
from app.prompts import operaciones as ops


CLAVE_FAKE = ("fake", "fake")

SA_BASE = {"titulo": "Situación de prueba", "curso": "2º ESO", "materia": "Matemáticas"}

#: Contenido con la forma real de la sección `descripcion`.
DESCRIPCION = {
    "texto": "Un texto largo y detallado sobre la situación de aprendizaje.",
    "producto_final": "Una maqueta",
    "pregunta_guia": "¿Cómo lo harías?",
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
def sa_con_descripcion(client, db):
    """SA con la sección `descripcion` ya generada."""
    # Se comprueba el registro: sin esta aserción, un fallo aquí no se ve y
    # reaparece varias líneas más abajo como un 401 desconcertante. Pasó:
    # `nombre` exige dos caracteres y el valor era de uno.
    alta = client.post(
        "/auth/register",
        json={
            "correo": "ops@test.com",
            "contrasena": "ContraSegura1!",
            "nombre": "Docente Operaciones", "comunidad_autonoma": "Ceuta",
        },
    )
    assert alta.status_code in (200, 201), alta.get_data(as_text=True)

    creada = client.post("/api/situaciones", json=SA_BASE)
    assert creada.status_code == 201, creada.get_data(as_text=True)
    id_sa = creada.get_json()["id_situacion"]

    from app.extensions import db as _db
    from app.models import SituacionAprendizaje

    sa = _db.session.get(SituacionAprendizaje, id_sa)
    sa.contenido = {
        "descripcion": {
            **DESCRIPCION,
            "_meta": {"proveedor": "fake", "modelo": "m", "version_prompt": "v1"},
        }
    }
    sa.estado = SituacionAprendizaje.GENERADA
    _db.session.commit()
    return id_sa


def _url(id_sa: int, seccion: str, operacion: str) -> str:
    return f"/api/situaciones/{id_sa}/secciones/{seccion}/{operacion}"


# ---------------------------------------------------------------------------
# Qué se puede aplicar y dónde
# ---------------------------------------------------------------------------


class TestAplicabilidad:
    @pytest.mark.parametrize("operacion", ops.OPERACIONES)
    def test_la_conexion_curricular_no_admite_ninguna(self, operacion):
        """Es una tabla de códigos del Real Decreto, no redacción libre.

        Resumirla la vacía, expandirla invita a inventar y traducirla rompe el
        anclaje normativo.
        """
        assert not ops.aplicable(operacion, "conexion_curricular")

    @pytest.mark.parametrize("operacion", ops.OPERACIONES)
    def test_la_descripcion_admite_las_tres(self, operacion):
        assert ops.aplicable(operacion, "descripcion")

    def test_el_endpoint_rechaza_una_operacion_no_aplicable(
        self, client, sa_con_descripcion
    ):
        res = client.post(_url(sa_con_descripcion, "conexion_curricular", "traducir"))
        assert res.status_code == 422
        assert res.get_json()["error"] == "operacion_no_aplicable"

    def test_operacion_inventada_devuelve_400(self, client, sa_con_descripcion):
        res = client.post(_url(sa_con_descripcion, "descripcion", "mejorar"))
        assert res.status_code == 400
        assert res.get_json()["error"] == "operacion_desconocida"

    def test_seccion_sin_contenido_devuelve_422(self, client, sa_con_descripcion):
        """No se puede resumir lo que aún no existe."""
        res = client.post(_url(sa_con_descripcion, "evaluacion", "resumir"))
        assert res.status_code == 422
        assert res.get_json()["error"] == "seccion_vacia"

    def test_requiere_sesion(self, client, db):
        assert client.post(_url(1, "descripcion", "resumir")).status_code == 401


# ---------------------------------------------------------------------------
# El prompt
# ---------------------------------------------------------------------------


class TestPrompt:
    def test_lleva_el_contenido_actual(self):
        peticion = ops.build(
            operacion=ops.RESUMIR, seccion="descripcion", contenido=DESCRIPCION
        )
        assert "Un texto largo y detallado" in peticion.user

    def test_prohibe_tocar_los_codigos_curriculares(self):
        """Vale para las tres, también para traducir."""
        for operacion in ops.OPERACIONES:
            peticion = ops.build(
                operacion=operacion, seccion="objetivos", contenido={"objetivos": []}
            )
            assert "CE1" in peticion.system, operacion

    def test_traducir_nombra_el_idioma_destino(self):
        peticion = ops.build(
            operacion=ops.TRADUCIR,
            seccion="descripcion",
            contenido=DESCRIPCION,
            idioma="fr",
        )
        assert "francés" in peticion.user

    def test_pide_json(self):
        peticion = ops.build(
            operacion=ops.EXPANDIR, seccion="descripcion", contenido=DESCRIPCION
        )
        assert peticion.response_format == "json"

    def test_operacion_no_soportada_es_error(self):
        with pytest.raises(ValueError):
            ops.build(operacion="inventada", seccion="descripcion", contenido={})


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------


class TestAplicacion:
    def test_sustituye_el_contenido(self, client, sa_con_descripcion):
        resumido = {**DESCRIPCION, "texto": "Un texto corto."}
        _fijar_respuesta(json.dumps(resumido, ensure_ascii=False))

        res = client.post(_url(sa_con_descripcion, "descripcion", "resumir"))
        assert res.status_code == 202

        sa = client.get(f"/api/situaciones/{sa_con_descripcion}").get_json()
        assert sa["contenido"]["descripcion"]["texto"] == "Un texto corto."

    def test_anota_la_operacion_en_los_metadatos(self, client, sa_con_descripcion):
        _fijar_respuesta(json.dumps(DESCRIPCION, ensure_ascii=False))
        client.post(_url(sa_con_descripcion, "descripcion", "expandir"))

        sa = client.get(f"/api/situaciones/{sa_con_descripcion}").get_json()
        meta = sa["contenido"]["descripcion"]["_meta"]
        assert meta["operacion"] == "expandir"
        assert "transformada_en" in meta

    def test_guarda_una_version_antes_de_tocar_nada(self, client, sa_con_descripcion):
        """Es lo que permite aplicar sin previsualizar."""
        _fijar_respuesta(json.dumps({**DESCRIPCION, "texto": "otro"}, ensure_ascii=False))
        client.post(_url(sa_con_descripcion, "descripcion", "resumir"))

        versiones = client.get(
            f"/api/situaciones/{sa_con_descripcion}/versiones"
        ).get_json()
        assert versiones, "debería existir al menos una versión"
        assert "resumir" in versiones[0]["descripcion_cambio"]


class TestEsquemaAlterado:
    """Si el modelo cambia la forma, se descarta el resultado.

    Sustituir el bloque por una estructura distinta dejaría la sección sin
    renderizar: el renderizador busca claves concretas y caería al volcado
    JSON. Vale más no aplicar nada.
    """

    def test_claves_distintas_no_se_aplican(self, client, sa_con_descripcion):
        _fijar_respuesta(json.dumps({"otra_cosa": "vaya"}, ensure_ascii=False))
        client.post(_url(sa_con_descripcion, "descripcion", "resumir"))

        sa = client.get(f"/api/situaciones/{sa_con_descripcion}").get_json()
        assert sa["contenido"]["descripcion"]["texto"] == DESCRIPCION["texto"]

    def test_respuesta_no_json_no_se_aplica(self, client, sa_con_descripcion):
        _fijar_respuesta("Lo siento, no puedo.")
        client.post(_url(sa_con_descripcion, "descripcion", "traducir"))

        sa = client.get(f"/api/situaciones/{sa_con_descripcion}").get_json()
        assert sa["contenido"]["descripcion"]["texto"] == DESCRIPCION["texto"]

    def test_falta_una_clave_no_se_aplica(self, client, sa_con_descripcion):
        """Perder `pregunta_guia` dejaría el callout sin pintar."""
        parcial = {"texto": "solo texto", "producto_final": "x"}
        _fijar_respuesta(json.dumps(parcial, ensure_ascii=False))
        client.post(_url(sa_con_descripcion, "descripcion", "resumir"))

        sa = client.get(f"/api/situaciones/{sa_con_descripcion}").get_json()
        assert sa["contenido"]["descripcion"] == {
            **DESCRIPCION,
            "_meta": sa["contenido"]["descripcion"]["_meta"],
        }


# ---------------------------------------------------------------------------
# Deshacer
# ---------------------------------------------------------------------------


class TestDeshacer:
    def test_restaura_el_contenido_anterior(self, client, sa_con_descripcion):
        _fijar_respuesta(json.dumps({**DESCRIPCION, "texto": "resumido"}, ensure_ascii=False))
        client.post(_url(sa_con_descripcion, "descripcion", "resumir"))

        res = client.post(
            f"/api/situaciones/{sa_con_descripcion}/secciones/descripcion/deshacer"
        )
        assert res.status_code == 200
        assert res.get_json()["contenido"]["descripcion"]["texto"] == DESCRIPCION["texto"]

    def test_sin_version_previa_devuelve_404(self, client, sa_con_descripcion):
        res = client.post(
            f"/api/situaciones/{sa_con_descripcion}/secciones/evaluacion/deshacer"
        )
        assert res.status_code == 404
        assert res.get_json()["error"] == "sin_version_previa"

    def test_solo_restaura_la_seccion_pedida(self, client, sa_con_descripcion):
        """Deshacer un resumen no debe llevarse por delante otras ediciones."""
        from app.extensions import db as _db
        from app.models import SituacionAprendizaje

        _fijar_respuesta(json.dumps({**DESCRIPCION, "texto": "resumido"}, ensure_ascii=False))
        client.post(_url(sa_con_descripcion, "descripcion", "resumir"))

        # Después de la operación, el docente añade otra sección a mano.
        sa = _db.session.get(SituacionAprendizaje, sa_con_descripcion)
        contenido = dict(sa.contenido)
        contenido["evaluacion"] = {"instrumentos": [{"nombre": "Rúbrica"}]}
        sa.contenido = contenido
        _db.session.commit()

        client.post(
            f"/api/situaciones/{sa_con_descripcion}/secciones/descripcion/deshacer"
        )

        final = client.get(f"/api/situaciones/{sa_con_descripcion}").get_json()
        assert final["contenido"]["descripcion"]["texto"] == DESCRIPCION["texto"]
        assert "evaluacion" in final["contenido"], (
            "deshacer una sección no debe borrar el trabajo hecho en otra"
        )
