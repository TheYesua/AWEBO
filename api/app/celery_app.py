"""Instancia compartida de Celery (sin dependencia de ``create_app``).

Este módulo se puede importar desde la web (para llamar ``.delay()`` sobre
las tareas) y desde el worker sin crear ciclos de importación. El broker
y el backend se leen directamente del entorno para mantener un único
punto de configuración.

El wrapping con ``Flask.app_context()`` (``FlaskTask``) se hace en
:mod:`app.celery_worker`, que SÍ importa ``create_app`` y solo se
ejecuta en el proceso worker.
"""
from __future__ import annotations

import structlog
from celery import Celery
from celery.schedules import crontab
from celery.signals import task_postrun, task_prerun

from .config import Config


celery_app = Celery(
    "awebo",
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.generacion",
        "app.tasks.operaciones",
        "app.tasks.mantenimiento",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Madrid",
    enable_utc=True,
    task_track_started=True,
    # Planificador. Lo consume el servicio ``beat`` del compose; el worker lo
    # ignora. Definirlo aquí y no en la línea de órdenes de beat mantiene el
    # calendario bajo control de versiones.
    beat_schedule={
        "purgar-cuentas-vencidas": {
            "task": "awebo.purgar_cuentas_vencidas",
            # A las 4:00, cuando no hay nadie generando. Diario y no cada
            # hora: el plazo es de 90 días, así que apurar el momento exacto
            # del borrado no aporta nada y sí multiplica las consultas.
            "schedule": crontab(hour=4, minute=0),
        },
    },
)
# Fijar como app "current" para que ``@shared_task`` y ``AsyncResult`` la
# usen por defecto en procesos que no sean el worker.
celery_app.set_default()


# ---------------------------------------------------------------------------
# Propagación de request_id desde las cabeceras de la tarea hasta los
# contextvars de structlog. Aplica tanto en producción (worker) como en
# tests (eager).
# ---------------------------------------------------------------------------


@task_prerun.connect
def _bind_request_id_from_headers(task_id, task, *_a, **_kw):
    rid = None
    headers = getattr(task.request, "headers", None) or {}
    if isinstance(headers, dict):
        rid = headers.get("X-Request-ID") or headers.get("x-request-id")
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=task_id,
        task_name=task.name,
        request_id=rid or "",
    )


@task_postrun.connect
def _clear_request_id(*_a, **_kw):
    structlog.contextvars.clear_contextvars()
