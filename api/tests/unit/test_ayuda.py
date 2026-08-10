"""Que el portal de ayuda no prometa cosas que no existen.

POR QUÉ ESTE FICHERO
---------------------
Ayuda ha mentido dos veces, y las dos por el mismo motivo: se escribió leyendo
la hoja de ruta en lugar del código.

* El 07/08/2026 decía «puedes darte de baja desde tu perfil» cuando no había
  ningún botón. Se corrigió a mano.
* Hasta el 10/08/2026 decía que al restablecer la contraseña «no se envía
  ningún correo de confirmación, porque AWEBO todavía no tiene servidor de
  correo». Llevaba un día siendo falso: la tarea 11 lo había implementado.

Las dos veces el texto era plausible y nadie lo notó. Lo que sigue no puede
comprobar que una frase sea verdad —para eso hay que leerla—, pero sí ata la
parte mecánica: que todo enlace que ofrece lleve a algún sitio.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


AYUDA = Path(__file__).resolve().parents[2] / "app" / "templates" / "ayuda.html"


def _enlaces_internos() -> set[str]:
    """Los `href="/..."` que aparecen en la plantilla, incluidos los de dentro
    de cadenas traducibles marcadas con `|safe`."""
    texto = AYUDA.read_text(encoding="utf-8")
    return {m.group(1) for m in re.finditer(r'href=\\?"(/[^"\\#?]*)', texto)}


def test_hay_enlaces_que_comprobar():
    """Si el detector deja de encontrar nada, los demás tests pasarían solos."""
    assert len(_enlaces_internos()) >= 3, _enlaces_internos()


@pytest.mark.parametrize("ruta", sorted(_enlaces_internos()))
def test_cada_enlace_de_la_ayuda_lleva_a_una_pagina_real(app, client, ruta):
    """Un enlace roto en la ayuda es peor que no ponerlo: manda a alguien que
    ya estaba perdido a una página que no existe.

    Se comprueba contra el mapa de rutas y no pidiendo la página, porque
    muchas exigen sesión y aquí no interesa el permiso sino la existencia.
    """
    coincide = app.url_map.bind("localhost")
    try:
        coincide.match(ruta, method="GET")
    except Exception as exc:  # NotFound, MethodNotAllowed…
        pytest.fail(f"la ayuda enlaza a {ruta}, que no existe: {type(exc).__name__}")


def test_la_ayuda_no_dice_que_falte_el_correo():
    """La frase concreta que estuvo mintiendo un día entero.

    No es un test general —no puede serlo—, pero esta afirmación ya se quedó
    obsoleta una vez y volvería a hacerlo si alguien copiara el párrafo.
    """
    texto = AYUDA.read_text(encoding="utf-8")
    for frase in ("todavía no tiene servidor de correo",
                  "no se envía ningún correo",
                  "no hay opción de darse de baja"):
        assert frase not in texto, (
            f"la ayuda sigue diciendo «{frase}», y eso dejó de ser cierto"
        )
