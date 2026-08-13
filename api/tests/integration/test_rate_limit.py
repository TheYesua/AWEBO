"""Tests de integración de rate limiting (Fase 7).

Los tests de la suite general corren con ``RATELIMIT_ENABLED = False``
para no ralentizarlos. Aquí levantamos una app temporal con el limiter
activo y usamos un namespace de Redis único para no contaminar otros tests.
"""
from __future__ import annotations

import pytest

from app import create_app
from app.config import Config
from app.extensions import db as _db
from app.seeds import seed_ods, seed_roles


def _redirigir_a_test_db(uri: str) -> str:
    import re
    return re.sub(r"/[^/?]+(\?.*)?$", lambda m: "/awebo_test" + (m.group(1) or ""), uri, count=1)


class RateLimitConfig(Config):
    """Config que deja el rate limiter activo para estos tests."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = _redirigir_a_test_db(Config.SQLALCHEMY_DATABASE_URI)
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "redis://redis:6379/5"  # DB separado para tests
    RATELIMIT_DEFAULT = "100 per minute"
    AI_PROVIDER = "fake"
    OPENAI_API_KEY = ""


def _app_rl():
    """App fresca con rate limiting activo."""
    app = create_app(RateLimitConfig)
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        seed_roles()
        seed_ods()
    return app


def _limpiar_db(app):
    with app.app_context():
        from sqlalchemy import text

        TABLAS = (
            "version",
            "situacion_competencia",
            "situacion_criterio",
            "situacion_saber",
            "situacion_ods",
            "situacion_aprendizaje",
            "criterio_evaluacion",
            "saber_basico",
            "competencia",
            "usuario",
        )
        _db.session.execute(
            text("TRUNCATE TABLE " + ", ".join(TABLAS) + " RESTART IDENTITY CASCADE")
        )
        _db.session.commit()


def _limpiar_redis():
    import redis

    redis.from_url("redis://redis:6379/5").flushdb()


def _register(client, correo):
    return client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "ContraSegura1!",
            "nombre": "Docente", "comunidad_autonoma": "Ceuta",
            "centro_educativo": "IES Test",
        },
    )


# ---------------------------------------------------------------------------
# Endpoints sensibles
# ---------------------------------------------------------------------------


def test_login_rate_limit_bloquea_despues_de_10_por_minuto():
    """10 peticiones de login/minuto → la 11ª devuelve 429."""
    app = _app_rl()
    _limpiar_db(app)
    _limpiar_redis()

    with app.test_client() as c:
        for i in range(10):
            res = c.post(
                "/auth/login",
                json={"correo": f"user{i}@t.com", "contrasena": "wrong"},
            )
            # 401 es esperado (credenciales malas), pero NO 429
            assert res.status_code == 401, f"Falló en intento {i}: {res.status_code}"

        # 11ª petición → 429 Too Many Requests
        res = c.post(
            "/auth/login",
            json={"correo": "overflow@t.com", "contrasena": "wrong"},
        )
        assert res.status_code == 429


def test_register_rate_limit_bloquea_despues_de_5_por_hora():
    """El endpoint de registro auto-loguea al nuevo usuario, por lo que
    un cliente persistente cambiaría la clave de rate-limit de IP a user:N.
    Usamos un cliente nuevo en cada petición para forzar clave IP."""
    app = _app_rl()
    _limpiar_db(app)
    _limpiar_redis()

    for i in range(5):
        with app.test_client() as c:
            res = _register(c, f"reg{i}@t.com")
            assert res.status_code == 201, f"Intento {i}: {res.status_code}"

    with app.test_client() as c:
        res = _register(c, "overflow@t.com")
        assert res.status_code == 429


def test_exportar_pdf_sin_autenticar_no_gasta_limite():
    """Endpoints que requieren login no consumen cuota si devuelven 401."""
    app = _app_rl()
    _limpiar_db(app)
    _limpiar_redis()

    with app.test_client() as c:
        for _ in range(15):
            res = c.get("/api/situaciones/1/exportar?formato=pdf")
            assert res.status_code == 401

        # La 16ª sigue siendo 401 porque @login_required va antes que @limiter.limit.
        res = c.get("/api/situaciones/1/exportar?formato=pdf")
        assert res.status_code == 401


def test_headers_rate_limit_presentes():
    """Flask-Limiter añade cabeceras X-RateLimit-* cuando está activo."""
    app = _app_rl()
    _limpiar_db(app)
    _limpiar_redis()

    with app.test_client() as c:
        res = c.post(
            "/auth/login",
            json={"correo": "hdr@test.com", "contrasena": "wrong"},
        )
        assert res.status_code == 401
        assert "X-RateLimit-Limit" in res.headers
        assert "X-RateLimit-Remaining" in res.headers


def test_request_id_se_propaga():
    """Cada respuesta incluye X-Request-ID único."""
    app = _app_rl()

    with app.test_client() as c:
        res1 = c.get("/")
        rid1 = res1.headers.get("X-Request-ID")
        assert rid1 and len(rid1) == 36  # UUID

        res2 = c.get("/")
        rid2 = res2.headers.get("X-Request-ID")
        assert rid2 != rid1


def test_request_id_cliente_se_respeta():
    """Si el cliente envía X-Request-ID, se devuelve el mismo."""
    app = _app_rl()

    with app.test_client() as c:
        rid = "mi-trace-id-123"
        res = c.get("/", headers={"X-Request-ID": rid})
        assert res.headers.get("X-Request-ID") == rid
