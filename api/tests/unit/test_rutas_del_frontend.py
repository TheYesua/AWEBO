"""Que las URL a las que llama el JavaScript de las plantillas existan.

EL HUECO QUE TAPA
-----------------
`tests/js/llamadas.test.js` ya comprueba que el JavaScript no invoque funciones
inexistentes — nació porque una plantilla llamaba a `escapeHtml`, que ahí no
existe, y ninguna SdA mostraba su contenido durante un día. Pero una llamada a
`fetch('/api/situaciones/1/audioo')` es JavaScript perfectamente válido, con
funciones que existen, y falla solo cuando alguien pulsa el botón.

Este fichero cierra ese hueco desde el otro lado: extrae las rutas de los
`fetch` de las plantillas y comprueba que Flask las conoce. Es barato porque el
mapa de rutas ya está construido.

LO QUE NO COMPRUEBA
-------------------
Que el método coincida, que los parámetros sean los correctos o que la
respuesta tenga la forma esperada. Solo que la dirección lleve a algún sitio.
Es el equivalente al test de enlaces del portal de ayuda: la parte mecánica.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


PLANTILLAS = Path(__file__).resolve().parents[2] / "app" / "templates"

#: Cualquier literal que sea una ruta de la API, **esté o no dentro de un
#: `fetch(`**.
#:
#: La primera versión miraba solo dentro de `fetch(...)`, y con eso no vio
#: nada: `detalle.html` construye la URL del audio en una función auxiliar y
#: se la pasa después a `fetch`. Al sabotear la URL a propósito, el test
#: seguía en verde. Es la misma ceguera que tuvo el detector de cadenas sin
#: traducir: **un detector que no ve el caso que lo motivó no vale**.
#:
#: Se acota a los prefijos que son rutas de verdad —`/api`, `/auth`, `/admin`,
#: `/me`— en lugar de a cualquier cadena que empiece por barra, que arrastraría
#: rutas de ficheros y de CSS.
_RUTA = re.compile(r"""[`'"](/(?:api|auth|admin|me)/[^`'"\s]*)[`'"]""")


def _rutas_llamadas() -> set[tuple[str, str]]:
    """Pares (plantilla, ruta) con las interpolaciones neutralizadas."""
    encontradas = set()
    for plantilla in PLANTILLAS.rglob("*.html"):
        texto = plantilla.read_text(encoding="utf-8")
        for cruda in _RUTA.findall(texto):
            # `${ID}` y compañía se sustituyen por un número: lo que se
            # comprueba es la forma de la ruta, no el valor concreto.
            ruta = re.sub(r"\$\{[^}]*\}", "1", cruda).split("?")[0]
            encontradas.add((plantilla.relative_to(PLANTILLAS).as_posix(), ruta))
    return encontradas


def test_hay_llamadas_que_comprobar():
    """Si el detector deja de encontrar nada, el test de abajo pasaría solo."""
    # Eran 31 al escribir esto. El umbral va holgado para que no salte al
    # añadir o quitar una, pero sí si el detector se rompe del todo.
    assert len(_rutas_llamadas()) >= 25, _rutas_llamadas()


@pytest.mark.parametrize("plantilla,ruta", sorted(_rutas_llamadas()))
def test_cada_fetch_apunta_a_una_ruta_real(app, plantilla, ruta):
    adaptador = app.url_map.bind("localhost")
    for metodo in ("GET", "POST", "PUT", "DELETE"):
        try:
            adaptador.match(ruta, method=metodo)
            return
        except Exception:
            continue
    pytest.fail(f"{plantilla} llama a {ruta}, que no existe en el mapa de rutas")
