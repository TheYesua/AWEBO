"""Los idiomas que se ofrecen, y los tres que se retiraron el 22/09/2026.

QUÉ SE QUITÓ Y POR QUÉ
-----------------------
`IDIOMAS` ofrecía inglés, francés y árabe además de las cuatro lenguas
cooficiales. Ninguno de los tres se sostenía:

* **Ninguno tiene voz.** La síntesis local cubre castellano, catalán, gallego y
  euskera, y nada más.
* **El árabe se escribe de derecha a izquierda** y ni el PDF ni el DOCX lo
  contemplan: el documento salía mal maquetado.

Ofrecer un idioma cuyo documento sale peor que el original no es una
funcionalidad de más: es una promesa incumplida justo donde el docente menos
puede comprobarla, porque para eso tendría que saber el idioma.

LO QUE ESTE FICHERO **NO** HACE, PORQUE YA ESTABA HECHO
--------------------------------------------------------
No comprueba que el `Literal` del esquema, el prompt de traducción y los dos
`<select>` coincidan con `IDIOMAS`. Eso lo cubre
`test_modelos.py::TestIdiomasDeUnaSituacion` desde que la lista se unificó, y
duplicarlo aquí solo añadiría un sitio más que mantener — que es precisamente
el problema que aquel test vino a resolver.

La primera versión de este fichero sí lo duplicaba. Queda escrito porque es la
tercera vez esta semana que escribo algo que el proyecto ya tenía: antes fue
`_raiz()` en `test_configuracion.py` y el `\\s*` de `RX_OBXECTIVO`. La regla que
va saliendo es mirar el test de al lado antes de escribir el propio.

LO QUE SÍ CUBRE
---------------
Los cuatro huecos que aquel test deja: que los retirados no vuelvan por
descuido, el diccionario de rótulos de `detalle.html`, la frase de `ayuda.html`
—donde una lista desactualizada no la caza ningún test de tipos— y la relación
con los idiomas que de verdad tienen voz, que es el motivo de la poda.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.situacion import SituacionAprendizaje

_APP = Path(__file__).resolve().parents[2] / "app"
NUEVA = _APP / "templates" / "situaciones" / "nueva.html"
DETALLE = _APP / "templates" / "situaciones" / "detalle.html"
AYUDA = _APP / "templates" / "ayuda.html"

#: Los que se quitaron. Se nombran para que reaparecer sea imposible por
#: descuido: volver a ofrecerlos exige borrar su línea de aquí, y eso es un
#: acto deliberado y no un `<option>` copiado.
RETIRADOS = ("en", "fr", "ar")


class TestLosRetiradosNoVuelven:
    @pytest.mark.parametrize("codigo", RETIRADOS)
    def test_no_estan_en_el_modelo(self, codigo):
        assert codigo not in SituacionAprendizaje.IDIOMAS

    @pytest.mark.parametrize("codigo", RETIRADOS)
    def test_no_estan_en_ningun_selector(self, codigo):
        for ruta in (NUEVA, DETALLE):
            html = ruta.read_text(encoding="utf-8")
            bloque = re.search(r'<select id="idioma".*?</select>', html, re.S)
            assert bloque, f"no hay selector de idioma en {ruta.name}"
            assert f'value="{codigo}"' not in bloque.group(0)

    @pytest.mark.parametrize("palabra", ["inglés", "francés", "árabe"])
    def test_la_ayuda_no_los_promete(self, palabra):
        """La página de ayuda los nombraba en una frase corrida, que es el
        sitio donde una lista desactualizada no la caza ningún test de tipos ni
        ningún validador: solo la lee un humano, y tarde."""
        assert palabra not in AYUDA.read_text(encoding="utf-8")


class TestLosRotulosDeDetalle:
    """`T.idiomas`, que es con lo que se dice «no hay voz para X».

    No lo cubre el test de los `<select>` porque no es un selector: es un
    diccionario de JavaScript. Un idioma que falte ahí no rompe nada, solo hace
    que el aviso salga con el código en crudo — «no hay voz para eu»—, que es
    de las cosas que nadie reporta y nadie arregla.
    """

    def _rotulados(self) -> set[str]:
        html = DETALLE.read_text(encoding="utf-8")
        # Hasta el cierre del bloque con su sangría, y no con `\\{(.*?)\\}`:
        # los valores son `{{ _('…')|tojson }}`, así que el primer `}` que
        # aparece es el de una expresión de Jinja y la versión perezosa cortaba
        # ahí. El test daba rojo con el fichero correcto.
        bloque = re.search(r"\n  idiomas: \{\n(.*?)\n  \},", html, re.S)
        assert bloque, "no se encuentra el diccionario T.idiomas"
        return set(re.findall(r"^\s*(\w+):", bloque.group(1), re.M))

    def test_cubre_todos_los_idiomas_y_ninguno_mas(self):
        assert self._rotulados() == set(SituacionAprendizaje.IDIOMAS)


class TestLoQueSiSeSostiene:
    @pytest.mark.parametrize("codigo", ["es", "ca", "gl", "eu"])
    def test_las_cuatro_cooficiales_siguen(self, codigo):
        """El control negativo. Sin él, un `IDIOMAS` vacío pasaría todos los
        tests de arriba tan contento."""
        assert codigo in SituacionAprendizaje.IDIOMAS

    def test_son_las_mismas_que_tienen_voz(self):
        """La poda se hizo por la voz, así que se comprueba contra ella y no
        contra una lista escrita otra vez.

        Si algún día aHoTTS cubre una lengua más, este test señala el sitio
        exacto donde ampliar la oferta; y si se ofrece una sin voz, avisa antes
        de que un docente se encuentre el botón de audio sin funcionar.
        """
        # `LENGUAS` es el diccionario con el que `_comprobar_instalacion`
        # decide si hay voz: si un código no está ahí, la síntesis responde
        # «No hay voz para el idioma X». Es la fuente de verdad, no una lista
        # paralela.
        #
        # La primera versión buscaba un atributo que no existe y se **saltaba**
        # el test. Un test que se salta no vigila nada, y ese mismo fichero de
        # configuración del proyecto ya lo deja escrito para `importorskip`.
        from app.voz.local import LENGUAS

        assert set(SituacionAprendizaje.IDIOMAS) == set(LENGUAS)
