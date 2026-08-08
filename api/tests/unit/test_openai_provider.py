"""Tests del proveedor de OpenAI: reintentos y parámetros no admitidos.

Ninguno toca la red: se construyen excepciones reales del SDK y se sustituye
el cliente por un doble que registra las llamadas.

Origen de estos tests: al elegir un modelo GPT-5.6 desde el perfil, la
generación fallaba con
``400 Unsupported value: 'temperature' does not support 0.6 with this model``.
La traza mostró además que ese 400 —una petición mal formada, e igual de mal
formada las cuatro veces— se estaba reintentando cuatro veces.
"""
from __future__ import annotations

import httpx
import pytest

from app.ai import openai_provider as op
from app.ai.provider import LLMRequest


#: Cuerpo exacto con el que respondió la API en el fallo original.
CUERPO_TEMPERATURA = {
    "message": (
        "Unsupported value: 'temperature' does not support 0.6 with this "
        "model. Only the default (1) value is supported."
    ),
    "type": "invalid_request_error",
    "param": "temperature",
    "code": "unsupported_value",
}


def _respuesta(codigo: int) -> httpx.Response:
    return httpx.Response(codigo, request=httpx.Request("POST", "https://api.openai.com"))


def _error_temperatura():
    from openai import BadRequestError

    return BadRequestError(
        "Error code: 400", response=_respuesta(400), body=CUERPO_TEMPERATURA
    )


@pytest.fixture(autouse=True)
def _memoria_limpia():
    """El conjunto de modelos sin temperatura vive en el módulo."""
    op._SIN_TEMPERATURA.clear()
    yield
    op._SIN_TEMPERATURA.clear()


# ---------------------------------------------------------------------------
# Política de reintentos
# ---------------------------------------------------------------------------


class TestReintentos:
    """Solo lo transitorio merece reintento."""

    @pytest.mark.parametrize("codigo", [400, 401, 403, 404, 422])
    def test_los_errores_del_cliente_no_se_reintentan(self, codigo):
        from openai import APIStatusError

        exc = APIStatusError("cliente", response=_respuesta(codigo), body=None)
        assert not op._es_reintentable(exc), (
            f"un {codigo} está igual de mal formado en el cuarto intento "
            "que en el primero"
        )

    @pytest.mark.parametrize("codigo", [500, 502, 503, 504])
    def test_los_errores_del_servidor_si_se_reintentan(self, codigo):
        from openai import APIStatusError

        exc = APIStatusError("servidor", response=_respuesta(codigo), body=None)
        assert op._es_reintentable(exc)

    def test_timeouts_y_cortes_de_conexion_se_reintentan(self):
        from openai import APIConnectionError, APITimeoutError

        peticion = httpx.Request("POST", "https://api.openai.com")
        assert op._es_reintentable(APITimeoutError(request=peticion))
        assert op._es_reintentable(APIConnectionError(request=peticion))

    def test_el_limite_de_ritmo_se_reintenta(self):
        from openai import RateLimitError

        exc = RateLimitError("demasiadas", response=_respuesta(429), body=None)
        assert op._es_reintentable(exc)


# ---------------------------------------------------------------------------
# Detección del parámetro no admitido
# ---------------------------------------------------------------------------


class TestDeteccionTemperatura:
    def test_reconoce_el_error_real(self):
        assert op._rechaza_temperatura(_error_temperatura())

    def test_no_confunde_con_otro_parametro(self):
        from openai import BadRequestError

        exc = BadRequestError(
            "otro", response=_respuesta(400), body={"param": "model"}
        )
        assert not op._rechaza_temperatura(exc)

    def test_no_confunde_con_un_error_de_servidor(self):
        from openai import APIStatusError

        exc = APIStatusError("boom", response=_respuesta(500), body=None)
        assert not op._rechaza_temperatura(exc)


# ---------------------------------------------------------------------------
# Reintento sin el parámetro
# ---------------------------------------------------------------------------


class _CompletionsFalsas:
    """Doble del cliente: falla si recibe ``temperature``."""

    def __init__(self) -> None:
        self.llamadas: list[dict] = []

    def create(self, **kwargs):
        self.llamadas.append(kwargs)
        if "temperature" in kwargs:
            raise _error_temperatura()

        mensaje = type("Mensaje", (), {"content": '{"ok": true}'})()
        return type(
            "Respuesta",
            (),
            {
                "choices": [type("Opcion", (), {"message": mensaje})()],
                "model": kwargs["model"],
                "usage": type("Uso", (), {"prompt_tokens": 10, "completion_tokens": 5})(),
            },
        )()


def _proveedor(modelo: str = "gpt-5.6-luna") -> op.OpenAIProvider:
    """Instancia sin pasar por ``__init__``, que crearía un cliente real."""
    p = op.OpenAIProvider.__new__(op.OpenAIProvider)
    p._client = type(
        "Cliente", (), {"chat": type("Chat", (), {"completions": _CompletionsFalsas()})()}
    )()
    p._modelo = modelo
    p._max_intentos = 4
    return p


class TestReintentoSinTemperatura:
    def test_la_generacion_termina_bien(self):
        p = _proveedor()
        r = p.generar(LLMRequest(user="hola", temperature=0.6))
        assert r.texto == '{"ok": true}'

    def test_se_reintenta_una_sola_vez_y_sin_el_parametro(self):
        p = _proveedor()
        p.generar(LLMRequest(user="hola", temperature=0.6))

        llamadas = p._client.chat.completions.llamadas
        assert len(llamadas) == 2
        assert "temperature" in llamadas[0]
        assert "temperature" not in llamadas[1]

    def test_el_reintento_conserva_el_resto_de_parametros(self):
        p = _proveedor()
        p.generar(
            LLMRequest(
                user="hola", system="instrucciones", temperature=0.6,
                response_format="json",
            )
        )
        segunda = p._client.chat.completions.llamadas[1]
        assert segunda["model"] == "gpt-5.6-luna"
        assert segunda["response_format"] == {"type": "json_object"}
        assert len(segunda["messages"]) == 2  # system + user

    def test_la_siguiente_llamada_no_malgasta_una_peticion(self):
        """La restricción se aprende una vez por modelo y proceso."""
        p = _proveedor()
        p.generar(LLMRequest(user="primera", temperature=0.6))
        p._client.chat.completions.llamadas.clear()

        p.generar(LLMRequest(user="segunda", temperature=0.9))
        llamadas = p._client.chat.completions.llamadas
        assert len(llamadas) == 1
        assert "temperature" not in llamadas[0]

    def test_se_anota_el_modelo_concreto_no_el_proveedor(self):
        """Que un modelo rechace el parámetro no dice nada de los demás."""
        p = _proveedor("gpt-5.6-luna")
        p.generar(LLMRequest(user="hola", temperature=0.6))

        assert op._SIN_TEMPERATURA == {"gpt-5.6-luna"}

    def test_un_modelo_no_marcado_sigue_enviando_temperature(self):
        otro = _proveedor("gpt-5.6-luna")
        otro.generar(LLMRequest(user="hola", temperature=0.6))

        # Un modelo distinto arranca sin la marca: su primera llamada debe
        # llevar temperature, porque puede que sí la admita.
        p = _proveedor("modelo-que-si-la-admite")
        p._client.chat.completions.create = lambda **kw: (
            p._client.chat.completions.llamadas.append(kw)
            or type(
                "R",
                (),
                {
                    "choices": [
                        type("O", (), {"message": type("M", (), {"content": "{}"})()})()
                    ],
                    "model": kw["model"],
                    "usage": None,
                },
            )()
        )
        p.generar(LLMRequest(user="hola", temperature=0.5))
        assert "temperature" in p._client.chat.completions.llamadas[0]

    def test_un_400_por_otro_motivo_si_llega_al_usuario(self):
        """Solo se absorbe el rechazo de temperature, no cualquier 400."""
        from openai import BadRequestError

        p = _proveedor()

        def _siempre_falla(**kwargs):
            raise BadRequestError(
                "modelo inexistente", response=_respuesta(400), body={"param": "model"}
            )

        p._client.chat.completions.create = _siempre_falla
        with pytest.raises(Exception) as exc:
            p.generar(LLMRequest(user="hola", temperature=0.6))
        assert "fallo_llm" in str(exc.value)
