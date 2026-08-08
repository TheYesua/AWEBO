"""Tests del decorador ``@role_required``.

Las rutas auxiliares ``/_test/solo-admin`` y ``/_test/admin-o-docente``
están registradas en ``tests/conftest.py``.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import Rol, Usuario


def _crear_admin(db) -> str:
    """Crea un usuario administrador y devuelve su correo."""
    rol = db.session.scalar(select(Rol).where(Rol.nombre == "administrador"))
    user = Usuario(id_rol=rol.id_rol, correo="admin@test.com", nombre="Admin")
    user.set_password("Admin1234")
    db.session.add(user)
    db.session.commit()
    return "admin@test.com"


def test_role_required_sin_sesion_devuelve_401(client, db):
    res = client.get("/_test/solo-admin")
    assert res.status_code == 401
    assert res.get_json()["error"] == "no_autenticado"


def test_role_required_con_rol_correcto_devuelve_200(client, db):
    correo = _crear_admin(db)
    client.post("/auth/login", json={"correo": correo, "contrasena": "Admin1234"})
    res = client.get("/_test/solo-admin")
    assert res.status_code == 200


def test_role_required_con_rol_distinto_devuelve_403(client, db):
    # Registramos un docente normal
    client.post(
        "/auth/register",
        json={
            "correo": "doc@test.com",
            "contrasena": "Docente1234",
            "nombre": "Doc",
        },
    )
    res = client.get("/_test/solo-admin")
    assert res.status_code == 403
    assert res.get_json()["error"] == "permiso_denegado"


def test_role_required_acepta_varios_roles(client, db):
    client.post(
        "/auth/register",
        json={
            "correo": "doc2@test.com",
            "contrasena": "Docente1234",
            "nombre": "Doc",
        },
    )
    res = client.get("/_test/admin-o-docente")
    assert res.status_code == 200
