"""El filtro de idioma del panel de administración.

POR QUÉ ESTÁ AQUÍ Y NO EN /situaciones
---------------------------------------
El listado del docente no lleva filtro de idioma a propósito: casi todas las
SdA de una cuenta están en el mismo idioma, así que el desplegable ocuparía
sitio sin separar nada. En /admin sí, porque ahí se ven las de todo el mundo.

LO QUE SE COMPRUEBA
-------------------
Que el desplegable y el validador digan lo mismo. Un desplegable escrito a
mano es un contrato duplicado: el día que se añada o se quite un idioma del
modelo, la plantilla seguirá ofreciendo el viejo y el usuario verá un error
—o peor, un listado vacío— por elegir algo que la propia página le ofreció.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.situacion import SituacionAprendizaje
from app.services import admin_service as svc

_RAIZ = Path(__file__).resolve().parents[2]
PANEL = _RAIZ / "app" / "templates" / "admin" / "panel.html"
VISTA = _RAIZ / "app" / "api" / "admin.py"


class TestElDesplegableNoSeEscribeAMano:
    def test_las_opciones_salen_del_modelo(self):
        html = PANEL.read_text(encoding="utf-8")

        assert re.search(
            r'<select id="filtro-idioma".*?idiomas_sda\.items\(\).*?</select>',
            html,
            re.S,
        ), "el desplegable de idioma tiene que recorrer idiomas_sda"

    def test_la_vista_le_pasa_la_lista_del_modelo(self):
        codigo = VISTA.read_text(encoding="utf-8")

        assert "idiomas_sda=SituacionAprendizaje.IDIOMAS" in codigo, (
            "panel() tiene que pasar la lista del modelo, no una copia"
        )

    def test_ningun_codigo_de_idioma_aparece_escrito_en_la_plantilla(self):
        """Lo que se persigue no es el texto sino la copia: si algún día
        alguien mete `<option value="fr">` aquí, este test lo dice."""
        html = PANEL.read_text(encoding="utf-8")
        bloque = re.search(
            r'<select id="filtro-idioma".*?</select>', html, re.S
        )
        assert bloque, "no está el desplegable de idioma"

        valores = re.findall(r'<option value="([^"]*)"', bloque.group(0))

        # El «Todos», que no es un idioma sino su ausencia, y la expresión del
        # bucle. Cualquier otra cosa es un código copiado.
        assert valores == ["", "{{ codigo }}"], (
            f"opciones escritas a mano: {valores}"
        )


class TestElValidadorRechazaLoQueNoOfrece:
    def test_un_idioma_inventado_da_error_y_no_un_listado_vacio(self):
        """Antes de tocar la base de datos: un valor puesto a mano en la URL
        no puede parecerse a «no hay ninguna».

        El código de prueba se deriva de la lista y no se escribe: «fr» parecía
        inventado y está en IDIOMAS, así que el test habría pasado por la razón
        contraria a la que dice."""
        inventado = "zz"
        assert inventado not in SituacionAprendizaje.IDIOMAS

        with pytest.raises(svc.AdminError) as exc:
            svc.listar_situaciones(idioma=inventado)

        assert exc.value.code == "idioma_desconocido"

    # AQUÍ HUBO UN TEST Y COLGÓ LA BATERÍA ENTERA. No se repone.
    #
    # Comprobaba «el otro lado del contrato»: que los idiomas que el
    # desplegable ofrece pasen la validación. Llamaba a `listar_situaciones`
    # con cada uno de los siete y envolvía el resultado en
    # `except Exception: pass`, porque en un entorno sin Postgres la llamada
    # revienta al llegar a la consulta.
    #
    # En Docker sí hay Postgres, así que la consulta se ejecutaba. Y como el
    # fixture `app` es de ámbito sesión y mantiene un contexto de aplicación
    # abierto, un test puede tocar la base de datos **sin pedir el fixture
    # `db`** — que es el que limpia después. Los siete SELECT dejaban una
    # transacción abierta con su ACCESS SHARE sobre `situacion_aprendizaje`, y
    # el siguiente `TRUNCATE` del fixture `db` se quedaba esperando ese bloqueo
    # para siempre. La batería colgaba al 74 %, en el primer test de
    # `test_i18n.py` que pide `db`.
    #
    # No se repone porque además no medía nada: las opciones y el validador
    # leen el MISMO diccionario `IDIOMAS`, así que comparar uno con otro es
    # comparar algo consigo mismo. Que no se separen ya lo vigilan los tres
    # tests de arriba, y sin tocar la base de datos.
    #
    # Lo que queda como lección: `except Exception: pass` no hacía el test
    # portátil, lo hacía silencioso. Escondió que la llamada sí llegaba a la
    # base de datos, que es justo lo que había que saber.
