"""Proveedor LLM que usa el cliente oficial de Google Generative AI (Gemini).

Características:
* Reintentos exponenciales ante errores de red o cuota.
* Mapeo de system prompt al comportamiento esperado por Gemini.
"""
from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .provider import LLMProviderError, LLMRequest, LLMResponse

logger = logging.getLogger("ai.gemini")

def _excepciones_reintentables():
    from google.api_core.exceptions import RetryError, ResourceExhausted, ServiceUnavailable, InternalServerError, DeadlineExceeded
    return (RetryError, ResourceExhausted, ServiceUnavailable, InternalServerError, DeadlineExceeded)

class GeminiProvider:
    """Implementa :class:`LLMProvider` contra la API de Gemini."""

    nombre = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        modelo: str,
        max_intentos: int = 4,
    ) -> None:
        if not api_key:
            raise ValueError("GeminiProvider requiere api_key no vacía.")
            
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        self._modelo = modelo
        self._max_intentos = max_intentos

    # -- API pública ------------------------------------------------------

    @property
    def modelo(self) -> str:
        return self._modelo

    def generar(self, peticion: LLMRequest) -> LLMResponse:
        try:
            return self._invocar_con_reintentos(peticion)
        except Exception as exc:
            if isinstance(exc, LLMProviderError):
                raise
            logger.exception("Fallo no recuperable al invocar Gemini")
            raise LLMProviderError(f"fallo_llm: {exc}") from exc

    # -- internos --------------------------------------------------------

    def _invocar_con_reintentos(self, peticion: LLMRequest) -> LLMResponse:
        reintentables = _excepciones_reintentables()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_intentos),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            retry=retry_if_exception_type(reintentables),
            before_sleep=lambda rs: logger.warning(
                "Reintentando Gemini (intento %d) tras %s",
                rs.attempt_number,
                rs.outcome.exception().__class__.__name__,
            ),
        )
        def _ejecutar() -> LLMResponse:
            return self._llamar(peticion)

        return _ejecutar()

    def _llamar(self, peticion: LLMRequest) -> LLMResponse:
        import google.generativeai as genai
        
        # Configurar modelo con system instruction si lo hay
        kwargs = {}
        if peticion.system:
            kwargs["system_instruction"] = peticion.system
            
        # Configurar parámetros de generación
        generation_config = genai.types.GenerationConfig(
            temperature=peticion.temperature,
        )
        if peticion.max_tokens is not None:
            generation_config.max_output_tokens = peticion.max_tokens
        if peticion.response_format == "json":
            generation_config.response_mime_type = "application/json"
            
        # Crear modelo instanciado
        model = genai.GenerativeModel(
            model_name=self._modelo,
            **kwargs
        )
        
        # Ejecutar
        respuesta = model.generate_content(
            peticion.user,
            generation_config=generation_config
        )
        
        # Extraer texto y uso
        texto = respuesta.text
        usage = respuesta.usage_metadata
        
        tokens_prompt = getattr(usage, "prompt_token_count", None) if usage else None
        tokens_respuesta = getattr(usage, "candidates_token_count", None) if usage else None

        return LLMResponse(
            texto=texto,
            modelo=self._modelo,
            tokens_prompt=tokens_prompt,
            tokens_respuesta=tokens_respuesta,
            proveedor=self.nombre,
        )
