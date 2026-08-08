"""Endpoint de polling del estado de una tarea Celery.

Se mantiene genérico (``/api/tasks/<task_id>``) para reutilizarlo desde
distintos flujos (generación completa, regeneración de sección,
exportación, etc.). Solo expone los campos necesarios al frontend:
estado + progreso + resultado/resumen.
"""
from __future__ import annotations

from flask import Blueprint, jsonify
from flask_login import login_required

from ..celery_app import celery_app


bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


# Estado estándar de Celery (strings). PROGRESO lo emiten nuestras tareas
# con update_state para publicar avance.
_ESTADOS_VIVOS = {"PENDING", "STARTED", "PROGRESO", "RETRY"}


@bp.get("/<task_id>")
@login_required
def obtener(task_id: str):
    """Devuelve el estado de una tarea Celery por id."""
    async_result = celery_app.AsyncResult(task_id)
    estado_raw = async_result.state
    listo = async_result.ready()

    # Normalizamos el estado: si la tarea ya terminó con éxito pero el
    # backend todavía conserva el último PROGRESO, reportamos SUCCESS.
    if listo and async_result.successful():
        estado = "SUCCESS"
    elif listo and async_result.failed():
        estado = "FAILURE"
    else:
        estado = estado_raw

    payload: dict = {
        "task_id": task_id,
        "estado": estado,
        "listo": listo,
    }

    if estado == "SUCCESS":
        # .result/.get() devuelve el valor retornado por la task.
        payload["resultado"] = async_result.result
    elif estado == "FAILURE":
        info = async_result.result
        payload["error"] = (
            info
            if isinstance(info, dict)
            else {"mensaje": str(info) if info else "desconocido"}
        )
    else:
        info = async_result.info
        if isinstance(info, dict):
            payload["progreso"] = {
                "seccion_actual": info.get("seccion_actual"),
                "completadas": info.get("completadas"),
                "total": info.get("total"),
            }

    return jsonify(payload), 200
