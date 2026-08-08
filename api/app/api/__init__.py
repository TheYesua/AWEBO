"""Registro centralizado de blueprints."""
from __future__ import annotations

from flask import Flask

from .admin import bp as admin_bp
from .auth import bp as auth_bp
from .curriculo import bp as curriculo_bp
from .health import bp as health_bp
from .me import bp as me_bp
from .pages import bp as pages_bp
from .situaciones import bp as situaciones_bp
from .tasks import bp as tasks_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(me_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(situaciones_bp)
    app.register_blueprint(curriculo_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(admin_bp)
