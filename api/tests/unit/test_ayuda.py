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


#: Las carpetas de salida del extractor, que son lo que siembra el catálogo.
#: Se leen estas y no la base de datos porque la batería no tiene currículo
#: sembrado, y porque el desfase que este fichero persigue es entre la página y
#: **lo que hay extraído**, que es lo que se carga.
SALIDAS = Path(__file__).resolve().parents[2].parent / "curriculo"

#: La página está en castellano y el catálogo guarda el nombre oficial en la
#: lengua de cada norma. Sin esta tabla, buscar «Segunda Lengua Extranjera» en
#: los ficheros no encuentra nada y el test pasaría en verde diciendo que la
#: materia no está — que es exactamente la conclusión falsa que hubo que
#: deshacer el 23/09.
NOMBRES_OFICIALES = {
    "Segunda Lengua Extranjera": (
        "Segona Llengua Estrangera",       # Cataluña
        "Segunda Lingua Estranxeira",      # Galicia
        "ATZERRIKO BIGARREN HIZKUNTZA",    # País Vasco
    ),
}


def _bloques():
    """Todos los bloques de currículo extraído, de las diez carpetas."""
    import json

    for fichero in SALIDAS.glob("salida*/*.json"):
        datos = json.loads(fichero.read_text(encoding="utf-8"))
        for bloque in (datos if isinstance(datos, list) else [datos]):
            yield bloque


def test_hay_curriculo_que_comprobar():
    """Regla 15. Si `SALIDAS` deja de apuntar a donde debe —dentro del
    contenedor el currículo se monta en `/curriculo`—, los dos tests de abajo
    no encontrarían ninguna materia y pasarían los dos en verde afirmando que
    nada está cargado."""
    assert SALIDAS.is_dir(), (
        f"no está {SALIDAS}. Se monta en /curriculo: mira los `volumes` de "
        f"docker-compose.override.yml y el paso `pytest` de la CI."
    )
    assert sum(1 for _ in _bloques()) > 500, "el detector no lee los bloques"


@pytest.mark.parametrize("etapa", ("ESO", "Bachillerato"))
def test_la_ayuda_no_niega_una_etapa_que_esta_cargada(etapa):
    """El fallo que puso este test.

    La página decía «Están disponibles las materias de Educación Secundaria
    Obligatoria. **Bachillerato y Formación Profesional todavía no**». Era
    cierto cuando se escribió y dejó de serlo el 19/09, cuando Bachillerato
    entró en las cinco comunidades. Nadie la tocó, porque una página de ayuda
    no se estropea: se queda vieja sola.

    Formación Profesional sigue fuera, así que la frase no se puede vigilar
    entera. Lo que sí se puede es esto: si hay currículo extraído de una etapa,
    la ayuda no puede decir que no lo hay.
    """
    if not any(b.get("etapa") == etapa for b in _bloques()):
        pytest.skip(f"no hay currículo de {etapa} extraído")

    texto = AYUDA.read_text(encoding="utf-8")
    for frase in (f"{etapa} y Formación Profesional todavía no",
                  f"{etapa} todavía no",
                  f"{etapa} no está disponible"):
        assert frase not in texto, (
            f"la ayuda dice «{frase}» y hay currículo de {etapa} cargado"
        )


@pytest.mark.parametrize("castellano, oficiales", sorted(NOMBRES_OFICIALES.items()))
def test_la_ayuda_no_declara_ausente_una_materia_cargada(castellano, oficiales):
    """La afirmación que estuvo mal más tiempo, y peor comprobada.

    «Segunda Lengua Extranjera no aparece en el desplegable. No es un olvido:
    el BOE no le publica currículo propio.» La segunda frase es cierta **de la
    vía del BOE**, que es la de Ceuta y Melilla. Cataluña, Galicia y el País
    Vasco sí le dan currículo propio, y está extraído: un docente de esas tres
    comunidades la ve en el desplegable mientras la ayuda le dice que no
    existe.

    Se dio por comprobada dos veces y las dos con el mismo error de método:
    mirar solo `curriculo/salida/`, que es la carpeta estatal, y escribir la
    conclusión como si valiera para las diez. De ahí que este test recorra
    `salida*` entera.
    """
    cargada = {
        (b.get("comunidad"), b.get("etapa"))
        for b in _bloques()
        if (b.get("materia_oficial") or "").strip() in oficiales
    }
    if not cargada:
        pytest.skip(f"{castellano} no está cargada en ninguna comunidad")

    texto = AYUDA.read_text(encoding="utf-8")
    for frase in (f"{castellano}</strong> no aparece en el desplegable",
                  f"{castellano}, no está disponible",
                  f"{castellano} no está disponible"):
        assert frase not in texto, (
            f"la ayuda dice «{frase}», y {castellano} está cargada en "
            f"{sorted(c for c, _ in cargada if c)}. Si la frase quiere decir "
            f"«en algunas comunidades no», tiene que decirlo así."
        )


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
