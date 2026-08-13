"""Factory de la aplicación Flask."""
from __future__ import annotations

from flask import Flask

from .config import Config
from .extensions import init_extensions, login_manager
from .api import register_blueprints


def create_app(config_object: type[Config] | None = None) -> Flask:
    """Construye la aplicación Flask siguiendo el patrón factory."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object or Config())

    # Logging estructurado: configurado lo antes posible para que TODO
    # mensaje (incluidos los de extensiones) salga ya con formato JSON.
    from .logging_config import configure_logging
    configure_logging(
        json_logs=app.config.get("LOG_JSON"),
        level=app.config.get("LOG_LEVEL", "INFO"),
    )

    init_extensions(app)
    _register_user_loader()
    # Importa los modelos para que SQLAlchemy y Alembic los conozcan.
    # noqa: F401 — efecto de side-effect intencional.
    from . import models  # noqa: F401
    register_blueprints(app)

    from .errors import register_error_handlers
    register_error_handlers(app)

    from .cli import register_cli
    register_cli(app)

    from .middleware import register_middlewares
    register_middlewares(app)

    from . import temas
    temas.init_app(app)

    from . import i18n
    i18n.init_app(app)

    # Lo último, y sin poder tumbar el arranque: si la base de datos va por
    # detrás del código, deja en el log el comando que lo arregla. Ver el
    # docstring de ese módulo — un 500 en todas las páginas se parece mucho a
    # «he roto algo gordo» cuando lo que falta es una orden de una línea.
    from . import migraciones_pendientes
    migraciones_pendientes.comprobar(app)

    return app


def _register_user_loader() -> None:
    """Registra el callback que Flask-Login usa para cargar al usuario."""
    from .models.usuario import Usuario
    from .extensions import db

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            usuario = db.session.get(Usuario, int(user_id))
        except (TypeError, ValueError):
            return None
        # Una cuenta con lápida no carga, y eso cierra de inmediato las
        # sesiones que tuviera abiertas. Sin esta comprobación, dar de baja a
        # alguien no lo echaría: su cookie de sesión seguiría siendo válida
        # hasta caducar, y mientras tanto podría seguir trabajando en una
        # cuenta que el administrador cree eliminada.
        if usuario is not None and usuario.esta_eliminado:
            return None
        return usuario
