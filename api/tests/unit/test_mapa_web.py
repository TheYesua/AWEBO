"""El mapa web nombra todas las páginas, y ninguna se queda fuera en silencio.

POR QUÉ IMPORTA MÁS DE LO QUE PARECE
-------------------------------------
Un mapa web incompleto es **peor que no tenerlo**: es lo que usa quien navega
con lector de pantalla para saber qué hay, y una ausencia no se distingue de
«esa función no existe». El que había listaba 10 páginas de las 15 que sirve la
aplicación.

Y no se puede arreglar una vez: se arregla y vuelve a quedarse corto en cuanto
alguien añade una página, porque nada le obliga a mirar aquí. De eso va este
fichero.

LA CLASIFICACIÓN, QUE ES LO QUE HACE EL TRABAJO
------------------------------------------------
No basta con «todas las rutas tienen que estar enlazadas»: sería falso. Tres de
las que faltaban —`/baja`, `/correo-de-respaldo` y `/reclamacion`— son
pantallas de aterrizaje de un enlace enviado por correo y **esperan un token en
la dirección**. Enlazarlas a secas prometería una navegación que no existe:
quien pulsara vería un error.

Así que cada página cae en uno de tres cubos, y **el test exige que caiga en
alguno**. Añadir una ruta nueva sin clasificarla pone esto en rojo, que es la
única forma de que la decisión se tome.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MAPA = Path(__file__).resolve().parents[2] / "app" / "templates" / "mapa_web.html"

#: Se llega a ellas navegando, así que el mapa las lleva como enlace.
NAVEGABLES = {
    "/",
    "/login",
    "/register",
    "/restablecer-contrasena",
    "/situaciones",
    "/situaciones/nueva",
    "/perfil",
    "/ayuda",
    "/accesibilidad",
    "/mapa-web",
}

#: Aterrizajes de un enlace de correo. El mapa las **nombra** pero no las
#: enlaza: sin el token de la dirección no hacen nada, y un enlace que lleva a
#: un error es peor que una frase que explica dónde aparece la pantalla.
POR_CORREO = {
    "/baja",
    "/correo-de-respaldo",
    "/reclamacion",
}

#: Fuera del mapa, cada una con su motivo escrito. La lista es corta a
#: propósito: cuanto más fácil sea meter algo aquí, menos sirve el test.
EXCLUIDAS = {
    # No es una dirección: lleva un identificador. Se menciona en prosa, en el
    # apartado del listado, porque el mapa debe decir que existe.
    "/situaciones/<int:id_situacion>": "ruta dinámica, no hay una URL que enlazar",
    # Solo la ve quien tiene el rol. Se menciona en prosa por lo mismo.
    "/admin/": "restringida por rol",
}


def _rutas_de_pagina(app) -> set[str]:
    """Las rutas GET que devuelven HTML.

    Se leen del `url_map` de la aplicación y no de una lista escrita aquí: una
    lista a mano tendría el mismo problema que el mapa web, y entonces el test
    comprobaría que dos copias mías coinciden entre sí.
    """
    rutas = set()
    for regla in app.url_map.iter_rules():
        if "GET" not in (regla.methods or set()):
            continue
        # Se selecciona por BLUEPRINT y no por prefijo de la ruta. La primera
        # versión descartaba lo que empezara por `/api/`, y se colaron `/me`,
        # `/me/correo-de-respaldo` y `/me/ia/catalogo`: devuelven JSON y no
        # empiezan por ahí. Un prefijo describe la forma de la URL; el
        # blueprint describe para qué es.
        raiz = (regla.endpoint or "").split(".")[0]
        if raiz not in ("pages", "admin"):
            continue
        # Dentro de `admin` conviven el panel y su API.
        if regla.rule.startswith("/admin/api/"):
            continue
        rutas.add(regla.rule)
    return rutas


def _enlaces_del_mapa() -> set[str]:
    return set(re.findall(r'<a href="([^"]+)"', MAPA.read_text(encoding="utf-8")))


class TestLaClasificacionEstaCompleta:
    def test_ninguna_pagina_se_queda_sin_clasificar(self, app):
        """El test que de verdad protege: una ruta nueva **obliga** a decidir
        si va en el mapa, si es un aterrizaje de correo o si se excluye."""
        clasificadas = NAVEGABLES | POR_CORREO | set(EXCLUIDAS)
        sin_clasificar = sorted(_rutas_de_pagina(app) - clasificadas)

        assert not sin_clasificar, (
            f"{sin_clasificar} no está en ninguno de los tres cubos de "
            "test_mapa_web.py. Decide si va enlazada en el mapa, si es una "
            "pantalla a la que se llega por correo, o si se excluye con su "
            "motivo."
        )

    def test_no_se_clasifica_nada_que_no_exista(self, app):
        """El otro lado. Sin esto, las listas de arriba envejecerían llenas de
        rutas borradas y el test seguiría en verde."""
        reales = _rutas_de_pagina(app)
        inventadas = sorted((NAVEGABLES | POR_CORREO | set(EXCLUIDAS)) - reales)

        assert not inventadas, f"{inventadas} ya no existen en la aplicación"


class TestLoQueElMapaEnlaza:
    @pytest.mark.parametrize("ruta", sorted(NAVEGABLES))
    def test_cada_pagina_navegable_esta_enlazada(self, ruta):
        assert ruta in _enlaces_del_mapa(), f"el mapa web no enlaza {ruta}"

    @pytest.mark.parametrize("ruta", sorted(POR_CORREO))
    def test_las_de_correo_no_se_enlazan(self, ruta):
        """Enlazarlas prometería una navegación que no existe: sin el token de
        la dirección, la pantalla no hace nada."""
        assert ruta not in _enlaces_del_mapa(), (
            f"{ruta} es un aterrizaje de correo y no debería ir como enlace"
        )

    def test_pero_si_se_nombran(self):
        """Que no se enlacen no significa que puedan faltar: un mapa web sirve
        para saber **qué hay**, y quien llega buscando «cómo me doy de baja»
        merece una respuesta."""
        texto = MAPA.read_text(encoding="utf-8")

        assert "baja de la cuenta" in texto
        assert "correo de respaldo" in texto
        assert "Recuperar una cuenta" in texto

    def test_el_panel_de_administracion_se_menciona(self):
        assert "/admin" in MAPA.read_text(encoding="utf-8")

    def test_no_enlaza_nada_que_no_sea_una_pagina(self, app):
        """Un enlace roto en el mapa web es especialmente malo: la página
        existe para orientar."""
        rutas = _rutas_de_pagina(app)
        rotos = sorted(e for e in _enlaces_del_mapa() if e not in rutas)

        assert not rotos, f"el mapa web enlaza rutas que no existen: {rotos}"
