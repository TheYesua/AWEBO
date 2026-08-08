"""Tarea Celery que transforma un bloque ya generado (CU-05 ampliado).

Las cuatro operaciones comparten flujo: se toma el contenido actual de una
sección y se pide al LLM una versión transformada. La diferencia está en el
destino. Resumir, expandir y traducir **sustituyen** el contenido; proponer una
alternativa lo deja **junto al actual**, bajo `_alternativa`, esperando a que
el docente elija.

Se aplica **directamente**, sin previsualización, porque antes de sustituir se
guarda una versión completa de la SA. Deshacer es restaurar esa versión, y
resulta más natural juzgar el resultado en su sitio —con el resto de la SA
alrededor— que en un panel de comparación.

Va por Celery y no de forma síncrona, al contrario que las sugerencias: aquí se
transforma una sección entera, que puede ser larga, y el frontend ya tiene el
polling de progreso montado para la regeneración.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from celery import shared_task

from ..ai import LLMProviderError
from ..ai.factory import get_provider_para
from ..extensions import db
from ..models import SituacionAprendizaje, Version
from ..prompts import operaciones as prompt_operaciones


logger = structlog.get_logger("tasks.operaciones")


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guardar_version(sa: SituacionAprendizaje, descripcion: str) -> int:
    """Guarda un snapshot del contenido ANTES de transformarlo.

    Es lo que hace viable aplicar sin previsualizar. Se reutiliza el mismo
    mecanismo de versiones del CRUD para no tener dos historiales distintos:
    en el listado de versiones, una operación aparece junto a las ediciones
    manuales, que es donde el docente la va a buscar.
    """
    # Import local: ``situacion_service`` importa modelos que a su vez tiran de
    # este módulo por la vía de las tareas, y a nivel de módulo sería un ciclo.
    from ..services.situacion_service import _proximo_numero_version, _snapshot

    version = Version(
        id_situacion=sa.id_situacion,
        numero_version=_proximo_numero_version(sa.id_situacion),
        contenido=_snapshot(sa),
        descripcion_cambio=descripcion,
    )
    db.session.add(version)
    db.session.flush()
    return version.numero_version


@shared_task(
    bind=True,
    name="awebo.transformar_seccion",
    autoretry_for=(LLMProviderError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=2,
)
def transformar_seccion(
    self, id_situacion: int, seccion: str, operacion: str
) -> dict[str, Any]:
    """Aplica ``operacion`` sobre ``seccion`` y sustituye su contenido."""
    if not prompt_operaciones.aplicable(operacion, seccion):
        raise ValueError(
            f"La operación {operacion!r} no se aplica a la sección {seccion!r}"
        )

    sa = db.session.get(SituacionAprendizaje, id_situacion)
    if sa is None:
        raise ValueError(f"SituacionAprendizaje id={id_situacion} no existe")

    contenido = dict(sa.contenido or {})
    bloque = contenido.get(seccion)
    if not isinstance(bloque, dict) or not bloque:
        raise ValueError(f"La sección {seccion!r} no tiene contenido que transformar")

    # Fuera ``_meta`` (trazabilidad nuestra: proveedor, modelo, versión de
    # prompt) y ``_alternativa`` (una candidata anterior sin resolver).
    # Ninguna de las dos es contenido de la sección, y mandarlas al modelo le
    # invitaría a reescribirlas o a copiarlas.
    sin_meta = {
        k: v for k, v in bloque.items() if k not in ("_meta", "_alternativa")
    }

    version_previa = _guardar_version(
        sa, f"Antes de {operacion} la sección «{seccion}»"
    )

    estado_previo = sa.estado
    sa.estado = SituacionAprendizaje.GENERANDO
    db.session.commit()

    provider = get_provider_para(sa.usuario)
    peticion = prompt_operaciones.build(
        operacion=operacion,
        seccion=seccion,
        contenido=sin_meta,
        idioma=sa.idioma,
    )

    try:
        respuesta = provider.generar(peticion)
    except LLMProviderError:
        db.session.rollback()
        sa = db.session.get(SituacionAprendizaje, id_situacion)
        sa.estado = estado_previo
        db.session.commit()
        raise

    try:
        nuevo = json.loads(respuesta.texto)
    except json.JSONDecodeError:
        logger.warning(
            "operacion_no_json",
            seccion=seccion,
            operacion=operacion,
            modelo=respuesta.modelo,
        )
        nuevo = None

    # Si el modelo devuelve algo que no es un objeto, o cambia las claves de
    # sitio, se descarta: sustituir el bloque por una estructura distinta
    # dejaría la sección sin renderizar. Mejor no tocar nada y decirlo.
    if not isinstance(nuevo, dict) or set(nuevo) != set(sin_meta):
        logger.warning(
            "operacion_esquema_alterado",
            seccion=seccion,
            operacion=operacion,
            esperadas=sorted(sin_meta),
            recibidas=sorted(nuevo) if isinstance(nuevo, dict) else None,
        )
        db.session.rollback()
        sa = db.session.get(SituacionAprendizaje, id_situacion)
        sa.estado = estado_previo
        db.session.commit()
        return {
            "id_situacion": id_situacion,
            "seccion": seccion,
            "operacion": operacion,
            "aplicada": False,
            "motivo": "esquema_alterado",
        }

    nuevo["_meta"] = {
        **bloque.get("_meta", {}),
        "operacion": operacion,
        "version_operacion": prompt_operaciones.VERSION,
        "proveedor": respuesta.proveedor,
        "modelo": respuesta.modelo,
        "transformada_en": _ahora_iso(),
    }

    if operacion == prompt_operaciones.ALTERNATIVA:
        # La alternativa NO sustituye: se guarda junto a la actual, bajo la
        # clave `_alternativa`, y ahí espera a que el docente elija. Es la
        # diferencia de fondo con las otras tres operaciones — aquí el docente
        # no ha pedido un cambio, ha pedido algo entre lo que decidir.
        #
        # Va dentro del propio bloque y no en una clave hermana de `contenido`
        # para que borrar la sección se lleve su candidata por delante y no
        # queden alternativas huérfanas de secciones que ya no existen.
        actual = dict(bloque)
        actual.pop("_alternativa", None)   # una nueva reemplaza a la anterior
        actual["_alternativa"] = nuevo
        contenido[seccion] = actual
    else:
        contenido[seccion] = nuevo

    sa.contenido = contenido  # JSONB: hay que reasignar para que se detecte
    sa.estado = estado_previo
    db.session.commit()

    logger.info(
        "seccion_transformada",
        id_situacion=id_situacion,
        seccion=seccion,
        operacion=operacion,
        proveedor=respuesta.proveedor,
        modelo=respuesta.modelo,
    )

    return {
        "id_situacion": id_situacion,
        "seccion": seccion,
        "operacion": operacion,
        "aplicada": True,
        "version_previa": version_previa,
        "proveedor": respuesta.proveedor,
        "modelo": respuesta.modelo,
    }
