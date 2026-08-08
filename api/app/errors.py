"""Manejadores globales de errores que devuelven JSON o HTML según corresponda."""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException


def _es_peticion_api() -> bool:
    """Una petición debe responderse en JSON si va contra la API.

    Usamos el path como discriminador robusto (más fiable que el header
    Accept, que los navegadores envían a menudo con ``*/*``).
    """
    p = request.path or ""
    return (
        p.startswith("/api/")
        or p.startswith("/auth/")
        or p in {"/me", "/health"}
        or p.startswith("/me/")
    )


def register_error_handlers(app: Flask) -> None:
    """Registra los handlers globales (HTML para páginas, JSON para API)."""

    @app.errorhandler(ValidationError)
    def handle_pydantic_validation(exc: ValidationError):
        # ``include_context=False`` evita exponer objetos no serializables
        # (p.ej. la ValueError original lanzada en field_validator).
        return (
            jsonify(
                {
                    "error": "validacion",
                    "detalles": exc.errors(include_url=False, include_context=False),
                }
            ),
            400,
        )

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):
        if _es_peticion_api():
            return (
                jsonify({"error": exc.name.lower().replace(" ", "_"), "mensaje": exc.description}),
                exc.code,
            )
        # Página web → HTML accesible.
        plantilla = "errores/404.html" if exc.code == 404 else "errores/error.html"
        return render_template(plantilla, exc=exc), exc.code

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):  # noqa: BLE001
        app.logger.exception("Error no controlado")
        if _es_peticion_api():
            return jsonify({"error": "error_interno"}), 500
        return render_template("errores/error.html", exc=None), 500
