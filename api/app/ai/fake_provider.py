"""Proveedor LLM determinista para tests y desarrollo sin API key.

No hace ninguna llamada de red. Produce una respuesta reproducible basada
en un hash estable del prompt, de modo que:

* Los tests pueden aserir contra el contenido sin flakiness.
* El contrato JSON sigue siendo válido (cuando ``response_format="json"``,
  devuelve un objeto JSON con una estructura mínima útil).

Se puede inyectar una ``tabla_respuestas`` en tiempo de test para responder
valores fijos a prompts concretos (mapeo ``clave_substring -> respuesta``).
"""
from __future__ import annotations

import hashlib
import json

from .provider import LLMProvider, LLMRequest, LLMResponse


class FakeProvider:
    """Implementa :class:`LLMProvider` sin dependencias externas."""

    nombre = "fake"
    modelo = "fake"

    def __init__(self, tabla_respuestas: dict[str, str] | None = None) -> None:
        self.tabla_respuestas: dict[str, str] = tabla_respuestas or {}
        self.llamadas: list[LLMRequest] = []  # para inspección en tests

    # -- API pública ------------------------------------------------------

    def generar(self, peticion: LLMRequest) -> LLMResponse:
        self.llamadas.append(peticion)

        # 1) Coincidencia manual en la tabla (tests explícitos).
        for clave, respuesta in self.tabla_respuestas.items():
            if clave in peticion.user:
                return self._empaquetar(respuesta, peticion)

        # 2) Respuesta sintética.
        if peticion.response_format == "json":
            payload = {
                "generado_por": "FakeProvider",
                "resumen": self._resumen(peticion.user),
                "items": [
                    f"Elemento {i + 1} generado para la prueba."
                    for i in range(3)
                ],
            }
            return self._empaquetar(json.dumps(payload, ensure_ascii=False), peticion)

        texto = (
            "Respuesta simulada de FakeProvider.\n"
            f"Longitud prompt={len(peticion.user)} caracteres.\n"
            f"Resumen: {self._resumen(peticion.user)}"
        )
        return self._empaquetar(texto, peticion)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _resumen(texto: str) -> str:
        """Hash corto estable del prompt (para que el fake sea determinista)."""
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]

    def _empaquetar(self, texto: str, peticion: LLMRequest) -> LLMResponse:
        return LLMResponse(
            texto=texto,
            modelo="fake-model-v1",
            tokens_prompt=len(peticion.user.split()),
            tokens_respuesta=len(texto.split()),
            proveedor=self.nombre,
        )
