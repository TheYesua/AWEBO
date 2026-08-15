"""Que la tabla del listado se pueda leer entera al estrechar la ventana.

EL FALLO, QUE ES CONTRAINTUITIVO
---------------------------------
El listado ya estaba dentro de `.tabla-responsiva`, que tiene
`overflow-x: auto`. Y aun así, al estrechar la ventana, la columna «Modificada»
y el botón «Abrir» se cortaban, **y arrastrar la barra horizontal no servía de
nada**.

El motivo es que `width: 100%` le dice a la tabla que quepa siempre en su
contenedor. Y cabe: comprimiendo las columnas hasta que el texto ya no entra.
Como cabe, **no hay desbordamiento que scrollear**, así que el scroll aparece
sin recorrido y el contenido queda recortado igual.

Un contenedor con `overflow-x` no basta si lo de dentro se niega a desbordar.
"""
from __future__ import annotations

import re
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]
CSS = _RAIZ / "app" / "static" / "css" / "styles.css"
LISTAR = _RAIZ / "app" / "templates" / "situaciones" / "listar.html"


class TestLaTablaSeNiegaAAplastarse:
    def test_tiene_un_ancho_minimo_dentro_del_contenedor_con_scroll(self):
        """Sin `min-width` la tabla cabe siempre, y el `overflow-x` del padre
        no tiene nada que desplazar."""
        css = CSS.read_text(encoding="utf-8")

        m = re.search(r"\.tabla-responsiva\s*>\s*\.api\s*\{[^}]*min-width\s*:\s*(\d+)", css)

        assert m, "la tabla del listado no declara min-width: volverá a aplastarse"
        assert int(m.group(1)) >= 30, "un mínimo tan bajo no evita el recorte"

    def test_el_contenedor_sigue_teniendo_scroll_horizontal(self):
        """La otra mitad. Con `min-width` y sin `overflow-x`, la tabla
        desbordaría la página entera en vez de su caja."""
        css = CSS.read_text(encoding="utf-8")

        assert re.search(r"\.tabla-responsiva\s*\{[^}]*overflow-x\s*:\s*auto", css)


class TestLasDosColumnasQueSeCortaban:
    def test_la_fecha_y_las_acciones_no_se_parten(self):
        """Una fecha partida en dos líneas es ilegible, y un botón partido no
        se puede pulsar del todo."""
        css = CSS.read_text(encoding="utf-8")

        bloque = re.search(
            r"\.api td\.fecha[^{]*\{[^}]*white-space\s*:\s*nowrap", css, re.S
        )
        assert bloque, "la fecha y las acciones pueden volver a partirse"

    def test_las_celdas_llevan_su_clase_en_la_plantilla(self):
        """El CSS no sirve de nada si el HTML no marca las celdas. Se comprueba
        en la cabecera **y** en la fila que genera el JavaScript: son dos
        sitios distintos y el segundo es fácil de olvidar."""
        html = LISTAR.read_text(encoding="utf-8")

        assert 'scope="col" class="fecha"' in html
        assert 'scope="col" class="acciones"' in html
        assert '<td class="fecha">' in html
        assert '<td class="acciones">' in html
