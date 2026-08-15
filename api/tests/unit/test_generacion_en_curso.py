"""Que una SdA que ya estaba generando siga su curso al abrir la página.

EL FALLO
--------
`pollear` solo se llamaba desde `lanzarGeneracion`, o sea **solo si la
generación se lanzaba desde esa misma página**. Al abrir la SdA desde el
listado mientras generaba, o al recargar, el estado se pintaba «Generando» y
ahí se quedaba: sin barra, sin avanzar, y sin más salida que refrescar a mano
hasta acertar.

Encaja con lo que se observó usando la aplicación: pasaba «más la primera vez»
—cuando uno abre la SdA recién lanzada— y no al regenerar desde el detalle, que
es justo el caso en que sí se llama a `pollear`.

POR QUÉ NO SE REANUDA `pollear`
-------------------------------
Necesita el `task_id`, que solo existe en la respuesta del POST que lanzó la
tarea y no se guarda en ninguna parte. Se sondea el **estado de la SdA**, que sí
es recuperable: se pierde el «sección 3 de 6» y se gana que la página deje de
mentir.
"""
from __future__ import annotations

import re
from pathlib import Path

DETALLE = (
    Path(__file__).resolve().parents[2]
    / "app" / "templates" / "situaciones" / "detalle.html"
)


class TestSeReanudaElSondeo:
    def test_al_cargar_una_sda_generando_se_sigue(self):
        html = DETALLE.read_text(encoding="utf-8")

        assert re.search(
            r"sa\.estado === 'generando'.*seguirGeneracionEnCurso\(\)", html
        ), "al abrir una SdA que ya genera, nadie la sigue"

    def test_no_se_abren_dos_sondeos_a_la_vez(self):
        """`cargar()` se llama desde varios sitios —al guardar, al restaurar una
        versión—. Sin la guarda, cada llamada abriría otro bucle y multiplicaría
        las peticiones mientras dura la generación."""
        html = DETALLE.read_text(encoding="utf-8")

        assert "!sondeandoEstado" in html
        assert re.search(r"sondeandoEstado = true", html)
        assert re.search(r"finally\s*\{\s*sondeandoEstado = false", html), (
            "si el sondeo sale por una excepción, la guarda se queda puesta y "
            "no vuelve a sondearse nunca"
        )

    def test_la_barra_va_en_indeterminado(self):
        """Sin `task_id` no hay «cuántas van de cuántas». Poner un número sería
        inventárselo; quitarle el `value` a un `<progress>` lo deja
        indeterminado, que es lo que de verdad sabemos."""
        html = DETALLE.read_text(encoding="utf-8")

        assert "removeAttribute('value')" in html

    def test_al_terminar_se_recarga_la_situacion(self):
        """Si no, la página se queda con el contenido de antes de generar: sin
        barra pero también sin las secciones nuevas."""
        html = DETALLE.read_text(encoding="utf-8")
        i = html.index("async function seguirGeneracionEnCurso")
        cuerpo = html[i:i + 1400]

        assert "await cargar()" in cuerpo
