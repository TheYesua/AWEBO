"""Endpoint de healthcheck que verifica BD y Redis."""
from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import text

from .. import extensions
from ..ai.factory import get_provider
from ..extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    """Devuelve el estado de los servicios externos críticos."""
    status: dict[str, str] = {"app": "ok"}
    http_code = 200

    # Postgres
    try:
        db.session.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        status["database"] = f"error: {exc.__class__.__name__}"
        http_code = 503

    # Redis (sesiones)
    try:
        if extensions.redis_client is None:
            raise RuntimeError("redis client not initialised")
        extensions.redis_client.ping()
        status["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        status["redis"] = f"error: {exc.__class__.__name__}"
        http_code = 503

    # IA: se pregunta al proveedor realmente activo. Antes se devolvía
    # OPENAI_MODEL a secas, que mentía con AI_PROVIDER=gemini y ocultaba los
    # casos en que la factoría cae a FakeProvider por faltar una API key.
    # No instancia nada nuevo: get_provider() cachea por proceso.
    try:
        proveedor = get_provider()
        status["ai_provider"] = proveedor.nombre
        status["model"] = proveedor.modelo
    except Exception as exc:  # noqa: BLE001
        # Una IA mal configurada no debe tumbar el healthcheck: la app sigue
        # sirviendo CRUD y exportaciones sin ella.
        status["ai_provider"] = f"error: {exc.__class__.__name__}"
        status["model"] = ""

    return jsonify(status), http_code
