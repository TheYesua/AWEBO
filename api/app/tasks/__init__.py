"""Tareas asíncronas (Celery)."""
from __future__ import annotations

from typing import Any

from flask import g, has_request_context

from . import generacion  # noqa: F401 -- registro de tasks en Celery
from . import operaciones  # noqa: F401 -- idem
from . import correo  # noqa: F401 -- idem

__all__ = ["generacion", "operaciones", "correo", "encolar"]


def encolar(task, *args: Any, **kwargs: Any):
    """Encola una tarea Celery propagando el ``request_id`` actual.

    Es un envoltorio fino sobre ``task.apply_async`` que añade la
    cabecera ``X-Request-ID`` (tomada de ``flask.g``) a las cabeceras de
    Celery, para que el worker pueda correlacionar sus logs con la
    petición HTTP que originó la tarea.
    """
    headers = dict(kwargs.pop("headers", None) or {})
    if has_request_context():
        rid = g.get("request_id")
        if rid and "X-Request-ID" not in headers:
            headers["X-Request-ID"] = rid
    return task.apply_async(args=args, kwargs=kwargs, headers=headers or None)
