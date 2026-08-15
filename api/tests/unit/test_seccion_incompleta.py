"""Que una sección incompleta se reintente, y si no, se cuente.

POR QUÉ EXISTE
--------------
El 14/08/2026 la misma SdA salió **tres veces seguidas** en catalán sin
criterios de evaluación. El JSON era válido; la clave sencillamente no venía.

Un JSON válido pero incompleto es peor que uno inválido. El inválido se
detecta y se guarda como texto crudo para que el docente lo vea. El incompleto
se guarda tal cual, el bloque no se pinta, y el documento sale **pareciendo
completo**.

`autoretry_for=(LLMProviderError,)` no cubría esto: cubre que el proveedor
falle, no que conteste bien con contenido cojo.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tasks.generacion import _CLAVES_EXIGIDAS, _ejecutar_seccion, _partes_vacias


class TestQueCuentaComoIncompleta:
    @pytest.mark.parametrize("payload, esperado", [
        ({"competencias": [1], "criterios": [1], "saberes": [1]}, []),
        ({"competencias": [1], "saberes": [1]}, ["criterios"]),
        ({"competencias": [1], "criterios": [], "saberes": [1]}, ["criterios"]),
        ({}, ["competencias", "criterios", "saberes"]),
    ])
    def test_falta_o_viene_vacia(self, payload, esperado):
        """Una lista vacía cuenta igual que la clave ausente: el bloque no se
        pinta en ninguno de los dos casos."""
        assert _partes_vacias("conexion_curricular", payload) == esperado

    def test_un_error_de_parseo_no_se_cuenta_dos_veces(self):
        """Ya está señalado por otra vía y con su texto crudo. Reintentarlo
        aquí gastaría cuota por algo que el docente ya puede ver."""
        assert _partes_vacias("conexion_curricular", {"_error_parseo": True}) == []

    def test_una_seccion_sin_exigencias_nunca_esta_incompleta(self):
        """`descripcion` es texto libre: no hay clave cuya ausencia esconda
        nada. Exigir algo aquí sería inventarse un contrato."""
        assert _partes_vacias("descripcion", {}) == []

    def test_las_tres_secciones_vigiladas_son_las_que_pintan_bloques(self):
        """Se fija la lista entera a propósito: si alguien añade una sección
        cuyo bloque desaparece al faltar, tiene que pasar por aquí."""
        assert set(_CLAVES_EXIGIDAS) == {
            "conexion_curricular", "objetivos", "secuencia_sesiones"
        }


class _ProveedorFalso:
    """Devuelve las respuestas de la lista, una por llamada."""

    def __init__(self, textos):
        self.textos = list(textos)
        self.llamadas = 0

    def generar(self, peticion):
        self.llamadas += 1
        texto = self.textos[min(self.llamadas - 1, len(self.textos) - 1)]
        return SimpleNamespace(
            texto=texto, proveedor="falso", modelo="falso",
            tokens_prompt=0, tokens_respuesta=0,
        )


@pytest.fixture
def ctx(monkeypatch):
    """Un contexto de mentira, y el prompt sustituido por uno trivial.

    Lo que se prueba aquí es **el reintento**, no la construcción del prompt:
    montar un `ctx` completo obligaría a fabricar media SdA y ataría este
    fichero a cada campo que se le añada al contexto.
    """
    from app.prompts import SECCIONES
    from app.ai.provider import LLMRequest

    monkeypatch.setitem(
        SECCIONES, "conexion_curricular",
        ("v-test", lambda c: LLMRequest(user="u", system="s")),
    )
    return SimpleNamespace(idioma="ca")


class TestElReintento:
    COMPLETA = '{"competencias":[{"codigo":"1"}],"criterios":[{"codigo":"1.1"}],"saberes":[{"codigo":"A.1"}]}'
    SIN_CRITERIOS = '{"competencias":[{"codigo":"1"}],"saberes":[{"codigo":"A.1"}]}'

    def test_una_seccion_completa_no_se_reintenta(self, ctx):
        """Reintentar de más cuesta cuota y tiempo en cada generación."""
        prov = _ProveedorFalso([self.COMPLETA])

        _ejecutar_seccion("conexion_curricular", ctx, prov)

        assert prov.llamadas == 1

    def test_si_falta_una_parte_se_pide_otra_vez(self, ctx):
        prov = _ProveedorFalso([self.SIN_CRITERIOS, self.COMPLETA])

        payload, _ = _ejecutar_seccion("conexion_curricular", ctx, prov)

        assert prov.llamadas == 2
        assert payload["criterios"]
        assert "_incompleta" not in payload

    def test_se_reintenta_UNA_vez_y_no_mas(self, ctx):
        """Si a la segunda sigue faltando, lo más probable es que no sea
        variabilidad sino algo sistemático —el prompt, el idioma, el modelo— e
        insistir solo gasta cuota."""
        prov = _ProveedorFalso([self.SIN_CRITERIOS])

        _ejecutar_seccion("conexion_curricular", ctx, prov)

        assert prov.llamadas == 2

    def test_lo_que_sigue_incompleto_se_guarda_marcado(self, ctx):
        """Media sección es más útil que ninguna, y la exportación ya avisa.
        Pero queda contado: es lo que permitirá saber si esto es variabilidad
        o un fallo del prompt."""
        prov = _ProveedorFalso([self.SIN_CRITERIOS])

        payload, _ = _ejecutar_seccion("conexion_curricular", ctx, prov)

        assert payload["_incompleta"] == ["criterios"]
        assert payload["competencias"], "no se tira lo que sí vino"

    def test_un_json_invalido_no_dispara_reintento(self, ctx):
        """Tiene su propio camino, con el texto crudo guardado."""
        prov = _ProveedorFalso(["esto no es JSON"])

        payload, _ = _ejecutar_seccion("conexion_curricular", ctx, prov)

        assert prov.llamadas == 1
        assert payload["_error_parseo"] is True


class TestSiempreQuedaConstanciaDeQueSeGeneró:
    """Un cero puede ser dos cosas, y una parece una buena noticia.

    «No ha llegado ninguna sección incompleta» y «no hay registro de que se
    haya generado nada» dan el mismo cero. Pasó el 15/08/2026: el contador dijo
    0 y 0, y no había forma de saber si era porque todo fue bien o porque el
    log del worker no llegaba tan atrás.

    Es el mismo error de forma que el `WHERE` que devolvía el 100 % de las
    filas y se leyó como «sobran todas» en vez de como «el filtro está mal».
    """

    @staticmethod
    def _eventos(monkeypatch, ctx, prov):
        """Espía el logger del módulo en vez de capturar la salida.

        Se probó con `structlog.testing.capture_logs` y **pasaba fuera de
        Docker y fallaba dentro**: en el contenedor, `init_logging` engancha
        structlog al logging estándar, y `capture_logs` ya no intercepta nada.
        Con `caplog` pasa lo contrario. Un test cuyo resultado depende de cómo
        esté configurado el logging no mide lo que dice medir.

        Espiar el logger no depende de la configuración: comprueba que el
        código **pide** registrar el evento, que es lo que aquí importa.
        """
        from app.tasks import generacion

        eventos: list[str] = []

        class _Espia:
            def __getattr__(self, nivel):
                def registrar(evento, **kw):
                    eventos.append(evento)
                return registrar

        monkeypatch.setattr(generacion, "logger", _Espia())
        generacion._ejecutar_seccion("conexion_curricular", ctx, prov)
        return eventos

    def test_una_seccion_completa_tambien_deja_rastro(self, ctx, monkeypatch):
        prov = _ProveedorFalso([TestElReintento.COMPLETA])

        eventos = self._eventos(monkeypatch, ctx, prov)

        assert "seccion_generada" in eventos, (
            "sin esto, el contador no distingue «no pasó» de «no hay datos»"
        )

    def test_y_tambien_cuando_hay_que_reintentar(self, ctx, monkeypatch):
        """Dos generaciones, dos rastros: si no, el porcentaje de secciones que
        necesitan reintento saldría inflado."""
        prov = _ProveedorFalso([TestElReintento.SIN_CRITERIOS, TestElReintento.COMPLETA])

        eventos = self._eventos(monkeypatch, ctx, prov)

        assert eventos.count("seccion_generada") == 2
        assert "seccion_incompleta_se_reintenta" in eventos
