"""Interfaz común para los proveedores de LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LLMProviderError(Exception):
    """Error al invocar al LLM tras agotar los reintentos."""

    def __init__(self, mensaje: str, *, reintentos: int = 0) -> None:
        super().__init__(mensaje)
        self.reintentos = reintentos


@dataclass(frozen=True)
class LLMRequest:
    """Petición tipada a un LLM.

    ``system`` (opcional) se envía como mensaje ``system``; ``user`` es el
    prompt principal. ``response_format`` admite ``"json"`` para forzar la
    generación JSON estructurada cuando el proveedor lo soporta.
    """

    user: str
    system: str | None = None
    temperature: float = 0.5
    max_tokens: int | None = None
    response_format: str | None = None  # "json" | None
    metadata: dict = field(default_factory=dict)  # para logs / trazabilidad


@dataclass(frozen=True)
class LLMResponse:
    """Respuesta de un LLM, con metadatos de observabilidad."""

    texto: str
    modelo: str
    tokens_prompt: int | None = None
    tokens_respuesta: int | None = None
    proveedor: str = "desconocido"


class LLMProvider(Protocol):
    """Contrato mínimo que deben cumplir todos los proveedores."""

    nombre: str
    modelo: str
    """Modelo concreto en uso. Permite que /health informe de lo que se está
    ejecutando realmente en lugar de deducirlo de la configuración."""

    def generar(self, peticion: LLMRequest) -> LLMResponse:
        """Ejecuta la petición y devuelve la respuesta. Lanza LLMProviderError."""
        ...
