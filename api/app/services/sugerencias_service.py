"""Servicio de sugerencia inicial de temáticas.

Aísla la llamada al LLM del blueprint, igual que el resto de servicios, para
que el endpoint quede fino y esta lógica sea testable sin cliente HTTP.

Nota sobre la sincronía: a diferencia de la generación de una SA —que va por
Celery porque son seis secciones y minutos de trabajo—, esto devuelve tres
propuestas cortas y se resuelve dentro de la propia petición. Meterlo en la
cola obligaría a montar polling y espera para algo que tarda un par de
segundos, y la funcionalidad existe precisamente para reducir fricción.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from ..ai.factory import get_provider_para
from ..ai.provider import LLMProviderError, LLMResponse
from ..prompts import sugerencias as prompt_sugerencias


logger = structlog.get_logger("services.sugerencias")


#: Claves que debe traer cada propuesta. El orden es el de presentación.
_CLAVES = ("titulo", "resumen", "producto_final", "pregunta_guia")


class SugerenciasError(Exception):
    """Error al obtener sugerencias. Lleva su propio código HTTP."""

    def __init__(self, code: str, mensaje: str, http_status: int = 502) -> None:
        super().__init__(mensaje)
        self.code = code
        self.http_status = http_status


def _normalizar(bruto: Any) -> list[dict[str, str]]:
    """Extrae y sanea la lista de propuestas de la respuesta del modelo.

    Los LLM devuelven JSON con forma variable aunque se les pida un esquema:
    a veces la lista viene en la raíz, a veces bajo otra clave. Se aceptan las
    variantes razonables en lugar de fallar, pero se descarta cualquier
    propuesta a la que le falte el título, que es lo único imprescindible
    para que la tarjeta sea utilizable.
    """
    if isinstance(bruto, list):
        candidatas = bruto
    elif isinstance(bruto, dict):
        for clave in ("propuestas", "sugerencias", "items", "resultados"):
            if isinstance(bruto.get(clave), list):
                candidatas = bruto[clave]
                break
        else:
            candidatas = []
    else:
        candidatas = []

    propuestas: list[dict[str, str]] = []
    for item in candidatas:
        if not isinstance(item, dict):
            continue
        titulo = str(item.get("titulo") or "").strip()
        if not titulo:
            continue
        propuestas.append(
            {clave: str(item.get(clave) or "").strip() for clave in _CLAVES}
        )
    return propuestas


def proponer(
    *,
    curso: str,
    materia: str,
    contexto: str | None = None,
    idioma: str = "es",
    num_propuestas: int = prompt_sugerencias.NUM_PROPUESTAS_DEFECTO,
    usuario=None,
) -> dict[str, Any]:
    """Pide temáticas al LLM y devuelve ``{"propuestas": [...], "_meta": {...}}``.

    :param usuario: si se pasa, se respeta el proveedor que tenga elegido en su
        perfil. Con ``None`` se usa el del sistema.
    :raises SugerenciasError: si el proveedor falla o si la respuesta no
        contiene ninguna propuesta aprovechable.
    """
    peticion = prompt_sugerencias.build(
        curso=curso,
        materia=materia,
        contexto=contexto,
        idioma=idioma,
        num_propuestas=num_propuestas,
    )

    provider = get_provider_para(usuario)
    try:
        respuesta: LLMResponse = provider.generar(peticion)
    except LLMProviderError as exc:
        logger.warning("sugerencias_llm_error", error=str(exc))
        raise SugerenciasError(
            "llm_no_disponible",
            "No se han podido generar sugerencias ahora mismo. Inténtalo de nuevo "
            "en unos minutos.",
            http_status=503,
        ) from exc

    try:
        bruto = json.loads(respuesta.texto)
    except json.JSONDecodeError:
        # A diferencia de las secciones, aquí no tiene sentido guardar el texto
        # crudo: no hay nada que persistir ni que el docente pueda corregir a
        # mano. Se registra para diagnóstico y se devuelve un error limpio.
        logger.warning(
            "sugerencias_no_json",
            modelo=respuesta.modelo,
            proveedor=respuesta.proveedor,
            muestra=respuesta.texto[:200],
        )
        raise SugerenciasError(
            "respuesta_ilegible",
            "El modelo ha devuelto una respuesta con un formato inesperado. "
            "Vuelve a intentarlo.",
        )

    propuestas = _normalizar(bruto)
    if not propuestas:
        logger.warning(
            "sugerencias_vacias", modelo=respuesta.modelo, proveedor=respuesta.proveedor
        )
        raise SugerenciasError(
            "sin_propuestas",
            "El modelo no ha devuelto ninguna propuesta utilizable. "
            "Prueba a describir con algo más de detalle lo que buscas.",
        )

    logger.info(
        "sugerencias_generadas",
        curso=curso,
        materia=materia,
        n=len(propuestas),
        proveedor=respuesta.proveedor,
        modelo=respuesta.modelo,
    )

    return {
        "propuestas": propuestas,
        "_meta": {
            "version_prompt": prompt_sugerencias.VERSION,
            "proveedor": respuesta.proveedor,
            "modelo": respuesta.modelo,
            "tokens_prompt": respuesta.tokens_prompt,
            "tokens_respuesta": respuesta.tokens_respuesta,
        },
    }
