"""Tests de propagación del request_id a Celery y de structlog contextvars."""
from __future__ import annotations

import structlog
from flask import g

from app.celery_app import celery_app
from app.tasks import encolar


@celery_app.task(name="awebo.test.captura_headers", bind=True)
def _captura_headers(self):
    """Tarea de prueba que captura headers + contextvars al ejecutarse."""
    return {
        "headers": dict(getattr(self.request, "headers", None) or {}),
        "request_id_ctx": structlog.contextvars.get_contextvars().get("request_id"),
    }


def test_encolar_propaga_request_id_a_la_tarea(app):
    """``encolar`` añade X-Request-ID a las cabeceras de la tarea Celery,
    y el signal task_prerun lo enlaza en structlog contextvars."""
    with app.test_request_context("/dummy", headers={"X-Request-ID": "abc-123"}):
        # before_request no se dispara con test_request_context: inyectamos
        # manualmente lo que haría el middleware.
        g.request_id = "abc-123"
        result = encolar(_captura_headers).get(timeout=5)

    assert result["headers"].get("X-Request-ID") == "abc-123"
    assert result["request_id_ctx"] == "abc-123"


def test_encolar_sin_contexto_de_peticion_no_falla():
    """Fuera de contexto HTTP, ``encolar`` no añade el header pero funciona."""
    result = encolar(_captura_headers).get(timeout=5)
    assert "X-Request-ID" not in result["headers"]
    # El signal sigue limpiando/binding: request_id queda como cadena vacía.
    assert result["request_id_ctx"] == ""
