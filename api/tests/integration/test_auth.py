"""Tests de integración de los endpoints de autenticación.

Cubren los casos de uso CU-01 (registro), CU-02 (login), CU-08 (logout)
y CU-09 (consulta y edición del propio perfil).
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


VALIDOS = {
    "correo": "ana.lopez@example.com",
    "contrasena": "Secreto123",
    "nombre": "Ana López", "comunidad_autonoma": "Ceuta",
    "centro_educativo": "IES Ceuta",
    "especialidad": "Tecnología",
    "comunidad_autonoma": "Ceuta",
}


@pytest.fixture()
def docente_registrado(client, db):
    """Registra un docente y devuelve el cliente con sesión abierta."""
    res = client.post("/auth/register", json=VALIDOS)
    assert res.status_code == 201
    return res.get_json()


# ---------------------------------------------------------------------------
# CU-01 — Registro de usuario
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registro_correcto_devuelve_201_y_perfil(self, client, db):
        res = client.post("/auth/register", json=VALIDOS)
        assert res.status_code == 201
        body = res.get_json()
        assert body["correo"] == "ana.lopez@example.com"
        assert body["rol"] == "docente"
        assert body["id_usuario"] > 0
        # Nunca debe exponerse el hash
        assert "contrasena_hash" not in body
        assert "contrasena" not in body

    def test_registro_con_correo_duplicado_devuelve_409(self, client, db):
        client.post("/auth/register", json=VALIDOS)
        res = client.post("/auth/register", json=VALIDOS)
        assert res.status_code == 409
        assert res.get_json()["error"] == "correo_duplicado"

    def test_correo_se_normaliza_a_minusculas(self, client, db):
        payload = {**VALIDOS, "correo": "ANA.lopez@Example.com"}
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 201
        assert res.get_json()["correo"] == "ana.lopez@example.com"

    def test_contrasena_corta_devuelve_400(self, client, db):
        payload = {**VALIDOS, "contrasena": "abc12"}
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 400

    def test_contrasena_sin_digito_devuelve_400(self, client, db):
        payload = {**VALIDOS, "contrasena": "soloLetras"}
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 400

    def test_correo_invalido_devuelve_400(self, client, db):
        payload = {**VALIDOS, "correo": "no-es-email"}
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 400

    def test_campos_extra_no_permitidos_devuelve_400(self, client, db):
        payload = {**VALIDOS, "rol_nombre": "administrador"}
        res = client.post("/auth/register", json=payload)
        # No se permite que el cliente decida su rol
        assert res.status_code == 400

    def test_registro_inicia_sesion_automaticamente(self, client, db):
        client.post("/auth/register", json=VALIDOS)
        res = client.get("/me")
        assert res.status_code == 200
        assert res.get_json()["correo"] == VALIDOS["correo"]


# ---------------------------------------------------------------------------
# CU-02 — Login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_correcto_devuelve_200(self, client, db, docente_registrado):
        # Limpiamos sesión del auto-login del registro
        client.post("/auth/logout")
        res = client.post(
            "/auth/login",
            json={"correo": VALIDOS["correo"], "contrasena": VALIDOS["contrasena"]},
        )
        assert res.status_code == 200
        assert res.get_json()["correo"] == VALIDOS["correo"]

    def test_login_con_password_incorrecta_devuelve_401(self, client, db, docente_registrado):
        client.post("/auth/logout")
        res = client.post(
            "/auth/login",
            json={"correo": VALIDOS["correo"], "contrasena": "incorrecta1"},
        )
        assert res.status_code == 401
        assert res.get_json()["error"] == "credenciales_invalidas"

    def test_login_con_correo_inexistente_devuelve_401_mismo_error(self, client, db):
        # Mismo error que password incorrecta para evitar enumeración
        res = client.post(
            "/auth/login",
            json={"correo": "no-existe@x.com", "contrasena": "loquesea1"},
        )
        assert res.status_code == 401
        assert res.get_json()["error"] == "credenciales_invalidas"

    def test_login_si_ya_autenticado_devuelve_400(self, client, db, docente_registrado):
        # docente_registrado ya autenticó vía registro
        res = client.post(
            "/auth/login",
            json={"correo": VALIDOS["correo"], "contrasena": VALIDOS["contrasena"]},
        )
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# CU-08 — Logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_logout_invalida_sesion(self, client, db, docente_registrado):
        # Tras logout no se puede acceder a /me
        res = client.post("/auth/logout")
        assert res.status_code == 200
        res = client.get("/me")
        assert res.status_code == 401

    def test_logout_sin_sesion_devuelve_401(self, client, db):
        res = client.post("/auth/logout")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# CU-09 — Perfil propio
# ---------------------------------------------------------------------------


class TestPerfil:
    def test_get_me_devuelve_perfil(self, client, db, docente_registrado):
        res = client.get("/me")
        assert res.status_code == 200
        body = res.get_json()
        assert body["correo"] == VALIDOS["correo"]
        assert body["nombre"] == VALIDOS["nombre"]
        assert body["rol"] == "docente"
        assert "contrasena_hash" not in body

    def test_put_me_actualiza_campos_permitidos(self, client, db, docente_registrado):
        res = client.put(
            "/me",
            json={"nombre": "Ana López Pérez", "comunidad_autonoma": "Ceuta", "centro_educativo": "IES Otro"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["nombre"] == "Ana López Pérez"
        assert body["centro_educativo"] == "IES Otro"
        # Persistencia
        res2 = client.get("/me")
        assert res2.get_json()["nombre"] == "Ana López Pérez"

    def test_put_me_con_campo_no_permitido_devuelve_400(self, client, db, docente_registrado):
        res = client.put("/me", json={"correo": "otro@x.com"})
        assert res.status_code == 400

    def test_get_me_sin_sesion_devuelve_401(self, client, db):
        res = client.get("/me")
        assert res.status_code == 401
