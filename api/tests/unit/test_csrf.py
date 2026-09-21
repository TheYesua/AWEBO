"""La protección CSRF: el servidor, la plantilla y el envoltorio de `fetch`.

QUÉ SE PROTEGE
--------------
Que un sitio ajeno no pueda hacer que el navegador de un docente con la sesión
abierta ejecute una acción en AWEBO. El navegador adjunta la cookie por
destino, no por procedencia, así que sin esto bastaría un formulario oculto
para borrar una SdA.

LOS TRES NIVELES, Y POR QUÉ HACEN FALTA LOS TRES
-------------------------------------------------
El grueso de la comprobación —que un POST sin token se rechaza— lo ejercitan
ya los **298 tests** que hacen peticiones que cambian estado: su cliente manda
el token igual que lo haría un navegador, así que todos recorren la validación
de verdad. Este fichero cubre lo que aquellos no pueden ver:

1. Que **rechaza** de verdad. Los 298 mandan el token bueno; si la validación
   aceptara cualquier cosa, seguirían verdes.
2. Que la **plantilla** publica el token donde el navegador lo busca.
3. Que el **envoltorio de `fetch`** sigue en su sitio. Es el eslabón que no
   puede probar ningún test de Python y el más fácil de romper sin enterarse:
   son cuatro líneas en un fichero de JavaScript que nadie vuelve a mirar, y
   si desaparecen la aplicación deja de funcionar entera en el navegador
   mientras la batería sigue en verde.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import csrf

_RAIZ = Path(__file__).resolve().parents[2]
BASE_HTML = _RAIZ / "app" / "templates" / "base.html"
APP_JS = _RAIZ / "app" / "static" / "js" / "app.js"


class TestElServidorRechaza:
    """Lo que los 298 tests con token bueno no pueden demostrar."""

    def test_sin_token_no_se_puede_cambiar_nada(self, client):
        """`X-CSRF-Token` vacío: el cliente de pruebas no lo pisa, justo para
        que se pueda escribir este test."""
        respuesta = client.post("/auth/login", json={}, headers={"X-CSRF-Token": ""})

        assert respuesta.status_code == 403

    def test_con_un_token_inventado_tampoco(self, client):
        respuesta = client.post(
            "/auth/login", json={}, headers={"X-CSRF-Token": "me-lo-invento"}
        )

        assert respuesta.status_code == 403

    def test_un_token_de_otra_sesion_no_sirve(self, client):
        """El token va atado a la sesión, que es lo que distingue esto de un
        «doble envío» con una cookie firmada: un subdominio ajeno podría
        fabricar un par coherente, pero no conoce la sesión."""
        with client.session_transaction() as sesion:
            sesion[csrf.CLAVE_SESION] = "el-token-de-otro"

        respuesta = client.post(
            "/auth/login", json={}, headers={"X-CSRF-Token": "token-csrf-de-pruebas"}
        )

        assert respuesta.status_code == 403

    def test_leer_no_necesita_token(self, client):
        """El control negativo, y no es decorativo: una validación que
        rechazara también los GET dejaría la aplicación inservible, y los tests
        de arriba seguirían pasando tan contentos."""
        respuesta = client.get("/ayuda", headers={"X-CSRF-Token": ""})

        assert respuesta.status_code == 200

    @pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
    def test_ningun_metodo_que_cambia_estado_se_escapa(self, client, metodo):
        """Se recorren los cuatro en vez de fiarse del POST: la lista de
        métodos seguros se escribe a mano, y una letra de más ahí abre un
        agujero que solo se ve probándolos."""
        respuesta = getattr(client, metodo)(
            "/api/situaciones/1", headers={"X-CSRF-Token": "malo"}
        )

        assert respuesta.status_code == 403


class TestLaPlantillaPublicaElToken:
    def test_base_html_trae_la_etiqueta_meta(self):
        html = BASE_HTML.read_text(encoding="utf-8")

        assert re.search(
            r'<meta name="csrf-token" content="\{\{ csrf_token\(\) \}\}"', html
        ), "sin el <meta>, el envoltorio de `fetch` no encuentra el token"

    def test_el_formulario_de_idioma_lo_lleva_en_un_campo_oculto(self):
        """Es el único formulario HTML de verdad que queda, y tiene que
        funcionar sin JavaScript —lleva su `<noscript>`—, así que la cabecera
        no le vale."""
        html = BASE_HTML.read_text(encoding="utf-8")

        assert '<input type="hidden" name="_csrf"' in html

    def test_el_nombre_del_campo_es_el_que_espera_el_servidor(self):
        """Las dos mitades del contrato, comparadas. Escritas en ficheros de
        lenguajes distintos, es la clase de par que se desincroniza sin que
        nada proteste."""
        html = BASE_HTML.read_text(encoding="utf-8")

        assert f'name="{csrf.NOMBRE_CAMPO}"' in html

    def test_el_token_se_puede_pedir_en_una_pagina(self, client):
        """De punta a punta: que `csrf_token()` esté disponible en Jinja y que
        la página salga con un token dentro."""
        html = client.get("/ayuda").get_data(as_text=True)

        encontrado = re.search(r'name="csrf-token" content="([^"]+)"', html)
        assert encontrado, "la página no publica ningún token"
        assert len(encontrado.group(1)) > 20


class TestElEnvoltorioDeFetch:
    """El eslabón que no puede probar ningún test de Python.

    Son unas pocas líneas en `app.js`, lejos de las cuarenta llamadas que
    protegen. Si alguien las borra al limpiar el fichero, la batería no se
    entera y la aplicación deja de funcionar en el navegador: cada botón
    devolvería 403. Estos tests son el aviso.
    """

    def test_app_js_envuelve_fetch(self):
        js = APP_JS.read_text(encoding="utf-8")

        assert "window.fetch = function" in js, (
            "sin el envoltorio, ninguna llamada manda el token y toda la "
            "aplicación devuelve 403 en el navegador"
        )

    def test_manda_la_cabecera_que_el_servidor_lee(self):
        js = APP_JS.read_text(encoding="utf-8")

        assert csrf.NOMBRE_CABECERA in js, (
            f"el servidor lee {csrf.NOMBRE_CABECERA} y app.js manda otra cosa"
        )

    def test_no_manda_el_token_fuera_del_propio_origen(self):
        """Mandar el token a un tercero sería regalarle justo lo que esto
        protege."""
        js = APP_JS.read_text(encoding="utf-8")

        assert "esPropio" in js and "window.location.origin" in js

    def test_se_carga_antes_que_los_scripts_de_cada_pagina(self):
        """`app.js` tiene que estar en `base.html` **antes** del bloque
        `scripts`, o una página que llame a `fetch` al cargarse lo haría con el
        `fetch` sin envolver."""
        html = BASE_HTML.read_text(encoding="utf-8")

        posicion_app_js = html.find("js/app.js")
        posicion_bloque = html.find("{% block scripts %}")

        assert posicion_app_js != -1 and posicion_bloque != -1
        assert posicion_app_js < posicion_bloque


class TestLaLineaMuertaQueHabia:
    def test_ya_no_queda_ningun_WTF_CSRF_ENABLED(self):
        """`WTF_CSRF_ENABLED = False` estuvo en dos ficheros de test desde
        antes de que existiera ningún CSRF, y **no hacía nada**: Flask-WTF
        nunca se instaló, así que nadie leía esa variable.

        Lo que la hacía dañina no es que sobrara, sino que al leer el fichero
        daba por contestada una pregunta que seguía abierta — cualquiera que
        auditara la configuración habría visto una decisión tomada donde no
        había ninguna. Este test existe para que no vuelva.
        """
        # Busca la **asignación**, no la mención. Escrito primero como un `in`
        # a secas, el test se puso rojo señalando los dos comentarios que
        # explican por qué la línea se quitó — segunda vez en tres días que un
        # escáner de código fuente se caza su propia documentación. Un test que
        # castiga explicar la causa se «arregla» borrando la explicación.
        asignacion = re.compile(r"^\s*WTF_CSRF_ENABLED\s*=", re.M)

        sobrevivientes = [
            str(f.relative_to(_RAIZ))
            for f in (_RAIZ / "tests").rglob("*.py")
            if f.name != "test_csrf.py"
            and asignacion.search(f.read_text(encoding="utf-8"))
        ]

        assert not sobrevivientes, (
            f"{sobrevivientes} declaran WTF_CSRF_ENABLED, que no lee nadie: "
            "Flask-WTF no está instalado. La protección es `app/csrf.py`."
        )
