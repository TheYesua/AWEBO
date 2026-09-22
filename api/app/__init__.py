"""Factory de la aplicación Flask."""
from __future__ import annotations

from flask import Flask

from .config import Config
from .secretos import comprobar_configuracion
from .extensions import init_extensions, login_manager
from .api import register_blueprints


def create_app(config_object: type[Config] | None = None) -> Flask:
    """Construye la aplicación Flask siguiendo el patrón factory."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object or Config())

    # Lo primero después de cargar la configuración, y antes de que exista
    # nada más: si un secreto es un valor publicado, el proceso no arranca.
    # Va aquí y no al final porque una aplicación a medio construir que además
    # se niega a arrancar es más difícil de diagnosticar que una que se niega
    # antes de empezar. Ver el docstring de `comprobar_configuracion`.
    comprobar_configuracion(app.config)

    # Antes de las extensiones: el limitador de peticiones se registra ahí y
    # lee la IP del cliente, que sin esto sería la del proxy. Ver el comentario
    # de `PROXIES_DELANTE` en config.py — es la diferencia entre un límite por
    # visitante y un límite compartido por todos.
    proxies = app.config.get("PROXIES_DELANTE", 0)
    if proxies:
        from werkzeug.middleware.proxy_fix import ProxyFix

        # `x_host` y `x_prefix` a 0 a propósito: solo se confía en lo que hace
        # falta. `X-Forwarded-Host` lo usa Flask para construir URL absolutas, y
        # aceptarlo de fuera abre envenenamiento de enlaces —un atacante manda
        # la cabecera y el enlace de restablecer contraseña sale apuntando a su
        # servidor—. La URL base de los correos se configura aparte, en
        # `URL_BASE`, justo para no depender de esto.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies,
                                x_host=0, x_prefix=0)

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

    # Después de las extensiones y de los blueprints: su `before_request` tiene
    # que correr con la sesión ya disponible, y protege rutas que para entonces
    # ya están registradas.
    from . import csrf
    csrf.init_app(app)

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
