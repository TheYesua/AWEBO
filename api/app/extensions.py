"""Inicialización de extensiones Flask compartidas por toda la app."""
from __future__ import annotations

import redis
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
session_ext = Session()
redis_client: redis.Redis | None = None


def _rate_key() -> str:
    """Clave de rate limit: ID de usuario si está autenticado, IP en otro caso.

    Así un atacante no puede agotar la cuota de toda una red corporativa
    detrás de NAT con peticiones autenticadas como un usuario concreto.
    """
    try:
        if current_user.is_authenticated:
            return f"user:{current_user.id_usuario}"
    except Exception:
        pass
    return f"ip:{get_remote_address()}"


# Importable desde los blueprints como ``from ..extensions import limiter``
# y se aplica con ``@limiter.limit("5 per minute")``.
limiter = Limiter(
    key_func=_rate_key,
    default_limits=[],   # se configuran a través de app.config["RATELIMIT_DEFAULT"]
)


def init_extensions(app: Flask) -> None:
    """Registra las extensiones contra la aplicación."""
    global redis_client

    db.init_app(app)
    migrate.init_app(app, db)

    # Sesiones server-side en Redis
    redis_client = redis.Redis.from_url(app.config["SESSION_REDIS_URL"])
    app.config["SESSION_REDIS"] = redis_client
    session_ext.init_app(app)

    # Auth
    login_manager.init_app(app)

    @login_manager.unauthorized_handler
    def _unauthorized():
        from flask import jsonify

        return jsonify({"error": "no_autenticado"}), 401

    # Rate limiting. Flask-Limiter lee RATELIMIT_* directamente de app.config.
    limiter.init_app(app)
    if not app.config.get("RATELIMIT_ENABLED", True):
        # En tests: limiter sigue importable pero no aplica ningún límite.
        limiter.enabled = False

    # CORS
    origins = app.config.get("CORS_ORIGINS") or []
    if origins:
        CORS(
            app,
            resources={r"/api/*": {"origins": origins}, r"/auth/*": {"origins": origins}},
            supports_credentials=True,
        )
