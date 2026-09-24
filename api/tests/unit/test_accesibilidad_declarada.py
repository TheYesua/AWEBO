"""La declaración de accesibilidad no promete lo que la aplicación no hace.

POR QUÉ ESTE FICHERO (24/09/2026)
---------------------------------
`accesibilidad.html` hacía trece afirmaciones y **seis no se sostenían**. No es
una página cualquiera: es la que se compromete a algo frente a quien la lee, y
la única cuyo destinatario es justamente alguien que puede no poder usar el
resto de la aplicación.

Lo que decía y lo que había:

* «<kbd>Esc</kbd> para cerrar diálogos». **No hay ni un diálogo.** Y el motivo
  está escrito en `admin/panel.html`: se descartó el modal porque «necesita
  atrapar el foco, devolverlo al cerrar y gestionar Escape; son piezas que este
  proyecto no tiene». La página prometía la tecla que se decidió no hacer.
* «Información que no se transmite solo mediante color». Es exactamente la
  regla que axe rompió doce veces el 23/09, con el enlace del pie.
* «Lectura en voz alta… No requiere conexión ni servicio externo». Cierto solo
  del proveedor `local`. Hay tres, el de por defecto no genera nada y `openai`
  manda el texto fuera.
* «conforme a las WCAG 2.1 nivel AA», sin decir qué se había verificado.
* «Limitaciones conocidas» **sin una sola limitación**.
* «puedes comunicarla en la sección de Ayuda», donde no hay ninguna vía de
  contacto: en toda la aplicación no existe un solo `mailto:` ni un formulario.

LO QUE SE PUEDE COMPROBAR AQUÍ Y LO QUE NO
-------------------------------------------
Un test no puede leer una frase y decir si es verdad. Lo que sí puede es atar
las afirmaciones **cuya contraparte está en el código**: si la página nombra una
tecla para cerrar diálogos, que haya diálogos; si promete un canal de contacto,
que exista. Eso cubre cuatro de las seis.

Las otras dos —la conformidad WCAG y el apartado de limitaciones— no son
mecánicas. Para la segunda al menos se exige que **haya** limitaciones, porque
el fallo concreto fue un apartado vacío.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_APP = Path(__file__).resolve().parents[2] / "app"
PAGINA = _APP / "templates" / "accesibilidad.html"
PLANTILLAS = _APP / "templates"


def _texto() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _sin_comentarios() -> str:
    """El HTML sin los comentarios de Jinja.

    Hace falta porque los comentarios de esta página **citan las frases que se
    corrigieron**, para dejar constancia de qué decía antes. Sin quitarlos, cada
    test de abajo encontraría la frase prohibida en el comentario que explica
    por qué está prohibida, y el arreglo consistiría en borrar la explicación.

    Ya pasó el 20/09 con un test de CSS: se puso rojo por el comentario que
    describía el fallo que ese mismo test vigilaba.
    """
    return re.sub(r"\{#.*?#\}", "", _texto(), flags=re.S)


def test_la_pagina_existe_y_se_lee():
    """Regla 15: si la ruta cambia, todo lo de abajo pasaría en verde sobre una
    cadena vacía."""
    assert PAGINA.is_file(), PAGINA
    assert len(_sin_comentarios()) > 1000


class TestNoPrometeLoQueNoHay:
    def test_no_nombra_una_tecla_para_cerrar_dialogos_si_no_hay_dialogos(self):
        """La afirmación y su contraparte, cruzadas.

        Si algún día se añade un modal accesible, este test deja de exigir nada
        y la página puede volver a mencionar Escape. Mientras no lo haya, no.
        """
        hay_dialogos = any(
            re.search(r"<dialog|role=[\"']dialog[\"']|aria-modal", p.read_text(encoding="utf-8"))
            for p in PLANTILLAS.rglob("*.html")
        )
        if hay_dialogos:
            pytest.skip("ya hay diálogos: la página puede mencionar Escape")

        texto = _sin_comentarios()
        assert "cerrar diálogos" not in texto, (
            "la página dice que Esc cierra diálogos y no hay ninguno en la "
            "aplicación. Se descartaron a propósito: ver admin/panel.html."
        )

    def test_el_canal_para_avisar_existe(self):
        """El fallo peor de los seis.

        La página remitía a `/ayuda` «para comunicarlo», y en toda la
        aplicación no hay un `mailto:` ni un formulario de contacto. En una
        declaración de accesibilidad el canal no es un adorno: es lo que la
        convierte en un compromiso.

        Se acepta un `mailto:` **o** un enlace externo de avisos. Lo que no se
        acepta es remitir a una página interna que no tiene ninguno de los dos.
        """
        texto = _sin_comentarios()

        tiene_correo = "mailto:" in texto
        tiene_externo = bool(re.search(r'href="https?://[^"]+', texto))
        assert tiene_correo or tiene_externo, (
            "la página no ofrece ninguna vía para avisar de una barrera. Un "
            "`mailto:` del proyecto, o un enlace a los avisos del repositorio."
        )

        # Y que no vuelva a mandar a Ayuda, que sigue sin tener canal.
        ayuda = (PLANTILLAS / "ayuda.html").read_text(encoding="utf-8")
        if "mailto:" not in ayuda:
            assert "de <a href=\"/ayuda\">Ayuda</a>" not in texto, (
                "vuelve a remitir a /ayuda, que no tiene vía de contacto"
            )

    def test_no_describe_la_voz_como_si_hubiera_un_solo_proveedor(self):
        """«No requiere conexión ni servicio externo» era cierto de uno de los
        tres proveedores, y el de por defecto no es ese."""
        from app.voz import factoria

        proveedores = set(getattr(factoria, "_PROVEEDORES", {}))
        if len(proveedores) <= 1:
            pytest.skip("solo hay un proveedor de voz: la frase absoluta valdría")

        texto = _sin_comentarios()
        assert "No requiere conexión ni servicio externo" not in texto, (
            f"la página afirma en absoluto que la voz no sale de la máquina, y "
            f"hay {len(proveedores)} proveedores ({sorted(proveedores)}): "
            f"'openai' manda el texto fuera y el de por defecto no genera nada."
        )


class TestDiceLoQueNoSabe:
    def test_hay_limitaciones_listadas(self):
        """Un apartado de «limitaciones conocidas» vacío es la parte menos
        creíble de una declaración, porque el lector sabe que existen. El que
        había no listaba ninguna: decía que la aplicación era un TFG.

        Se cuentan elementos de lista después del encabezado, que es lo único
        mecánico aquí. Que digan algo cierto hay que leerlo.
        """
        texto = _sin_comentarios()
        i = texto.find("Limitaciones conocidas")
        assert i != -1, "ya no hay apartado de limitaciones conocidas"

        resto = texto[i:]
        fin = resto.find("</article>")
        assert fin != -1, "el apartado de limitaciones no cierra"

        assert resto[:fin].count("<li>") >= 3, (
            "el apartado de limitaciones conocidas lista menos de tres. Las hay "
            "más: las páginas con sesión no se auditan, ninguna herramienta "
            "automática ve el orden de tabulación, y nadie ha probado esto con "
            "un lector de pantalla."
        )

    def test_no_declara_conformidad_sin_haberla_verificado(self):
        """La página decía «se ha diseñado conforme a las WCAG 2.1 nivel AA»
        mientras acumulaba doce incumplimientos «serious» de la 1.4.1 sin
        detectar, porque el trabajo de la CI que los habría visto llevaba
        cinco semanas en rojo por otra causa.

        «Apuntar a» un nivel y «ser conforme» a él son cosas distintas, y en una
        declaración de accesibilidad la diferencia es el compromiso.
        """
        texto = _sin_comentarios()
        for frase in ("se ha diseñado conforme a", "cumple las WCAG",
                      "es conforme a las WCAG", "conformidad WCAG 2.1 nivel AA"):
            assert frase not in texto, (
                f"la página declara conformidad («{frase}») y no está "
                f"verificada: la auditoría automática cubre seis páginas "
                f"públicas y nadie la ha probado con un lector de pantalla."
            )
