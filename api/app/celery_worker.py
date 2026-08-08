"""Entrypoint del worker de Celery.

Se arranca con:
    celery -A app.celery_worker:celery_app worker --loglevel=INFO

Este módulo toma la instancia compartida de :mod:`app.celery_app` (que la
web también usa para encolar tareas con ``.delay()``) y la envuelve con
``FlaskTask`` para que cada tarea se ejecute dentro de un
``app_context()`` — imprescindible para SQLAlchemy.

Además registra signals de Celery que propagan el ``request_id`` desde
las cabeceras de la tarea hasta los ``contextvars`` de structlog: así un
log emitido dentro de una tarea queda correlacionado con la petición HTTP
original que la encoló.
"""
from __future__ import annotations

from . import create_app
from .celery_app import celery_app  # los signals de request_id ya viven aquí


flask_app = create_app()


class FlaskTask(celery_app.Task):
    """Task base que garantiza un app_context de Flask en cada ejecución."""

    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)


celery_app.Task = FlaskTask


# Tarea de prueba (Fase 0). Registrada aquí para mantenerla junto a
# la configuración del worker; el resto viven en app.tasks.
@celery_app.task(name="awebo.ping")
def ping() -> str:
    return "pong"
