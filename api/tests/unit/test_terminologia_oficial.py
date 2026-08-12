"""La terminología curricular coincide con la de los decretos autonómicos.

POR QUÉ MERECE UN FICHERO PROPIO
---------------------------------
`test_i18n.py` ya vigila que no falten cadenas y que ninguna sea una
adivinanza de `pybabel`. Nada de eso mira **si lo traducido es lo correcto**:
una traducción puede estar completa, no ser `fuzzy` y aun así llamar a las
cosas por un nombre que ningún docente de esa comunidad reconocería.

Y ese fallo es peor que un hueco. Una cadena sin traducir se ve: sale en
castellano y canta. Un término mal elegido se lee bien y hace pensar que la
herramienta no conoce el currículo con el que trabajas.

QUÉ ES ESTE TEST Y QUÉ NO ES
-----------------------------
**Sí es** una red que impide que estas decisiones concretas se deshagan sin
querer. Cada término de abajo se contrastó el 11/08/2026 contra el texto
oficial en la propia lengua, no contra una traducción de él:

* **ca** — Decret 175/2022, materiales del currículum de la XTEC.
* **gl** — Decreto 156/2022, texto gallego del DOG 183 del 26/09/2022.
* **eu** — 77/2023 Dekretua, versión en euskera del BOPV.

**No es** una revisión de la traducción. Cubre el vocabulario curricular, que
es el que tiene forma legal fija; el resto de la interfaz —cientos de cadenas
corrientes— sigue siendo trabajo del asistente y sigue pendiente de que lo
lean hablantes nativos. Que este fichero esté verde no significa que los
catálogos estén revisados.

DUDAS QUE SE DEJAN ABIERTAS A PROPÓSITO
----------------------------------------
En catalán, el Decret 175/2022 nombra el elemento curricular como **«sabers»**
a secas, mientras que los materiales de la XTEC usan también «sabers bàsics».
Se mantiene «Sabers bàsics» porque es lo que aparece en el material que llega
al profesorado y no deja lugar a duda sobre a qué se refiere, pero la elección
es discutible y conviene preguntarla cuando haya a quién.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from babel.messages.pofile import read_po


RAIZ = Path(__file__).resolve().parents[2] / "app" / "translations"


#: msgid -> traducción exacta exigida en cada lengua.
#:
#: Solo entra aquí lo que tiene forma oficial en un decreto. Un término
#: corriente no debe fijarse: convertiría cualquier mejora de estilo en un
#: test rojo, y este fichero dejaría de señalar lo que importa.
OFICIALES = {
    "Situaciones de Aprendizaje": {
        "ca": "Situacions d'Aprenentatge",
        "gl": "Situacións de Aprendizaxe",
        "eu": "Ikaskuntza-egoerak",
    },
    "Criterios de evaluación": {
        "ca": "Criteris d'avaluació",
        "gl": "Criterios de avaliación",
        "eu": "Ebaluazio-irizpideak",
    },
    "Competencias específicas": {
        "ca": "Competències específiques",
        "gl": "Competencias específicas",
        "eu": "Konpetentzia espezifikoak",
    },
    "Saberes básicos": {
        "ca": "Sabers bàsics",
        "gl": "Saberes básicos",
        "eu": "Oinarrizko jakintzak",
    },
}


def _catalogo(idioma: str) -> dict[str, str]:
    with open(RAIZ / idioma / "LC_MESSAGES" / "messages.po", encoding="utf-8") as f:
        cat = read_po(f, locale=idioma)
    return {
        (m.id if isinstance(m.id, str) else m.id[0]): (
            m.string if isinstance(m.string, str) else (m.string or [""])[0]
        )
        for m in cat
        if m.id
    }


@pytest.fixture(scope="module")
def catalogos():
    return {i: _catalogo(i) for i in ("ca", "gl", "eu")}


@pytest.mark.parametrize("idioma", ["ca", "gl", "eu"])
def test_los_terminos_de_los_decretos_se_respetan(catalogos, idioma):
    fallos = []
    for msgid, esperado in OFICIALES.items():
        actual = catalogos[idioma].get(msgid)
        if actual is None:
            continue          # la cadena puede desaparecer de la interfaz
        if actual != esperado[idioma]:
            fallos.append(f"{msgid!r}: es {actual!r}, el decreto dice {esperado[idioma]!r}")
    assert fallos == [], (
        f"{idioma}: terminología que no coincide con el decreto autonómico. "
        f"Si el cambio es deliberado, actualiza OFICIALES citando la fuente: {fallos}"
    )


class TestEuskeraConGuion:
    """El guion de `ikaskuntza-egoera` no es cosmético.

    En euskera marca que el compuesto es una unidad léxica, y el decreto
    77/2023 lo escribe así en todas sus apariciones. Escribirlo separado —como
    estaba— hace que se lea como dos palabras sueltas, «aprendizaje» y
    «situación», que es justo lo que el término no significa.

    Se comprueba sobre **todo** el catálogo y no solo sobre la cadena
    principal, porque el término aparece dentro de frases largas donde es fácil
    que sobreviva la versión antigua.
    """

    def test_ninguna_cadena_lo_escribe_separado(self, catalogos):
        malas = [
            (k, v) for k, v in catalogos["eu"].items()
            if "ikaskuntza egoera" in (v or "").lower()
        ]
        assert malas == [], (
            "en euskera el término va con guion (77/2023 Dekretua): "
            f"{[m[1][:60] for m in malas]}"
        )

    def test_y_alguna_lo_escribe_bien(self):
        """Si el término desapareciera del catálogo, el test de arriba pasaría
        solo. Este comprueba que sigue habiendo algo que vigilar."""
        catalogo = _catalogo("eu")
        assert any("ikaskuntza-egoera" in (v or "").lower() for v in catalogo.values())


class TestLoQueNoSeVigilaAqui:
    """Que conste en el propio fichero, y no solo en el docstring de arriba.

    El riesgo de un test así es que dé sensación de cobertura: alguien lo ve
    verde y da por revisadas las tres lenguas. Este test hace visible la
    proporción real.
    """

    def test_el_vocabulario_fijado_es_una_parte_minima_del_catalogo(self, catalogos):
        total = len([k for k, v in catalogos["ca"].items() if v])
        fijadas = len(OFICIALES)
        assert fijadas < total * 0.1, (
            "si esto falla es buena noticia y hay que reescribir este test, "
            "pero mientras tanto: solo se verifican los términos de decreto"
        )
        # No es una aserción, es el recordatorio que se lee al ejecutar -v.
        print(
            f"\n  Terminología verificada contra decretos: {fijadas} de {total} "
            f"cadenas. El resto sigue pendiente de revisión por hablantes."
        )
