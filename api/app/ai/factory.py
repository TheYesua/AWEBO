"""Factoría de :class:`LLMProvider`.

Resuelve qué proveedor usar en dos pasos:

1. Si se pide uno explícitamente —porque el usuario lo eligió en su perfil—,
   se usa ese.
2. Si no, se cae a la configuración del proceso (``AI_PROVIDER``,
   ``OPENAI_MODEL``…), que es el comportamiento histórico.

Los proveedores se cachean por proceso para no reabrir clientes HTTP en cada
tarea Celery. La clave del caché es la pareja **(proveedor, modelo)**: con
selección por usuario ya no basta el nombre, porque dos docentes pueden pedir
el mismo proveedor con modelos distintos y el modelo se fija al construir el
cliente.
"""
from __future__ import annotations

import logging

from flask import current_app

from .fake_provider import FakeProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .provider import LLMProvider


logger = logging.getLogger("ai.factory")


#: Caché por proceso. Clave: ``(proveedor, modelo)``.
_cache: dict[tuple[str, str], LLMProvider] = {}


def _fake() -> LLMProvider:
    return _cache.setdefault(("fake", "fake"), FakeProvider())


def _construir(nombre: str, modelo: str) -> LLMProvider:
    """Instancia el proveedor pedido, cacheando por (nombre, modelo)."""
    clave = (nombre, modelo)
    if clave in _cache:
        return _cache[clave]

    cfg = current_app.config

    if nombre == "openai":
        api_key = cfg.get("OPENAI_API_KEY") or ""
        if not api_key:
            logger.warning(
                "Se pidió el proveedor openai pero no hay OPENAI_API_KEY; "
                "usando FakeProvider como respaldo."
            )
            return _fake()
        _cache[clave] = OpenAIProvider(
            api_key=api_key,
            modelo=modelo or cfg.get("OPENAI_MODEL") or "gpt-4o-mini",
            timeout=int(cfg.get("OPENAI_TIMEOUT") or 120),
        )
        return _cache[clave]

    if nombre == "gemini":
        api_key = cfg.get("GEMINI_API_KEY") or ""
        if not api_key:
            logger.warning(
                "Se pidió el proveedor gemini pero no hay GEMINI_API_KEY; "
                "usando FakeProvider como respaldo."
            )
            return _fake()
        _cache[clave] = GeminiProvider(
            api_key=api_key,
            modelo=modelo or cfg.get("GEMINI_MODEL") or "gemini-3.5-flash",
        )
        return _cache[clave]

    if nombre == "fake":
        return _fake()

    raise ValueError(f"Proveedor de IA no soportado: {nombre!r}")


def _por_configuracion() -> tuple[str, str]:
    """Resuelve el proveedor del proceso a partir de la configuración."""
    cfg = current_app.config
    solicitado = (cfg.get("AI_PROVIDER") or "").lower().strip()
    api_key = cfg.get("OPENAI_API_KEY") or ""

    if solicitado == "fake" or (not solicitado and not api_key):
        return "fake", "fake"
    if solicitado in ("", "openai"):
        return "openai", cfg.get("OPENAI_MODEL") or ""
    if solicitado == "gemini":
        return "gemini", cfg.get("GEMINI_MODEL") or ""

    raise ValueError(f"AI_PROVIDER no soportado: {solicitado!r}")


def get_provider(
    proveedor: str | None = None, modelo: str | None = None
) -> LLMProvider:
    """Devuelve el proveedor a usar.

    :param proveedor: elección explícita (del perfil del usuario). Si es
        ``None``, se usa la configuración del proceso.
    :param modelo: modelo concreto. Solo se tiene en cuenta si se pasa
        ``proveedor``; si va vacío se usa el modelo por defecto de ese
        proveedor.

    Sin argumentos el comportamiento es idéntico al que había antes de que
    existiera la selección por usuario, que es lo que permite llamarla desde
    sitios sin usuario asociado (comandos de CLI, healthcheck).
    """
    if proveedor:
        nombre = proveedor.lower().strip()
        return _construir(nombre, (modelo or "").strip())

    nombre, modelo_cfg = _por_configuracion()
    return _construir(nombre, modelo_cfg)


def get_provider_para(usuario) -> LLMProvider:
    """Proveedor correspondiente a las preferencias de ``usuario``.

    Acepta ``None`` (o un usuario sin preferencia) y cae a la configuración
    del proceso. La validación contra el catálogo se hace aquí y no solo al
    guardar el perfil: si un proveedor desaparece del ``.env`` después de que
    alguien lo eligiera, su cuenta debe seguir funcionando con el del sistema
    en lugar de romperse.
    """
    from . import catalogo

    if usuario is None:
        return get_provider()

    proveedor, modelo = catalogo.validar(
        getattr(usuario, "proveedor_ia", None),
        getattr(usuario, "modelo_ia", None),
    )
    return get_provider(proveedor, modelo)


def reset_cache() -> None:
    """Vacía el caché (útil en tests al reconfigurar la app)."""
    _cache.clear()
