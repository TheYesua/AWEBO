"""La SdA queda en «generando» al encolar, no cuando el worker arranca.

EL FALLO QUE ESTO EVITA
------------------------
El estado lo ponía la propia tarea de Celery nada más empezar a ejecutarse.
Entre encolar y ejecutar hay una carrera, y **el navegador la perdía casi
siempre**: se creaba la SdA con «generar contenido con IA» marcado, el POST
respondía 202, la página del detalle se abría, pedía el estado y el worker aún
no había arrancado. La respuesta era `borrador`.

Ahí se acababa todo, porque el sondeo de progreso solo arranca
`if (sa.estado === 'generando')`. La página se quedaba en «Borrador» mientras
la generación corría por detrás, y el docente pulsaba «generar todo el
contenido» creyendo que no se había lanzado — encolando una segunda generación
de la misma SdA.

POR QUÉ NO LO VIO NINGUNO DE LOS 1148 TESTS
--------------------------------------------
Porque **en la batería Celery va en modo eager**: la tarea se ejecuta dentro
del propio POST, así que cuando la respuesta vuelve el estado ya es `generada`
y la carrera no existe. El modo que hace los tests rápidos y deterministas es
justo el que borra la condición que fallaba.

De ahí que estos tests **sustituyan `encolar`** por un doble que no ejecuta
nada: es la única forma de observar el estado en ese instante intermedio, que
es exactamente el que ve el navegador.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.situacion import SituacionAprendizaje


SA_BASE = {
    "titulo": "Explorando el barrio",
    "curso": "2º ESO",
    "materia": "Matemáticas",
    "idioma": "es",
    "num_sesiones": 3,
    "duracion_sesion_minutos": 55,
}


@pytest.fixture(autouse=True)
def _curriculo_disponible(sembrar_curriculo):
    """Generar exige currículo al que anclarse; sin esto sería un 422."""
    sembrar_curriculo()


@pytest.fixture
def _sin_worker():
    """`encolar` no ejecuta nada y devuelve un resultado con `id`.

    Reproduce el instante que el navegador ve de verdad: la tarea está en la
    cola y todavía no ha tocado la SdA.
    """
    class _Resultado:
        id = "tarea-de-prueba"

    with patch("app.api.situaciones.encolar", return_value=_Resultado()) as m:
        yield m


def _registrar_y_login(client, correo="carrera@test.com"):
    client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "ContraSegura1!",
            "nombre": "Docente", "comunidad_autonoma": "Ceuta",
            "centro_educativo": "IES Test",
        },
    )


class TestAlCrearConLaCasillaMarcada:

    def test_el_estado_ya_es_generando_cuando_responde(self, client, db, _sin_worker):
        """Es lo que la página del detalle lee nada más abrirse."""
        _registrar_y_login(client)
        res = client.post("/api/situaciones", json={**SA_BASE, "generar": True})
        assert res.status_code == 202
        assert res.get_json()["estado"] == "generando"

    def test_y_también_está_así_en_la_base_de_datos(self, client, db, _sin_worker):
        """No basta con que lo diga la respuesta: la página vuelve a
        preguntarlo con un GET, y ese lee de la base."""
        _registrar_y_login(client)
        sa_id = client.post(
            "/api/situaciones", json={**SA_BASE, "generar": True}
        ).get_json()["id_situacion"]

        detalle = client.get(f"/api/situaciones/{sa_id}").get_json()
        assert detalle["estado"] == "generando"

    def test_sin_la_casilla_se_queda_en_borrador(self, client, db, _sin_worker):
        """El contrapunto: marcar «generando» de más dejaría bloqueada una SdA
        que nadie va a generar."""
        _registrar_y_login(client)
        res = client.post("/api/situaciones", json=SA_BASE)
        assert res.status_code == 201
        assert res.get_json()["estado"] == "borrador"
        assert not _sin_worker.called


class TestAlPulsarGenerar:

    def test_el_estado_queda_generando_antes_de_que_arranque_el_worker(
        self, client, db, _sin_worker
    ):
        _registrar_y_login(client)
        sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]

        res = client.post(f"/api/situaciones/{sa_id}/generar")
        assert res.status_code == 202
        assert client.get(f"/api/situaciones/{sa_id}").get_json()["estado"] == "generando"

    def test_una_segunda_peticion_se_rechaza(self, client, db, _sin_worker):
        """Consecuencia buena de marcar el estado al encolar: la SdA queda
        protegida contra la doble generación desde el primer instante.

        Antes, las dos peticiones pasaban la comprobación de `ya_generando`
        porque ninguna había llegado a marcar nada — que es justo lo que
        ocurría cuando el docente pulsaba «generar» al ver «Borrador»."""
        _registrar_y_login(client)
        sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]

        assert client.post(f"/api/situaciones/{sa_id}/generar").status_code == 202
        segunda = client.post(f"/api/situaciones/{sa_id}/generar")
        assert segunda.status_code == 409
        assert segunda.get_json()["error"] == "ya_generando"


class TestAlRegenerarUnaSeccion:

    def test_tambien_queda_generando(self, client, db, _sin_worker):
        """El mismo endpoint tenía el mismo fallo, y se arregló con él.

        Regenerar una sección también dejaba la página sin sondear: se pedía,
        la respuesta decía «generando» y el GET siguiente contestaba lo que
        hubiera antes."""
        _registrar_y_login(client)
        sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]

        res = client.post(f"/api/situaciones/{sa_id}/regenerar/objetivos")
        assert res.status_code == 202
        assert client.get(f"/api/situaciones/{sa_id}").get_json()["estado"] == "generando"


class TestSiEncolarFalla:

    def test_la_situacion_vuelve_a_su_estado_anterior(self, client, db):
        """Dejarla en «generando» sin tarea que la atienda la bloquearía: la
        comprobación de `ya_generando` respondería 409 para siempre y no habría
        forma de desatascarla desde la interfaz.

        La primera versión de este test esperaba que la excepción se propagara
        —`TESTING = True` hace que Flask no la capture—, y **no se propaga**:
        la aplicación tiene un manejador propio para lo no controlado, así que
        el fallo sale como 500. Lo que importa comprobar no era la excepción
        sino lo que queda en la base después.
        """
        _registrar_y_login(client)
        sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]

        with patch("app.api.situaciones.encolar",
                   side_effect=RuntimeError("sin broker")):
            res = client.post(f"/api/situaciones/{sa_id}/generar")
        assert res.status_code == 500

        assert client.get(
            f"/api/situaciones/{sa_id}"
        ).get_json()["estado"] == SituacionAprendizaje.BORRADOR

    def test_y_se_puede_volver_a_intentar(self, client, db, _sin_worker):
        """La comprobación que de verdad importa: que no quede bloqueada."""
        _registrar_y_login(client)
        sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]

        with patch("app.api.situaciones.encolar",
                   side_effect=RuntimeError("sin broker")):
            client.post(f"/api/situaciones/{sa_id}/generar")

        assert client.post(f"/api/situaciones/{sa_id}/generar").status_code == 202
