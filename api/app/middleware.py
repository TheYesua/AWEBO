"""Middlewares de aplicación: request-id, headers de seguridad."""
from __future__ import annotations

import uuid

import structlog
from flask import Flask, g, request


def register_middlewares(app: Flask) -> None:
    """Registra before/after_request globales."""

    @app.before_request
    def _inject_request_id() -> None:
        # Prioridad: cabecera del cliente (para trazabilidad de proxies
        # o frontends) → auto-generado si no llega.
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = rid
        # Enlaza el request_id en los contextvars de structlog: a partir
        # de aquí, CUALQUIER log emitido durante la petición incluirá la
        # clave ``request_id`` sin tener que pasarla a mano.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)

    @app.after_request
    def _add_response_headers(response):
        # Siempre devolvemos el request-id para que el cliente pueda
        # correlacionar logs o errores con el servidor.
        response.headers["X-Request-ID"] = g.get("request_id", "")
        # Seguridad adicional
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.teardown_request
    def _clear_log_context(_exc):
        # Evita que el request_id de una petición se filtre a la siguiente
        # si el worker WSGI reutiliza el hilo (raro pero documentado).
        structlog.contextvars.clear_contextvars()
