"""Las rutas que audita axe existen de verdad.

POR QUÉ HACE FALTA ESTE TEST
-----------------------------
`tests/a11y/axe.mjs` lleva escrita a mano la lista de páginas públicas que
recorre. Al escribirla puse `/registro` y `/restablecer`, y las rutas reales
son `/register` y `/restablecer-contrasena`: dos de seis mal, por suponerlas en
vez de mirarlas.

Ese error se habría visto la primera vez que corriera el flujo. Lo que **no**
se vería es el contrario: si mañana alguien renombra una ruta, la lista deja de
cubrirla y la auditoría sigue en verde **auditando menos páginas**. Un flujo
que pasa recorriendo cinco páginas en vez de seis no se distingue de uno que
las recorre todas.

El script también aborta si una ruta devuelve 4xx, pero eso solo protege
mientras el flujo se ejecute; esto lo comprueba en cada `pytest`, que es más a
menudo y más cerca de quien hace el cambio.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "a11y" / "axe.mjs"


def _rutas_auditadas() -> list[str]:
    fuente = SCRIPT.read_text(encoding="utf-8")
    bloque = re.search(r"const RUTAS = \[(.*?)\];", fuente, re.S)
    assert bloque, "no se encuentra la lista RUTAS en axe.mjs"
    return re.findall(r"\['([^']+)'", bloque.group(1))


@pytest.mark.skipif(not SCRIPT.exists(), reason="no está el script de axe")
class TestLaListaCuadraConLaAplicacion:
    def test_todas_existen(self, app):
        """El fallo que se cometió al escribirla."""
        reales = {r.rule for r in app.url_map.iter_rules()}

        inexistentes = [r for r in _rutas_auditadas() if r not in reales]

        assert inexistentes == [], (
            f"axe.mjs audita rutas que no existen: {inexistentes}. "
            f"Si se renombraron, actualiza la lista."
        )

    def test_todas_responden_sin_sesion(self, client):
        """Auditar una página que redirige al login es auditar el login otra
        vez, y el informe diría «6 páginas» habiendo mirado dos."""
        redirigen = []
        for ruta in _rutas_auditadas():
            respuesta = client.get(ruta)
            if respuesta.status_code in (301, 302, 303, 307, 308):
                redirigen.append((ruta, respuesta.headers.get("Location")))

        assert redirigen == [], f"estas piden sesión: {redirigen}"

    def test_no_se_ha_quedado_ninguna_publica_fuera(self, app):
        """Aviso, no imposición: si aparece una página pública nueva, conviene
        decidir si entra en la auditoría en vez de que se quede fuera por
        olvido.

        La lista de exclusiones es explícita para que añadir una obligue a
        justificarla."""
        # Ni API, ni estáticos, ni nada que necesite sesión o parámetros.
        fuera_por_diseno = {
            "/",                    # redirige según haya sesión o no
            "/health",              # JSON, no tiene interfaz que auditar
            "/static/<path:filename>",
            # Estas dos son públicas pero solo se llega con un token en la URL,
            # así que sin él muestran un error y no la pantalla que interesa.
            "/correo-de-respaldo",
            "/reclamacion",
        }
        publicas = {
            r.rule for r in app.url_map.iter_rules()
            if "GET" in (r.methods or set())
            and "<" not in r.rule
            # `/_test/…` lo registra `conftest.py` para probar los decoradores
            # de rol: no existe en la aplicación real y no hay nada que
            # auditar. Salieron aquí porque este test se escribió mirando el
            # mapa de rutas **fuera** de pytest, donde no están.
            and not r.rule.startswith(("/api", "/admin", "/me", "/situaciones",
                                       "/perfil", "/baja", "/static", "/_test"))
        } - fuera_por_diseno

        sin_auditar = sorted(publicas - set(_rutas_auditadas()))

        assert sin_auditar == [], (
            f"páginas públicas sin auditar: {sin_auditar}. Añádelas a RUTAS en "
            f"axe.mjs, o a `fuera_por_diseno` con el motivo."
        )


@pytest.mark.skipif(not SCRIPT.exists(), reason="no está el script de axe")
class TestElScriptSigueHaciendoLoQueDice:
    def test_audita_los_dos_temas(self):
        """Las dos paletas tienen contrastes distintos: auditar una sola deja
        la otra sin comprobar, que es justo donde aparecieron los dos
        incumplimientos WCAG que venían del TFG."""
        fuente = SCRIPT.read_text(encoding="utf-8")

        assert "const TEMAS = ['claro', 'oscuro']" in fuente

    def test_falla_con_los_graves(self):
        """Si alguien relaja esto, la auditoría pasa a ser decorativa."""
        fuente = SCRIPT.read_text(encoding="utf-8")

        assert "new Set(['serious', 'critical'])" in fuente
        assert "process.exit(1)" in fuente
