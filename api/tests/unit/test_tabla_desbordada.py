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


PANEL = _RAIZ / "app" / "templates" / "admin" / "panel.html"


class TestLaCeldaDeBotonesSigueSiendoUnaCelda:
    """`display: flex` en un `<td>` lo saca del layout de tabla.

    EL FALLO
    ---------
    El panel tenía `.tabla-admin td:last-child { display: flex }` para alinear
    los botones. Una celda con `display: flex` deja de ser celda: **no se
    estira a la altura de su fila**. Medido en el navegador sobre la tabla
    real, con una fila de dos renglones y dos de uno:

        celda de acciones   35, 35, 35
        resto de la fila    61, 39, 39

    El resultado es la línea separadora de la última columna partida y sin
    juntar de una fila a otra, que es como se vio.

    Y tenía un segundo síntoma ya documentado en el propio CSS: la fila de
    edición desplegable necesitaba un `display: table-cell` a mano para
    contrarrestar esta misma regla, porque alcanzaba a cualquier última celda
    fuera o no de botones.

    Se comprueba la forma —el selector— y no el comportamiento, que aquí
    necesitaría un navegador. Es la excepción que admite la regla 3: para CSS
    no hay término medio barato entre leer el fichero y levantar Chromium, y
    el de accesibilidad ya levanta uno pero no mide alturas de celda.
    """

    def test_ninguna_regla_pone_flex_o_grid_en_una_celda(self):
        # Sin quitar los comentarios, el propio comentario que explica este
        # fallo —que cita `td:last-child` y `display: flex`— se cuenta como
        # una regla y el test se pone rojo por documentar bien.
        css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)

        culpables = [
            bloque for bloque in re.findall(r"([^{}]*td[^{}]*)\{([^}]*)\}", css)
            if re.search(r"display\s*:\s*(flex|grid|block)", bloque[1])
            and not re.search(r"display\s*:\s*table-cell", bloque[1])
        ]

        assert culpables == [], (
            f"una celda con display distinto de table-cell deja de estirarse "
            f"a la altura de su fila: {[c[0].strip() for c in culpables]}"
        )

    def test_los_botones_van_en_su_propio_envoltorio(self):
        css = CSS.read_text(encoding="utf-8")
        panel = PANEL.read_text(encoding="utf-8")

        assert re.search(r"\.celda-acciones\s*\{[^}]*display\s*:\s*flex", css), (
            "el flex de los botones tiene que vivir en el envoltorio"
        )
        assert "celda-acciones" in panel, (
            "el panel ya no crea el envoltorio: los botones volverían al `<td>`"
        )
