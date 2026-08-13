"""Páginas HTML mínimas para probar el sistema desde el navegador.

Estas vistas devuelven HTML renderizado con Jinja. Las acciones (registro,
login, edición de perfil) se realizan vía ``fetch`` desde JavaScript contra
los endpoints JSON ya existentes (``/auth/...``, ``/me``).
"""
from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user

from ..extensions import db


bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/login")
def login_page():
    return render_template("login.html")


@bp.get("/register")
def register_page():
    """El catálogo de provincias va incrustado, no por fetch.

    `/api/curriculo/provincias` exige sesión —para no servir de fuente de
    scraping anónimo— y aquí, por definición, todavía no la hay. Como son 52
    entradas fijas, se pasan a la plantilla y se acabó.
    """
    from ..curriculo import provincias

    return render_template("register.html", grupos_provincias=provincias.agrupadas())


@bp.get("/perfil")
def perfil_page():
    return render_template("perfil.html")


@bp.get("/restablecer-contrasena")
def restablecer_contrasena_page():
    return render_template("restablecer_contrasena.html")


@bp.get("/baja")
def baja_page():
    """Pantalla que abre el enlace de confirmación de baja.

    Sin `login_required`: el enlace llega al correo y se abre donde esté el
    buzón, que a menudo es otro navegador. Exigir sesión aquí obligaría a
    iniciarla justo para darse de baja.
    """
    return render_template("baja.html")


@bp.get("/correo-de-respaldo")
def correo_de_respaldo_page():
    """Pantalla que abre el enlace de confirmación del correo de respaldo.

    Sin `login_required`: cuando es un cambio, el enlace llega al respaldo
    *anterior*, que no tiene por qué estar abierto en el mismo navegador donde
    se pidió el cambio.
    """
    return render_template("correo_de_respaldo.html")


@bp.get("/reclamacion")
def reclamacion_page():
    """Pantalla que abre el enlace enviado al correo de respaldo.

    Sin `login_required` y con más motivo que `/baja`: quien la abre se dio de
    baja, así que no tiene ninguna sesión que iniciar.
    """
    return render_template("reclamacion.html")


@bp.get("/situaciones")
def situaciones_listar_page():
    return render_template("situaciones/listar.html")


@bp.get("/situaciones/nueva")
def situaciones_nueva_page():
    return render_template("situaciones/nueva.html")


@bp.get("/situaciones/<int:id_situacion>")
def situaciones_detalle_page(id_situacion: int):
    # Qué operaciones admite cada sección se decide en el servidor
    # (``prompt_operaciones.SECCIONES_APLICABLES``) y se inyecta en la
    # plantilla, en lugar de repetir la regla en JavaScript. Duplicarla
    # llevaría antes o después a ofrecer un botón que el servidor rechaza.
    from ..prompts import operaciones as ops

    por_seccion: dict[str, list[str]] = {}
    for operacion, secciones in ops.SECCIONES_APLICABLES.items():
        for seccion in secciones:
            por_seccion.setdefault(seccion, []).append(operacion)
    # Orden estable, el de OPERACIONES, para que los botones no bailen.
    for seccion in por_seccion:
        por_seccion[seccion].sort(key=ops.OPERACIONES.index)

    return render_template(
        "situaciones/detalle.html",
        id_situacion=id_situacion,
        operaciones_por_seccion=por_seccion,
    )


def _destino_seguro(siguiente: str | None, referrer: str | None) -> str:
    """Ruta a la que volver tras cambiar el idioma.

    Solo se aceptan rutas de esta misma aplicación. Volver al ``Referer`` sin
    comprobarlo convierte el endpoint en una redirección abierta: bastaría con
    enlazarlo desde fuera para llevar al usuario a cualquier sitio con la
    apariencia de venir de aquí.

    El ``Referer`` se usa **por su ruta**, no tal cual. Es el fallo que hacía
    que cambiar de idioma llevara siempre a Inicio: la comprobación exigía que
    el destino empezara por ``/``, y un ``Referer`` es una URL absoluta
    (``http://host/situaciones/54``), así que nunca pasaba y se caía al ``/``
    del respaldo. Quedarse con la ruta arregla el caso legítimo sin abrir la
    redirección: si el ``Referer`` viene de otro dominio, su ruta se aplica
    sobre el nuestro, que es inofensivo.
    """
    from urllib.parse import urlsplit

    candidato = siguiente or ""
    if not candidato and referrer:
        partes = urlsplit(referrer)
        candidato = partes.path + (f"?{partes.query}" if partes.query else "")

    # Una ruta que empieza por «//» la interpreta el navegador como
    # «//host/ruta», es decir, otro dominio. Se descarta.
    if not candidato.startswith("/") or candidato.startswith("//"):
        return "/"
    return candidato


@bp.post("/idioma")
def cambiar_idioma():
    """Cambia el idioma de la interfaz y vuelve a la página de origen.

    Guarda siempre una cookie —así funciona también sin cuenta, que es
    justamente lo que hace falta en la pantalla de acceso— y además lo escribe
    en el perfil si hay sesión, porque el idioma acompaña a la persona entre
    dispositivos.

    Es un ``POST`` con formulario y no un enlace: cambiar una preferencia
    modifica estado del servidor, y un ``GET`` que lo hiciera podría dispararse
    por un prefetch del navegador.
    """
    from flask import current_app, make_response, redirect, request

    from .. import i18n

    idioma = (request.form.get("idioma") or "").strip().lower()
    if idioma not in i18n.IDIOMAS:
        idioma = i18n.IDIOMA_POR_DEFECTO

    destino = _destino_seguro(
        request.form.get("siguiente"), request.referrer
    )

    respuesta = make_response(redirect(destino))
    respuesta.set_cookie(
        i18n.COOKIE_IDIOMA,
        idioma,
        max_age=i18n.MAX_AGE_COOKIE,
        samesite="Lax",
        httponly=False,  # el frontend no lo necesita, pero tampoco es un secreto
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
    )

    if current_user.is_authenticated:
        current_user.idioma_interfaz = idioma
        db.session.commit()

    return respuesta


@bp.get("/ayuda")
def ayuda_page():
    return render_template("ayuda.html")


@bp.get("/mapa-web")
def mapa_web_page():
    return render_template("mapa_web.html")


@bp.get("/accesibilidad")
def accesibilidad_page():
    return render_template("accesibilidad.html")
