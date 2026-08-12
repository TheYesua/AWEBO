"""Tests de la internacionalización de la interfaz.

Dos cosas distintas: que el idioma se **resuelva** bien —el orden de
precedencia entre perfil, cookie y navegador— y que los catálogos **traduzcan**
de verdad.

Lo segundo importa más de lo que parece: un catálogo mal compilado no da
ningún error, simplemente devuelve el texto original. La aplicación seguiría
funcionando y en castellano, y nadie se enteraría hasta que un docente
catalanoparlante abriera la página.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import render_template_string

from app import i18n


def _render(app, plantilla: str, **kwargs) -> str:
    """Renderiza en un contexto de aplicación NUEVO.

    Lo importante es el ``app_context()``, no el de petición. Flask-Babel
    guarda el idioma que resuelve en ``g._flask_babel.babel_locale``, y ``g``
    vive en el contexto de **aplicación**, no en el de petición.

    ``conftest`` deja un contexto de aplicación abierto durante toda la
    sesión de tests. ``test_request_context()`` no crea uno nuevo si ya lo
    hay: lo reutiliza. Sin este ``app_context()`` los cuatro idiomas
    comparten el mismo ``g``, el primero que se resuelve se queda pegado, y
    los tests de los demás idiomas comprueban el catálogo del primero.

    En producción no ocurre: cada petición empuja su propio contexto de
    aplicación. Solo muerde donde algo mantiene uno abierto —esta suite, una
    tarea Celery, un comando de CLI—.
    """
    with app.app_context(), app.test_request_context(**kwargs):
        return render_template_string(plantilla)


# ---------------------------------------------------------------------------
# Resolución
# ---------------------------------------------------------------------------


class TestResolucion:
    def test_sin_nada_es_castellano(self, app):
        with app.test_request_context("/"):
            assert i18n.resolver_idioma() == "es"

    def test_la_cookie_manda_sobre_el_navegador(self, app):
        with app.test_request_context(
            "/",
            headers={"Cookie": "idioma=ca", "Accept-Language": "gl"},
        ):
            assert i18n.resolver_idioma() == "ca"

    def test_se_usa_el_navegador_si_no_hay_cookie(self, app):
        with app.test_request_context("/", headers={"Accept-Language": "gl,es;q=0.8"}):
            assert i18n.resolver_idioma() == "gl"

    def test_un_idioma_que_no_se_ofrece_cae_al_castellano(self, app):
        with app.test_request_context("/", headers={"Accept-Language": "de,it;q=0.8"}):
            assert i18n.resolver_idioma() == "es"

    def test_una_cookie_manipulada_no_rompe_nada(self, app):
        with app.test_request_context("/", headers={"Cookie": "idioma=<script>"}):
            assert i18n.resolver_idioma() == "es"

    def test_el_perfil_manda_sobre_la_cookie(self, client, db):
        """El idioma acompaña a la persona, no al dispositivo."""
        client.post(
            "/auth/register",
            json={
                "correo": "i18n@test.com",
                "contrasena": "ContraSegura1!",
                "nombre": "Docente Idiomas",
            },
        )
        client.put("/me", json={"idioma_interfaz": "eu"})
        client.set_cookie("idioma", "ca")

        html = client.get("/login").data.decode("utf-8")
        assert 'lang="eu"' in html, "debe ganar el perfil, no la cookie"


# ---------------------------------------------------------------------------
# Los catálogos
# ---------------------------------------------------------------------------


class TestCatalogos:
    """Un catálogo que no carga no da error: devuelve el texto original."""

    @pytest.mark.parametrize(
        "idioma,esperado",
        [
            ("ca", "Les meves situacions"),
            ("gl", "As miñas situacións"),
            ("eu", "Nire egoerak"),
        ],
    )
    def test_traducen(self, app, idioma, esperado):
        salida = _render(
            app,
            "{{ _('Mis situaciones') }}",
            headers={"Cookie": f"idioma={idioma}"},
        )
        assert salida == esperado

    def test_el_castellano_devuelve_el_original(self, app):
        """Su catálogo está vacío a propósito: el origen ya está en castellano,
        así que `msgstr` vacío hace que gettext devuelva el `msgid`."""
        salida = _render(app, "{{ _('Ayuda') }}", headers={"Cookie": "idioma=es"})
        assert salida == "Ayuda"

    @pytest.mark.parametrize(
        "idioma,esperado",
        [
            ("ca", "Situacions d'Aprenentatge"),
            ("gl", "Situacións de Aprendizaxe"),
            ("eu", "Ikaskuntza-egoerak"),
        ],
    )
    def test_la_terminologia_curricular_esta_traducida(self, app, idioma, esperado):
        """El término que más se ve y el que peor sienta mal traducido.

        El euskera llevaba «Ikaskuntza Egoerak», sin guion, desde que se
        escribieron los catálogos. Se corrigió el 11/08/2026 al contrastarlo
        con el texto en euskera del 77/2023 Dekretua, que lo escribe con guion
        en todas sus apariciones: en euskera ese guion marca que el compuesto
        es una unidad léxica, y sin él se lee como dos palabras sueltas.

        Este test **fijaba la forma equivocada**, así que la protegía en vez de
        detectarla. Es el riesgo de escribir un test de terminología sin haber
        mirado la fuente: queda igual de verde y da la misma sensación de
        cobertura. Las fuentes de los tres idiomas están ahora citadas en
        `tests/unit/test_terminologia_oficial.py`.
        """
        salida = _render(
            app,
            "{{ _('Situaciones de Aprendizaje') }}",
            headers={"Cookie": f"idioma={idioma}"},
        )
        assert salida == esperado

    def test_todos_los_idiomas_tienen_catalogo_completo(self):
        """Una cadena sin traducir sale en castellano en medio del catalán:
        peor que no ofrecer el idioma, porque parece un error.

        Se lee el catálogo con el parser de Babel y no buscando ``msgstr ""``
        con una expresión regular, como hacía la primera versión. El formato
        `.po` parte las cadenas largas en varias líneas, y entonces la primera
        es literalmente ``msgstr ""`` seguida del texto:

            msgstr ""
            "Generació assistida de Situacions d'Aprenentatge…"

        Contando líneas, esa traducción figuraba como ausente. El 8/8/2026 el
        test dio 85 cadenas sin traducir en catalán cuando no faltaba ninguna:
        lo único que había cambiado era el ancho con que se reescribió el
        fichero.

        Falsas alarmas, no fallos silenciosos: un `msgstr` vacío ocupa siempre
        una sola línea, así que la versión anterior no dejaba pasar ninguno. El
        problema es que **medía el formato del fichero**, y con eso salta cada
        vez que alguien reescribe un `.po` con otro ancho —``pybabel update``
        parte las líneas por defecto— dejando 85 fallos que no señalan nada.
        Un test que grita sin motivo se acaba ignorando, y ahí sí se cuela algo.
        """
        from pathlib import Path

        from babel.messages.pofile import read_po

        raiz = Path(__file__).resolve().parents[2] / "app" / "translations"
        for idioma in ("ca", "gl", "eu"):
            ruta = raiz / idioma / "LC_MESSAGES" / "messages.po"
            with open(ruta, encoding="utf-8") as f:
                catalogo = read_po(f, locale=idioma)
            sin_traducir = [
                (m.id if isinstance(m.id, str) else m.id[0])
                for m in catalogo
                if m.id and not m.string
            ]
            assert not sin_traducir, (
                f"{idioma} tiene {len(sin_traducir)} cadenas sin traducir: "
                f"{[c[:40] for c in sin_traducir[:5]]}"
            )

    def test_ningun_catalogo_tiene_entradas_dudosas(self):
        """Una entrada `fuzzy` es una traducción **adivinada**, no una traducción.

        Cuando se añade una cadena nueva, ``pybabel update`` busca la más
        parecida que ya exista y copia su traducción marcándola así.
        ``pybabel compile`` las salta, con lo que en pantalla sale el
        castellano; y el texto que dejan escrito no tiene por qué guardar
        ninguna relación con el original.

        No es hipotético. El 8/8/2026, al marcar las cadenas que estaban a
        pelo dentro de los `<script>`, el catálogo catalán tenía «Deshacer»
        traducido como «Escoltar» y «Desarrollar» como «Error». Y siete
        cadenas del centro de ayuda llevaban un día dando por traducidas
        adivinanzas de otras frases.

        Lo que lo hizo invisible: el test de cadenas sin traducir mira que
        `msgstr` no esté vacío, y una fuzzy **no lo está**.
        """
        from pathlib import Path

        from babel.messages.pofile import read_po

        raiz = Path(__file__).resolve().parents[2] / "app" / "translations"
        for idioma in i18n.IDIOMAS:
            ruta = raiz / idioma / "LC_MESSAGES" / "messages.po"
            with open(ruta, encoding="utf-8") as f:
                catalogo = read_po(f, locale=idioma)
            dudosas = [
                (m.id if isinstance(m.id, str) else m.id[0])
                for m in catalogo
                if m.id and m.fuzzy
            ]
            assert not dudosas, (
                f"{idioma} tiene {len(dudosas)} traducciones adivinadas: "
                f"{[d[:40] for d in dudosas[:5]]}. Revísalas y quita la marca "
                f"fuzzy, o saldrán en castellano."
            )

    def test_los_catalogos_estan_compilados(self):
        """Flask-Babel lee `.mo`, no `.po`. Un `.po` traducido y sin compilar
        deja la interfaz en castellano sin dar ningún error."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2] / "app" / "translations"
        for idioma in i18n.IDIOMAS:
            mo = raiz / idioma / "LC_MESSAGES" / "messages.mo"
            assert mo.exists(), f"falta {mo}; ejecuta pybabel compile -d app/translations"


# ---------------------------------------------------------------------------
# El cambio de idioma
# ---------------------------------------------------------------------------


class TestCambioDeIdioma:
    def test_cambia_y_vuelve_a_la_pagina(self, client, db):
        res = client.post("/idioma", data={"idioma": "ca", "siguiente": "/login"})
        assert res.status_code == 302
        assert res.headers["Location"] == "/login"

    def test_la_pagina_sale_traducida(self, client, db):
        client.post("/idioma", data={"idioma": "gl"})
        html = client.get("/login").data.decode("utf-8")
        assert 'lang="gl"' in html
        assert "As miñas situacións" in html

    def test_funciona_sin_cuenta(self, client, db):
        """Hace falta justamente en la pantalla de acceso, antes de iniciar
        sesión: si solo funcionara con cuenta, no se podría llegar a ella."""
        res = client.post("/idioma", data={"idioma": "eu"})
        assert res.status_code == 302
        assert "Nire egoerak" in client.get("/login").data.decode("utf-8")

    def test_con_cuenta_ademas_se_guarda_en_el_perfil(self, client, db):
        client.post(
            "/auth/register",
            json={
                "correo": "cambio@test.com",
                "contrasena": "ContraSegura1!",
                "nombre": "Docente Cambio",
            },
        )
        client.post("/idioma", data={"idioma": "ca"})
        assert client.get("/me").get_json()["idioma_interfaz"] == "ca"

    def test_un_idioma_inventado_cae_al_castellano(self, client, db):
        client.post("/idioma", data={"idioma": "klingon"})
        assert 'lang="es"' in client.get("/login").data.decode("utf-8")

    @pytest.mark.parametrize(
        "destino", ["https://ejemplo-malicioso.test/", "//ejemplo-malicioso.test/"]
    )
    def test_no_redirige_fuera_de_la_aplicacion(self, client, db, destino):
        """Volver al destino sin comprobarlo convierte esto en una redirección
        abierta: bastaría con enlazarlo desde fuera para llevar al usuario a
        cualquier sitio con la apariencia de venir de aquí."""
        res = client.post("/idioma", data={"idioma": "ca", "siguiente": destino})
        assert res.headers["Location"] == "/"

    def test_un_get_no_cambia_el_idioma(self, client, db):
        """Cambiar una preferencia modifica estado: si fuera un GET, podría
        dispararlo un prefetch del navegador."""
        assert client.get("/idioma").status_code == 405


# ---------------------------------------------------------------------------
# Renderizado
# ---------------------------------------------------------------------------

#: Páginas que se sirven sin sesión. Las privadas redirigen a /login y no
#: llegarían a renderizar su plantilla, que es lo que aquí interesa.
PAGINAS_PUBLICAS = (
    "/",
    "/login",
    "/register",
    "/restablecer-contrasena",
    "/ayuda",
    "/mapa-web",
    "/accesibilidad",
    "/no-existe-esta-ruta",  # la plantilla de 404
)


class TestRenderizado:
    """Que una cadena traducida no rompa la página al pintarse.

    Jinja aplica ``cadena % variables`` al resultado de ``_()`` **siempre**,
    lleve marcadores o no. Un ``%`` suelto en una traducción tiene por tanto
    tres finales posibles, y el peor es el que no avisa:

    ==========================  ==========================================
    ``'... 200% sin pérdida'``   ``'... 200{}in pérdida'`` — sin excepción
    ``'... el 200%.'``           ``ValueError: incomplete format``
    ``'... 50% de los casos'``   ``TypeError: %d format: ...``
    ==========================  ==========================================

    Nada de esto lo detecta ``pybabel compile``: los catálogos figuran
    completos al 100 % y los tests de traducción pasan. El primero en
    enterarse sería el usuario.

    Y no basta con vigilar el castellano: el ``%`` puede estar solo en una
    traducción, así que se recorren las cuatro lenguas.
    """

    @staticmethod
    def _mensajes(app, idioma: str):
        from babel.messages.pofile import read_po

        ruta = Path(app.root_path) / "translations" / idioma / "LC_MESSAGES"
        with (ruta / "messages.po").open(encoding="utf-8") as f:
            return [m for m in read_po(f, locale=idioma) if m.id]

    def test_ningun_porciento_sin_duplicar(self, app):
        """La comprobación principal, porque cubre también el caso mudo.

        Va por delante del resto a propósito: si falla, dice qué idioma y qué
        cadena. Los otros dos tests fallan con «incomplete format», que no
        dice ni una cosa ni la otra.
        """
        sospechosas = [
            f"{idioma}: {m.string}"
            for idioma in i18n.IDIOMAS
            for m in self._mensajes(app, idioma)
            if re.search(r"(?<!%)%(?!%)", m.string or "")
        ]
        assert sospechosas == [], (
            "un % sin duplicar corrompe o rompe el renderizado de esa página; "
            f"escríbelo como %%: {sospechosas}"
        )

    @pytest.mark.parametrize("idioma", sorted(i18n.IDIOMAS))
    def test_ninguna_traduccion_revienta_al_formatear(self, app, idioma):
        """Reproduce literalmente lo que hace Jinja con cada cadena.

        No sustituye al test anterior: el caso mudo pasa por aquí sin
        rechistar. Sirve para que el fallo aparezca en el mismo sitio donde
        lo produciría la aplicación.
        """
        rotas = []
        for m in self._mensajes(app, idioma):
            try:
                str(m.string) % {}
            except (ValueError, TypeError) as e:
                rotas.append(f"{m.string!r}: {type(e).__name__}: {e}")
        assert rotas == [], f"traducciones que rompen el formato en «{idioma}»: {rotas}"

    @pytest.mark.parametrize("idioma", sorted(i18n.IDIOMAS))
    def test_las_paginas_publicas_se_sirven(self, client, db, idioma):
        """Render de verdad, extremo a extremo.

        Un intento anterior de este test recorría las 15 plantillas llamando
        a sus bloques con un contexto vacío. No servía: las plantillas que
        esperan datos fallaban con ``Undefined is not JSON serializable``
        antes de llegar a ninguna cadena traducida, de modo que el test
        medía la falta de contexto y no las traducciones.

        Pasar por el cliente cuesta más, pero da contexto real y comprueba
        de paso que la página sale marcada con el idioma que toca.
        """
        client.set_cookie("idioma", idioma)
        for ruta in PAGINAS_PUBLICAS:
            res = client.get(ruta)
            assert res.status_code in (200, 404), f"{ruta} devolvió {res.status_code}"
            assert f'lang="{idioma}"' in res.data.decode("utf-8"), (
                f"{ruta} no se sirvió en «{idioma}»"
            )


class TestCoberturaDeExtraccion:
    """Que las cadenas del código Python lleguen de verdad a los catálogos.

    Existe por un fallo que no daba ningún síntoma: ``exportacion_service``
    importaba ``lazy_gettext as _l``, y ``_l`` **no está entre las palabras
    clave que busca ``pybabel extract``**. El módulo no se extraía, así que sus
    seis rótulos nunca llegaron a los catálogos: los PDF salían con la cabecera
    en catalán y los títulos de sección en castellano.

    Nada avisaba. Los catálogos figuraban al 100 %, la compilación pasaba y los
    tests de traducción también — porque solo comprobaban cadenas que sí se
    habían extraído. El agujero era justo lo que no estaba ahí.
    """

    def test_los_rotulos_de_exportacion_estan_traducidos(self, app):
        """Comprueba el resultado visible, no la configuración de pybabel.

        Podría comprobarse que el ``.pot`` menciona el módulo, pero eso ata el
        test a la herramienta. Lo que importa es que una docente catalana reciba
        el PDF con los títulos en catalán.
        """
        from app.services.exportacion_service import secciones_para_export

        with app.app_context(), app.test_request_context(
            "/", headers={"Accept-Language": "ca"}
        ):
            etiquetas = dict(secciones_para_export())

        assert etiquetas["objetivos"] == "Objectius didàctics"
        assert etiquetas["evaluacion"] == "Avaluació"

    def test_ningun_modulo_usa_un_alias_que_no_se_extrae(self, app):
        """La causa raíz, cazada antes de que llegue a producir efectos.

        ``pybabel extract`` reconoce ``_``, ``gettext`` y ``ngettext``. Un
        ``lazy_gettext as _l`` —o cualquier otro alias— deja ese módulo fuera
        de los catálogos sin decir nada.
        """
        raiz = Path(app.root_path)
        culpables = []
        for ruta in raiz.rglob("*.py"):
            texto = ruta.read_text(encoding="utf-8")
            for linea in texto.splitlines():
                if "gettext as" in linea and not re.search(
                    r"gettext as (_|gettext|ngettext)\b", linea
                ):
                    culpables.append(f"{ruta.relative_to(raiz)}: {linea.strip()}")
        assert culpables == [], (
            "pybabel extract no reconoce estos alias, así que esos módulos no "
            f"llegan a los catálogos: {culpables}"
        )


class TestDestinoAlCambiarIdioma:
    """Cambiar de idioma debe dejarte donde estabas.

    No lo hacía: la comprobación de seguridad exigía que el destino empezara
    por ``/``, y el respaldo era ``request.referrer``, que es una URL
    **absoluta**. Nunca pasaba el filtro y siempre se caía al ``/``. El fallo
    estaba escondido dentro de una guarda correcta contra redirección abierta,
    que es de las peores formas de esconder uno.
    """

    def test_vuelve_a_la_pagina_de_origen(self, client, db):
        res = client.post(
            "/idioma", data={"idioma": "ca", "siguiente": "/situaciones/54"}
        )
        assert res.headers["Location"] == "/situaciones/54"

    def test_conserva_la_cadena_de_consulta(self, client, db):
        """Los filtros de un listado viven ahí; perderlos al cambiar de idioma
        obliga a volver a aplicarlos."""
        res = client.post(
            "/idioma",
            data={"idioma": "gl", "siguiente": "/situaciones?estado=borrador"},
        )
        assert res.headers["Location"] == "/situaciones?estado=borrador"

    def test_sin_campo_usa_la_ruta_del_referer(self, client, db):
        """El respaldo para quien no tenga JavaScript o pierda el campo.

        Se toma la **ruta** del Referer, no el Referer entero: es lo que
        arregla el fallo sin reabrir la redirección.
        """
        res = client.post(
            "/idioma",
            data={"idioma": "eu"},
            headers={"Referer": "http://localhost/perfil"},
        )
        assert res.headers["Location"] == "/perfil"

    @pytest.mark.parametrize(
        "destino",
        [
            "https://ejemplo-malicioso.test/",
            "//ejemplo-malicioso.test/",
            "http://localhost/otra",  # absoluta, aunque sea del mismo host
        ],
    )
    def test_sigue_sin_redirigir_fuera(self, client, db, destino):
        """La guarda contra redirección abierta no se ha aflojado al
        arreglar lo anterior, que es el riesgo de tocar este código."""
        res = client.post("/idioma", data={"idioma": "ca", "siguiente": destino})
        assert res.headers["Location"] == "/"

    def test_un_referer_ajeno_solo_aporta_su_ruta(self, client, db):
        """Se aplica sobre nuestro dominio, así que es inofensivo: como mucho
        lleva a una ruta nuestra que probablemente no exista."""
        res = client.post(
            "/idioma",
            data={"idioma": "ca"},
            headers={"Referer": "https://malicioso.test/robar"},
        )
        assert res.headers["Location"] == "/robar"

    def test_la_pagina_incluye_el_campo_con_la_ruta_actual(self, client, db):
        """Sin el campo, todo depende del Referer, que hay configuraciones de
        privacidad que eliminan."""
        html = client.get("/ayuda").data.decode("utf-8")
        assert 'name="siguiente"' in html
        assert 'value="/ayuda"' in html


class TestCableadoDeRutas:
    """Que cada ruta apunte a la vista que dice, y no a otra función.

    Existe por un fallo de una tontería con consecuencias grandes: al extraer
    un ayudante de ``cambiar_idioma`` lo coloqué **entre el decorador
    ``@bp.post("/idioma")`` y la vista**, así que el decorador registró el
    ayudante. Flask no se queja —cualquier función vale como vista— y la
    aplicación arranca perfectamente; el error solo aparece cuando alguien usa
    la ruta, y sale como un 500 genérico.

    Este test vive en el fichero de i18n porque fue ahí donde ocurrió, pero
    comprueba toda la aplicación.
    """

    def test_ninguna_ruta_apunta_a_un_ayudante_privado(self, app):
        """Una función con guion bajo delante no está pensada para ser vista.

        Se comprueba sobre ``url_map``, que es la verdad de lo que Flask ha
        registrado, y no leyendo el código: así también caza un
        ``add_url_rule`` escrito a mano.

        Quedan fuera dos cosas. Los manejadores de error, que se llaman
        ``_handle`` por convención y no son rutas. Y las rutas bajo
        ``/_test/``, que ``conftest`` registra a propósito para probar
        ``role_required`` y que solo existen en la aplicación de pruebas: su
        guion bajo es deliberado, precisamente para que no se confundan con
        rutas de la aplicación.

        La exclusión se hace por **prefijo de ruta** y no por nombre de
        función. Excluir cualquier ``_algo`` desactivaría el test entero, que
        es justo lo que comprueba.
        """
        culpables = [
            f"{regla.rule} -> {regla.endpoint}"
            for regla in app.url_map.iter_rules()
            if regla.endpoint.rsplit(".", 1)[-1].startswith("_")
            and not regla.rule.startswith("/_test/")
        ]
        assert culpables == [], (
            "estas rutas apuntan a una función privada, seguramente por haber "
            f"insertado algo entre el decorador y la vista: {culpables}"
        )

    def test_la_ruta_de_idioma_apunta_a_donde_debe(self, app):
        """El caso concreto, por si el criterio general se relaja algún día."""
        endpoints = {
            regla.rule: regla.endpoint
            for regla in app.url_map.iter_rules()
        }
        assert endpoints["/idioma"] == "pages.cambiar_idioma"
