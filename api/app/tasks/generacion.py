"""Tareas Celery para generar el contenido de una Situación de Aprendizaje.

Orquestación de la sección-por-sección:

1. Se carga el SA y se construye el contexto curricular.
2. Por cada sección del registro :data:`app.prompts.SECCIONES` se arma el
   prompt, se invoca al LLM y se intenta parsear como JSON.
3. El contenido se va mergeando en ``sa.contenido`` bajo la clave de la
   sección, con metadatos (``_meta``) de versión, proveedor y modelo.
4. El progreso se publica en el backend de resultados de Celery
   (``update_state``) para que el endpoint de polling lo muestre.

Se exponen dos tareas:

* ``generar_situacion_completa(id_situacion)`` — itera todas las secciones.
* ``generar_seccion(id_situacion, seccion)`` — regenera una sola sección
  (CU-05: "regenerar parte del contenido").
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from celery import shared_task, states
from celery.exceptions import Ignore

from ..ai import LLMProviderError
from ..ai.factory import get_provider_para
from ..ai.provider import LLMRequest, LLMResponse
from ..extensions import db
from ..models import SituacionAprendizaje
from ..prompts import ORDEN_SECCIONES, SECCIONES, construir_contexto


logger = structlog.get_logger("tasks.generacion")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cargar_sa(id_situacion: int) -> SituacionAprendizaje:
    sa = db.session.get(SituacionAprendizaje, id_situacion)
    if sa is None:
        raise ValueError(f"SituacionAprendizaje id={id_situacion} no existe")
    return sa


def _ejecutar_seccion(
    nombre: str, ctx, provider
) -> tuple[dict[str, Any], LLMResponse]:
    """Invoca al LLM para una sección y devuelve ``(payload, response)``."""
    version, build = SECCIONES[nombre]
    peticion: LLMRequest = build(ctx)
    respuesta: LLMResponse = provider.generar(peticion)

    # Intentar parsear JSON. Si falla, guardamos el texto crudo para que
    # el docente pueda ver qué devolvió el modelo y corregir.
    try:
        payload = json.loads(respuesta.texto)
    except json.JSONDecodeError:
        logger.warning(
            "seccion_no_json",
            seccion=nombre,
            mensaje="LLM devolvió texto no-JSON; se guarda como texto crudo",
        )
        payload = {"_error_parseo": True, "texto_crudo": respuesta.texto}

    # Metadatos de trazabilidad.
    payload["_meta"] = {
        "seccion": nombre,
        "version_prompt": version,
        "proveedor": respuesta.proveedor,
        "modelo": respuesta.modelo,
        "tokens_prompt": respuesta.tokens_prompt,
        "tokens_respuesta": respuesta.tokens_respuesta,
        "generada_en": _ahora_iso(),
    }
    return payload, respuesta


def _fusionar_seccion(
    sa: SituacionAprendizaje, nombre: str, payload: dict[str, Any]
) -> None:
    """Actualiza ``sa.contenido`` con la nueva sección y marca el dirty flag."""
    # ``contenido`` es JSONB; SQLAlchemy solo detecta cambios si reasignamos.
    contenido = dict(sa.contenido or {})
    contenido[nombre] = payload
    sa.contenido = contenido


# ---------------------------------------------------------------------------
# Tareas Celery
# ---------------------------------------------------------------------------


@shared_task(
    name="awebo.generar_situacion_completa",
    bind=True,
    autoretry_for=(LLMProviderError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=2,
)
def generar_situacion_completa(self, id_situacion: int) -> dict[str, Any]:
    """Genera TODAS las secciones de la SA, una a una."""
    sa = _cargar_sa(id_situacion)

    # Marcar estado de generación en BD (idempotente).
    sa.estado = SituacionAprendizaje.GENERANDO
    db.session.commit()

    # El proveedor sale de las preferencias del PROPIETARIO de la SA, no de la
    # configuración del proceso. Se lee aquí, dentro de la tarea, y no se pasa
    # como argumento: el worker es otro proceso, sin sesión ni petición, pero
    # sí tiene la SA en la mano y la SA conoce a su usuario.
    provider = get_provider_para(sa.usuario)
    ctx = construir_contexto(sa)

    total = len(ORDEN_SECCIONES)
    resumen: dict[str, Any] = {
        "id_situacion": id_situacion,
        "secciones": [],
        "tokens_totales": {"prompt": 0, "respuesta": 0},
    }

    try:
        for indice, nombre in enumerate(ORDEN_SECCIONES, start=1):
            self.update_state(
                state="PROGRESO",
                meta={
                    "id_situacion": id_situacion,
                    "seccion_actual": nombre,
                    "completadas": indice - 1,
                    "total": total,
                },
            )
            payload, respuesta = _ejecutar_seccion(nombre, ctx, provider)
            _fusionar_seccion(sa, nombre, payload)
            db.session.commit()

            resumen["secciones"].append({
                "nombre": nombre,
                "proveedor": respuesta.proveedor,
                "modelo": respuesta.modelo,
            })
            resumen["tokens_totales"]["prompt"] += respuesta.tokens_prompt or 0
            resumen["tokens_totales"]["respuesta"] += respuesta.tokens_respuesta or 0

        sa.estado = SituacionAprendizaje.GENERADA
        db.session.commit()
        resumen["completadas"] = total
        resumen["total"] = total
        # Escritura explícita de SUCCESS en el backend. En modo non-eager
        # Celery ya lo hace tras el return, pero así garantizamos que el
        # último PROGRESO no prevalezca en el backend de Redis (quirk en
        # eager, pero también hace más rápido el polling en prod).
        self.backend.mark_as_done(self.request.id, resumen, request=self.request)
        return resumen

    except LLMProviderError:
        # autoretry_for la capturará; dejamos rastro y relanzamos.
        db.session.rollback()
        sa = _cargar_sa(id_situacion)
        sa.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()
        raise
    except Exception as exc:
        logger.exception("fallo_generacion", id_situacion=id_situacion)
        db.session.rollback()
        sa = _cargar_sa(id_situacion)
        sa.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()
        # No reintentamos errores desconocidos; marcamos la task como fallida.
        self.update_state(
            state=states.FAILURE,
            meta={"exc_type": type(exc).__name__, "exc_message": str(exc)},
        )
        raise Ignore()


@shared_task(
    name="awebo.generar_seccion",
    bind=True,
    autoretry_for=(LLMProviderError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=2,
)
def generar_seccion(self, id_situacion: int, seccion: str) -> dict[str, Any]:
    """Regenera UNA sección concreta (CU-05)."""
    if seccion not in SECCIONES:
        raise ValueError(f"Sección desconocida: {seccion}")

    sa = _cargar_sa(id_situacion)
    estado_previo = sa.estado
    sa.estado = SituacionAprendizaje.GENERANDO
    db.session.commit()

    provider = get_provider_para(sa.usuario)
    ctx = construir_contexto(sa)

    try:
        payload, respuesta = _ejecutar_seccion(seccion, ctx, provider)
        _fusionar_seccion(sa, seccion, payload)
        # Tras regenerar una sección, la SA se considera "generada"
        # (aunque falten otras secciones, al menos una es válida).
        sa.estado = (
            SituacionAprendizaje.GENERADA
            if estado_previo != SituacionAprendizaje.FINALIZADA
            else SituacionAprendizaje.FINALIZADA
        )
        db.session.commit()
        return {
            "id_situacion": id_situacion,
            "seccion": seccion,
            "proveedor": respuesta.proveedor,
            "modelo": respuesta.modelo,
        }
    except LLMProviderError:
        db.session.rollback()
        sa = _cargar_sa(id_situacion)
        sa.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()
        raise
