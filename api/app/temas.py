"""Resolución del tema visual (claro / oscuro / automático).

El tema se resuelve **en el servidor** y Jinja lo escribe en
``<html data-tema="…">``. Es la parte que hace que la funcionalidad valga
para algo: si el tema se aplicara desde JavaScript al cargar, cada
navegación pintaría un fotograma en blanco antes de oscurecerse — justo el
destello que esta pantalla existe para evitar, y en el peor momento posible.

Como la aplicación no es una SPA y renderiza HTML en servidor, el atributo
puede venir ya puesto en la respuesta. Cero parpadeo, sin scripts bloqueantes
en el ``<head>``.

Dos cookies, con papeles distintos:

``tema``
    Lo que el usuario ha **elegido**: ``claro``, ``oscuro`` o ``auto``.

``tema_sistema``
    Lo que el navegador **informa** que prefiere el sistema operativo
    (``claro`` u ``oscuro``). La escribe el JavaScript del cliente, porque
    ``prefers-color-scheme`` no viaja en ninguna cabecera fiable.

Con ambas, el servidor emite siempre un valor concreto: ``auto`` nunca llega
al HTML. Eso permite que el CSS defina el tema oscuro **una sola vez**, sin
duplicar la paleta dentro de una media query.

Por qué cookie y no columna en ``Usuario``: el tema es una preferencia **de
dispositivo**, no de cuenta. El mismo docente quiere la interfaz oscura en su
portátil por la noche y clara al proyectarla en el aula por la mañana.
Guardarla en el perfil sincronizaría precisamente lo que no debe
sincronizarse — y de paso evita una migración.
"""
from __future__ import annotations

from flask import Flask, request


#: Lo que el usuario puede elegir.
TEMAS_ELEGIBLES = ("claro", "oscuro", "auto")

#: Lo que puede acabar en el HTML. ``auto`` no está: ya viene resuelto.
TEMAS_RESUELTOS = ("claro", "oscuro")

COOKIE_TEMA = "tema"
COOKIE_TEMA_SISTEMA = "tema_sistema"

#: Un año. La preferencia de tema no caduca en ningún sentido útil.
MAX_AGE_COOKIE = 60 * 60 * 24 * 365

TEMA_POR_DEFECTO = "auto"


def tema_elegido() -> str:
    """Devuelve la elección del usuario, saneada."""
    valor = (request.cookies.get(COOKIE_TEMA) or "").strip().lower()
    return valor if valor in TEMAS_ELEGIBLES else TEMA_POR_DEFECTO


def tema_sistema() -> str:
    """Devuelve la preferencia del sistema según la informó el navegador.

    Si no hay cookie —primera visita, o JavaScript deshabilitado— se asume
    ``claro``, que es el comportamiento histórico de la aplicación.
    """
    valor = (request.cookies.get(COOKIE_TEMA_SISTEMA) or "").strip().lower()
    return valor if valor in TEMAS_RESUELTOS else "claro"


def resolver_tema() -> str:
    """Traduce la elección a un tema concreto para el atributo ``data-tema``."""
    elegido = tema_elegido()
    return tema_sistema() if elegido == "auto" else elegido


def init_app(app: Flask) -> None:
    """Expone ``tema`` y ``tema_elegido`` a todas las plantillas Jinja."""

    @app.context_processor
    def _inyectar_tema() -> dict[str, str]:
        # ``tema``: valor concreto para data-tema (nunca "auto").
        # ``tema_elegido``: para marcar la opción activa en el selector, que
        # sí debe distinguir "automático" de "claro".
        return {"tema": resolver_tema(), "tema_elegido": tema_elegido()}
