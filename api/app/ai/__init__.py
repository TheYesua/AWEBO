"""Capa de acceso a modelos de lenguaje (LLM).

Expone una interfaz estable (``LLMProvider``) con dos implementaciones:

* ``OpenAIProvider``: cliente oficial de OpenAI con reintentos exponenciales
  ante fallos transitorios (``RateLimitError``, ``APIStatusError`` 5xx,
  timeouts).
* ``FakeProvider``: determinista, sin red, usado en tests y cuando
  ``AI_PROVIDER=fake`` (desarrollo sin API key).

La factoría :func:`get_provider` selecciona la implementación según la
configuración de Flask.
"""
from __future__ import annotations

from .provider import LLMProvider, LLMProviderError
from .factory import get_provider
from .fake_provider import FakeProvider
from .openai_provider import OpenAIProvider

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "get_provider",
    "FakeProvider",
    "OpenAIProvider",
]
