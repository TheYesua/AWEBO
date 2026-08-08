"""Proveedor LLM que usa el cliente oficial de OpenAI.

Características:

* Reintentos exponenciales (``tenacity``) ante errores transitorios:
  ``RateLimitError``, ``APITimeoutError`` y ``APIStatusError`` con código
  5xx. Máximo 4 intentos (≈ 1s, 2s, 4s, 8s).
* Traducción de cualquier error final a :class:`LLMProviderError` para
  aislar a quien llama del cliente concreto.
* Modo ``response_format="json"`` fuerza ``response_format={"type":
  "json_object"}`` en Chat Completions.
"""
from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .provider import LLMProvider, LLMProviderError, LLMRequest, LLMResponse


logger = logging.getLogger("ai.openai")


#: Modelos que han rechazado ``temperature`` en esta ejecución.
#:
#: Los modelos de razonamiento de OpenAI no admiten el parámetro: responden
#: ``400 unsupported_value`` diciendo que solo aceptan el valor por defecto.
#: En vez de mantener una lista de familias en el código —que caducaría igual
#: que caducaría una lista de modelos—, se aprende al primer rechazo y se
#: recuerda mientras viva el proceso. Coste: una petición fallida por modelo y
#: proceso; a cambio, funciona con modelos que aún no existen.
_SIN_TEMPERATURA: set[str] = set()


def _es_reintentable(exc: BaseException) -> bool:
    """Decide si un error merece reintento.

    Solo lo transitorio: tiempos de espera, cortes de conexión, límite de
    ritmo y errores 5xx del servidor.

    Antes esto era una tupla de clases que incluía ``APIStatusError`` entera,
    de modo que un ``400`` —petición mal formada, y por tanto igual de mal
    formada las cuatro veces— se reintentaba cuatro veces antes de fallar.
    El docstring del módulo ya decía «5xx»; solo el código no lo cumplía.
    """
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        RateLimitError,
    )

    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False


def _rechaza_temperatura(exc: BaseException) -> bool:
    """¿El error dice que este modelo no admite ``temperature``?

    Se mira el campo ``param`` de la respuesta, que es donde la API señala el
    parámetro conflictivo, con varias vías de acceso porque el SDK lo expone
    de forma distinta según la versión. El cotejo del texto queda como último
    recurso.
    """
    from openai import BadRequestError

    if not isinstance(exc, BadRequestError):
        return False

    if getattr(exc, "param", None) == "temperature":
        return True

    cuerpo = getattr(exc, "body", None)
    if isinstance(cuerpo, dict):
        error = cuerpo.get("error")
        if isinstance(error, dict) and error.get("param") == "temperature":
            return True

    return "'temperature'" in str(exc)


class OpenAIProvider:
    """Implementa :class:`LLMProvider` contra la Chat Completions API."""

    nombre = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        modelo: str,
        timeout: int = 120,
        max_intentos: int = 4,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAIProvider requiere api_key no vacía.")
        # Import local para que el paquete ``ai`` pueda importarse aunque
        # ``openai`` no esté disponible en tiempo de test.
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=timeout)
        self._modelo = modelo
        self._max_intentos = max_intentos

    # -- API pública ------------------------------------------------------

    @property
    def modelo(self) -> str:
        return self._modelo

    def generar(self, peticion: LLMRequest) -> LLMResponse:
        try:
            return self._invocar_con_reintentos(peticion)
        except Exception as exc:  # incluye LLMProviderError e inesperados
            if isinstance(exc, LLMProviderError):
                raise
            logger.exception("Fallo no recuperable al invocar OpenAI")
            raise LLMProviderError(f"fallo_llm: {exc}") from exc

    # -- internos --------------------------------------------------------

    def _invocar_con_reintentos(self, peticion: LLMRequest) -> LLMResponse:

        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_intentos),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            retry=retry_if_exception(_es_reintentable),
            before_sleep=lambda rs: logger.warning(
                "Reintentando OpenAI (intento %d) tras %s",
                rs.attempt_number,
                rs.outcome.exception().__class__.__name__,
            ),
        )
        def _ejecutar() -> LLMResponse:
            return self._llamar(peticion)

        return _ejecutar()

    def _construir_kwargs(
        self, peticion: LLMRequest, *, con_temperatura: bool
    ) -> dict:
        mensajes = []
        if peticion.system:
            mensajes.append({"role": "system", "content": peticion.system})
        mensajes.append({"role": "user", "content": peticion.user})

        kwargs: dict = {"model": self._modelo, "messages": mensajes}
        if con_temperatura:
            kwargs["temperature"] = peticion.temperature
        if peticion.max_tokens is not None:
            # Modelos GPT-5.x usan max_completion_tokens en lugar de max_tokens
            if self._modelo.startswith('gpt-5'):
                kwargs["max_completion_tokens"] = peticion.max_tokens
            else:
                kwargs["max_tokens"] = peticion.max_tokens
        if peticion.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def _llamar(self, peticion: LLMRequest) -> LLMResponse:
        con_temp = self._modelo not in _SIN_TEMPERATURA

        try:
            respuesta = self._client.chat.completions.create(
                **self._construir_kwargs(peticion, con_temperatura=con_temp)
            )
        except Exception as exc:
            # Los modelos de razonamiento no aceptan ``temperature``. No es un
            # fallo del que haya que informar al docente: se anota el modelo y
            # se repite la petición sin el parámetro. A partir de ahí, este
            # proceso ya no lo enviará para ese modelo.
            if not (con_temp and _rechaza_temperatura(exc)):
                raise
            logger.info(
                "El modelo %s no admite 'temperature'; se reintenta sin él.",
                self._modelo,
            )
            _SIN_TEMPERATURA.add(self._modelo)
            respuesta = self._client.chat.completions.create(
                **self._construir_kwargs(peticion, con_temperatura=False)
            )

        choice = respuesta.choices[0]
        texto = choice.message.content or ""
        usage = getattr(respuesta, "usage", None)

        return LLMResponse(
            texto=texto,
            modelo=respuesta.model,
            tokens_prompt=getattr(usage, "prompt_tokens", None),
            tokens_respuesta=getattr(usage, "completion_tokens", None),
            proveedor=self.nombre,
        )
