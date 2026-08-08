"""Internacionalización de la interfaz.

Traduce lo que la aplicación dice **de su propia cosecha**: menús, botones,
mensajes de error, etiquetas de formulario. **No** traduce el contenido
curricular, que es texto legal anclado a un decreto oficial y se muestra en la
lengua en que ese decreto lo publica. Ver la decisión en el DIARIO.

Resolución del idioma, en este orden:

1. La preferencia guardada en el perfil del usuario, si está autenticado.
2. La cookie ``idioma``, que es lo que permite a alguien sin cuenta cambiar de
   idioma en la pantalla de acceso.
3. La cabecera ``Accept-Language`` del navegador.
4. Castellano.

Por qué el perfil y no solo una cookie, al contrario que el tema: el idioma es
propiedad de la **persona**, no del dispositivo. Nadie lee en catalán en el
portátil y en castellano en el móvil. El tema sí cambia entre dispositivos —de
ahí que aquel viva en una cookie y este en la base de datos.

Como el tema, se resuelve **en el servidor**: Jinja recibe el idioma ya
decidido y la página llega traducida de una vez, sin un salto de idioma al
cargar.
"""
from __future__ import annotations

from flask import Flask, request
from flask_babel import Babel, get_locale
from flask_login import current_user


#: Idiomas ofrecidos, cada uno escrito en su propia lengua. Es la convención
#: en un selector de idioma: quien busca «Català» no lo reconocería bajo la
#: etiqueta «Catalán».
IDIOMAS: dict[str, str] = {
    "es": "Español",
    "ca": "Català",
    "gl": "Galego",
    "eu": "Euskara",
}

IDIOMA_POR_DEFECTO = "es"

COOKIE_IDIOMA = "idioma"

#: Un año: la preferencia de idioma no caduca en ningún sentido útil.
MAX_AGE_COOKIE = 60 * 60 * 24 * 365

babel = Babel()


def _de_perfil() -> str | None:
    """Idioma guardado en el perfil, si hay sesión y está fijado."""
    try:
        if not current_user.is_authenticated:
            return None
    except Exception:  # noqa: BLE001 — fuera de contexto de petición
        return None
    valor = getattr(current_user, "idioma_interfaz", None)
    return valor if valor in IDIOMAS else None


def _de_cookie() -> str | None:
    valor = (request.cookies.get(COOKIE_IDIOMA) or "").strip().lower()
    return valor if valor in IDIOMAS else None


def _del_navegador() -> str | None:
    """Mejor coincidencia entre lo que pide el navegador y lo que se ofrece."""
    return request.accept_languages.best_match(list(IDIOMAS))


def resolver_idioma() -> str:
    """Devuelve el código de idioma a usar en esta petición."""
    if not request:
        return IDIOMA_POR_DEFECTO
    return (
        _de_perfil()
        or _de_cookie()
        or _del_navegador()
        or IDIOMA_POR_DEFECTO
    )


def idioma_actual() -> str:
    """Idioma resuelto para esta petición.

    Delega en Flask-Babel y no cachea nada por su cuenta.

    Sobre dónde se cachea, que costó dos intentos aclarar: Flask-Babel guarda
    el idioma en ``g._flask_babel.babel_locale``. Es decir, **en el contexto
    de aplicación**, porque ahí es donde vive ``flask.g``; no en el de
    petición, como sugiere el nombre. Un intento anterior de esta función
    cacheaba en ``flask.g`` directamente, se corrigió delegando en
    Flask-Babel «que ya cachea en el contexto de petición», y esa segunda
    versión seguía rota por el mismo motivo: Flask-Babel usa el mismo ``g``.

    En producción da igual, porque cada petición empuja su propio contexto de
    aplicación. Solo se nota donde algo mantiene uno abierto y sirve varias
    peticiones dentro —la suite de tests, una tarea Celery, un comando de
    CLI—: allí el primer idioma resuelto se queda fijo para todo lo demás.
    """
    return str(get_locale() or IDIOMA_POR_DEFECTO)


def init_app(app: Flask) -> None:
    """Configura Babel y expone el idioma a las plantillas."""
    app.config.setdefault("BABEL_DEFAULT_LOCALE", IDIOMA_POR_DEFECTO)
    app.config.setdefault("BABEL_TRANSLATION_DIRECTORIES", "translations")

    babel.init_app(app, locale_selector=resolver_idioma)

    @app.context_processor
    def _inyectar_idioma() -> dict:
        return {
            "idioma": idioma_actual(),
            "idiomas_disponibles": IDIOMAS,
        }
