"""Tests de integración del CRUD de situaciones de aprendizaje (CU-03..CU-07)."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


SA_VALIDA = {
    "titulo": "Construyendo un puente",
    "curso": "2º ESO",
    "materia": "Tecnología",
    "comunidad_autonoma": "Ceuta",
    "descripcion": "Proyecto STEM con maquetas",
    "metodologia": "ABP",
    "num_sesiones": 6,
    "duracion_sesion_minutos": 55,
}


def _registrar_y_login(client, correo="docente@test.com"):
    """Registra (auto-login) y devuelve el id del usuario creado."""
    res = client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "Secreto123",
            "nombre": "Docente Test", "comunidad_autonoma": "Ceuta",
        },
    )
    assert res.status_code == 201, res.data
    return res.get_json()["id_usuario"]


@pytest.fixture()
def docente(client, db):
    return _registrar_y_login(client, "docente@test.com")


# ---------------------------------------------------------------------------
# CU-03 — Crear
# ---------------------------------------------------------------------------


class TestCrear:
    def test_crear_situacion_basica_devuelve_201(self, client, docente):
        res = client.post("/api/situaciones", json=SA_VALIDA)
        assert res.status_code == 201
        body = res.get_json()
        assert body["id_situacion"] > 0
        assert body["titulo"] == SA_VALIDA["titulo"]
        assert body["estado"] == "borrador"
        assert body["idioma"] == "es"
        assert body["contenido"] == {}
        assert body["id_situacion_origen"] is None

    def test_crear_sin_sesion_devuelve_401(self, client, db):
        res = client.post("/api/situaciones", json=SA_VALIDA)
        assert res.status_code == 401

    def test_titulo_demasiado_corto_devuelve_400(self, client, docente):
        res = client.post("/api/situaciones", json={**SA_VALIDA, "titulo": "x"})
        assert res.status_code == 400

    def test_idioma_no_soportado_devuelve_400(self, client, docente):
        res = client.post("/api/situaciones", json={**SA_VALIDA, "idioma": "de"})
        assert res.status_code == 400

    def test_num_sesiones_negativo_devuelve_400(self, client, docente):
        res = client.post("/api/situaciones", json={**SA_VALIDA, "num_sesiones": 0})
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Listar y filtrar
# ---------------------------------------------------------------------------


class TestListar:
    def test_listar_solo_devuelve_propias(self, client, db):
        # Docente A crea una SA
        _registrar_y_login(client, "a@test.com")
        client.post("/api/situaciones", json={**SA_VALIDA, "titulo": "De A"})
        client.post("/auth/logout")

        # Docente B inicia sesión
        _registrar_y_login(client, "b@test.com")
        res = client.get("/api/situaciones")
        assert res.status_code == 200
        # El listado pasó a devolver {total, situaciones} al paginarse.
        assert res.get_json() == {"total": 0, "situaciones": []}

    def test_filtrar_por_curso_y_materia(self, client, docente):
        client.post("/api/situaciones", json={**SA_VALIDA, "curso": "1º ESO"})
        client.post("/api/situaciones", json={**SA_VALIDA, "curso": "2º ESO"})
        client.post(
            "/api/situaciones",
            json={**SA_VALIDA, "curso": "1º ESO", "materia": "Lengua"},
        )

        res = client.get("/api/situaciones?curso=1%C2%BA%20ESO&materia=Tecnolog%C3%ADa")
        body = res.get_json()
        assert res.status_code == 200
        assert body["total"] == 1
        assert len(body["situaciones"]) == 1
        assert body["situaciones"][0]["curso"] == "1º ESO"

    def test_filtrar_por_busqueda_por_titulo(self, client, docente):
        client.post("/api/situaciones", json={**SA_VALIDA, "titulo": "Robótica básica"})
        client.post("/api/situaciones", json={**SA_VALIDA, "titulo": "Otra cosa"})

        res = client.get("/api/situaciones?q=robotica")
        # El filtro es ilike, debería capturar "Robótica" ignorando mayúsculas
        # pero NO ignorando tildes (PostgreSQL ilike no es accent-insensitive
        # sin extensión). Probamos con el texto exacto.
        res = client.get("/api/situaciones?q=Rob%C3%B3tica")
        assert res.status_code == 200
        body = res.get_json()
        assert body["total"] == 1
        assert "Robótica" in body["situaciones"][0]["titulo"]


# ---------------------------------------------------------------------------
# Obtener / autorizar / eliminar
# ---------------------------------------------------------------------------


class TestAcceso:
    def test_obtener_de_otro_devuelve_403(self, client, db):
        _registrar_y_login(client, "a@test.com")
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]
        client.post("/auth/logout")

        _registrar_y_login(client, "b@test.com")
        res = client.get(f"/api/situaciones/{sa_id}")
        assert res.status_code == 403
        assert res.get_json()["error"] == "permiso_denegado"

    def test_obtener_inexistente_devuelve_404(self, client, docente):
        res = client.get("/api/situaciones/9999")
        assert res.status_code == 404

    def test_eliminar_propia_devuelve_204(self, client, docente):
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]
        res = client.delete(f"/api/situaciones/{sa_id}")
        assert res.status_code == 204
        # Ya no existe
        assert client.get(f"/api/situaciones/{sa_id}").status_code == 404


# ---------------------------------------------------------------------------
# CU-04, CU-07 — Editar y versionado automático
# ---------------------------------------------------------------------------


class TestActualizarYVersionado:
    def test_actualizar_titulo_persiste_y_crea_version(self, client, docente):
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]

        res = client.put(
            f"/api/situaciones/{sa_id}",
            json={
                "titulo": "Construyendo un puente (revisado)",
                "descripcion_cambio": "Cambio de título",
            },
        )
        assert res.status_code == 200
        assert res.get_json()["titulo"] == "Construyendo un puente (revisado)"

        # Debe existir una versión con el título antiguo
        versiones = client.get(f"/api/situaciones/{sa_id}/versiones").get_json()
        assert len(versiones) == 1
        v = versiones[0]
        assert v["numero_version"] == 1
        assert v["descripcion_cambio"] == "Cambio de título"
        assert v["contenido"]["titulo"] == "Construyendo un puente"

    def test_dos_cambios_generan_dos_versiones_secuenciales(self, client, docente):
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]

        client.put(f"/api/situaciones/{sa_id}", json={"titulo": "v2"})
        client.put(f"/api/situaciones/{sa_id}", json={"titulo": "v3"})

        versiones = client.get(f"/api/situaciones/{sa_id}/versiones").get_json()
        assert [v["numero_version"] for v in versiones] == [2, 1]

    def test_put_sin_cambios_no_crea_version(self, client, docente):
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]
        client.put(f"/api/situaciones/{sa_id}", json={})
        versiones = client.get(f"/api/situaciones/{sa_id}/versiones").get_json()
        assert versiones == []

    def test_actualizar_a_estado_finalizada(self, client, docente):
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]
        res = client.put(f"/api/situaciones/{sa_id}", json={"estado": "finalizada"})
        assert res.status_code == 200
        assert res.get_json()["estado"] == "finalizada"

    def test_estado_no_valido_devuelve_400(self, client, docente):
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]
        res = client.put(f"/api/situaciones/{sa_id}", json={"estado": "publicada"})
        assert res.status_code == 400

    def test_actualizar_de_otro_devuelve_403(self, client, db):
        _registrar_y_login(client, "a@test.com")
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]
        client.post("/auth/logout")
        _registrar_y_login(client, "b@test.com")
        res = client.put(f"/api/situaciones/{sa_id}", json={"titulo": "hack"})
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Duplicar
# ---------------------------------------------------------------------------


class TestDuplicar:
    def test_duplicar_crea_copia_independiente(self, client, docente):
        original_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()[
            "id_situacion"
        ]

        res = client.post(f"/api/situaciones/{original_id}/duplicar", json={})
        assert res.status_code == 201
        copia = res.get_json()
        assert copia["id_situacion"] != original_id
        assert copia["titulo"].endswith("(copia)")
        assert copia["estado"] == "borrador"
        assert copia["id_situacion_origen"] is None  # una copia no es adaptación

        # Modificar la copia no afecta al original
        client.put(f"/api/situaciones/{copia['id_situacion']}", json={"titulo": "X"})
        original = client.get(f"/api/situaciones/{original_id}").get_json()
        assert original["titulo"] == SA_VALIDA["titulo"]

    def test_duplicar_con_titulo_explicito(self, client, docente):
        sa_id = client.post("/api/situaciones", json=SA_VALIDA).get_json()["id_situacion"]
        res = client.post(
            f"/api/situaciones/{sa_id}/duplicar", json={"titulo": "Mi nueva versión"}
        )
        assert res.status_code == 201
        assert res.get_json()["titulo"] == "Mi nueva versión"

