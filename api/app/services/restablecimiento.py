"""Restablecimiento de contraseña por correo.

Sustituye al camino anterior, en el que ``POST /auth/reset-password`` cambiaba
la contraseña de cualquier cuenta **sabiendo solo su correo**: sin sesión, sin
token y sin confirmar nada. En desarrollo era una comodidad deliberada; en
cuanto hay una cuenta que no es la propia, es un secuestro en dos clics.

EL PRINCIPIO QUE ORDENA TODO ESTE MÓDULO
-----------------------------------------
Pedir un restablecimiento **no debe revelar si una dirección está registrada**.
Si la respuesta cambiara —un 404 aquí, un mensaje distinto allá—, el formulario
se convierte en una herramienta para averiguar qué docentes tienen cuenta, que
es justo lo que un atacante quiere antes de probar contraseñas.

Por eso ``solicitar`` no devuelve nada y nunca lanza excepción: haga lo que
haga por dentro, desde fuera es siempre la misma respuesta. El envío va por
Celery para que tampoco el *tiempo* de respuesta cambie según haya o no correo
que mandar.

TAMBIÉN VALE EL CORREO DE RESPALDO (tarea 13)
----------------------------------------------
Quien cambia de centro pierde su dirección institucional con la cuenta todavía
activa. Sin el respaldo se quedaría fuera para siempre, porque la única vía de
recuperación pasaba por un buzón que ya no lee nadie —o que lee otra persona—.

Eso obliga a buscar por dos columnas sin romper la indistinguibilidad: la
respuesta sigue siendo la misma exista o no una cuenta con esa dirección, y da
igual por cuál de las dos vías coincida.
"""
from __future__ import annotations

import structlog
from flask import current_app
from flask_babel import gettext as _
from sqlalchemy import select

from ..extensions import db
from ..models import Usuario
from .auth_service import AuthError, validar_contrasena
from .tokens import CADUCIDAD_RESTABLECER, TokenInvalido, generar_restablecimiento, leer_restablecimiento


log = structlog.get_logger(__name__)


def _texto_del_correo(enlace: str, horas: int) -> tuple[str, str]:
    """Cuerpo del mensaje, en texto plano y en HTML, **en el idioma de quien lo pide**.

    AQUÍ HUBO UN RAZONAMIENTO EQUIVOCADO, Y CONVIENE QUE CONSTE
    -----------------------------------------------------------
    Esta función decía: «no se traduce con ``_()``; el correo se envía desde
    una tarea de Celery, fuera de una petición, así que ahí no hay idioma de
    interfaz que consultar». La conclusión era falsa porque la premisa mezclaba
    dos momentos distintos:

    * el texto se **compone aquí**, dentro de la petición, donde el idioma sí
      se conoce;
    * lo único que ocurre en el worker es la **entrega** de unas cadenas que ya
      vienen hechas.

    Así que basta con marcar las cadenas. No hace falta guardar el idioma en el
    usuario ni activarlo en la tarea, que era el trabajo que se creía pendiente.

    Los marcadores van con ``{llaves}`` y no con ``%s``: ``pybabel`` extrae las
    dos formas, pero un ``%`` suelto en una traducción rompe el renderizado en
    Jinja, y el proyecto lo prohíbe en todo el catálogo.
    """
    texto = "\n\n".join([
        _("Has pedido restablecer tu contraseña en AWEBO."),
        _("Abre este enlace para elegir una nueva:") + f"\n{enlace}",
        _("El enlace caduca en {horas} hora(s) y solo se puede usar una vez.").format(horas=horas),
        _("Si no has sido tú, no hace falta que hagas nada: mientras no se abra el enlace, tu contraseña sigue siendo la de siempre."),
    ])
    html = (
        f"<p>{_('Has pedido restablecer tu contraseña en AWEBO.')}</p>"
        f'<p><a href="{enlace}">{_("Elegir una contraseña nueva")}</a></p>'
        f"<p>{_('El enlace caduca en {horas} hora(s) y solo se puede usar una vez.').format(horas=horas)}</p>"
        f"<p>{_('Si no has sido tú, no hace falta que hagas nada: mientras no se abra el enlace, tu contraseña sigue siendo la de siempre.')}</p>"
        f"<p style='color:#666;font-size:12px'>"
        f"{_('Si el enlace no funciona, copia esta dirección en el navegador:')}<br>{enlace}</p>"
    )
    return texto, html


def solicitar(correo: str) -> None:
    """Manda un enlace de restablecimiento **si** la dirección existe.

    No devuelve nada y no lanza nunca: quien llama no puede distinguir el caso
    en que se envió del caso en que no había a quién enviar. Ver la explicación
    de arriba.
    """
    # Importes tardíos: a nivel de módulo crearían un ciclo con celery.
    from ..tasks import encolar
    from ..tasks.correo import enviar_correo

    normalizado = correo.lower().strip()

    # Vale la dirección de la cuenta **o** el correo de respaldo (tarea 13).
    # Es lo que necesita quien cambia de centro: pierde el correo institucional
    # con la cuenta activa y, sin esto, se queda fuera para siempre.
    #
    # El respaldo cuenta **solo si está verificado**. Sin esa condición,
    # cualquiera podría poner como respaldo la dirección de otra persona y
    # hacer que a esa persona le llegaran enlaces de una cuenta ajena: no le
    # daría acceso a nada, pero es una palanca de engaño servida.
    coincidencias = db.session.scalars(
        select(Usuario).where(
            (Usuario.correo == normalizado)
            | (
                (Usuario.correo_respaldo == normalizado)
                & Usuario.correo_respaldo_verificado_en.is_not(None)
            )
        )
    ).all()

    # Varias cuentas pueden compartir un respaldo —una pareja de docentes— y
    # cada una recibe el suyo. Se manda **a la dirección que se escribió**, no
    # a la principal: quien pide desde su respaldo es justamente quien ya no
    # tiene acceso a la otra.
    vivas = [u for u in coincidencias if not u.esta_eliminado]
    if not vivas:
        # Se registra para poder diagnosticar «no me llega el correo», pero no
        # se le cuenta a quien lo pidió.
        log.info("restablecimiento_sin_destinatario")
        return

    base = current_app.config["URL_BASE"].rstrip("/")
    horas = max(1, CADUCIDAD_RESTABLECER // 3600)
    for usuario in vivas:
        token = generar_restablecimiento(usuario)
        enlace = f"{base}/restablecer-contrasena?token={token}"
        texto, html = _texto_del_correo(enlace, horas)
        # `encolar` en vez de `.delay`: propaga el request_id a las cabeceras de
        # Celery, que es lo que permite seguir en el log del worker qué petición
        # originó el envío. Es la convención del proyecto.
        encolar(
            enviar_correo,
            destino=normalizado,
            asunto=_("Restablecer tu contraseña de AWEBO"),
            texto=texto,
            html=html,
        )
        log.info(
            "restablecimiento_solicitado",
            id_usuario=usuario.id_usuario,
            por_respaldo=usuario.correo != normalizado,
        )


def restablecer(token: str, nueva_contrasena: str) -> None:
    """Cambia la contraseña si el token es válido.

    Lanza :class:`TokenInvalido` si no lo es y :class:`AuthError` si la
    contraseña no cumple la política. Son dos errores distintos a propósito:
    el primero no dice nada útil a quien prueba tokens, y el segundo tiene que
    explicar qué le falta a la contraseña para que se pueda corregir.
    """
    id_usuario = leer_restablecimiento(token)   # lanza TokenInvalido

    # Antes de tocar nada: si la contraseña no vale, el token debe seguir
    # sirviendo para reintentar. Validar después de asignarla la invalidaría
    # —el hash ya habría cambiado— y obligaría a pedir otro enlace por haber
    # escrito una contraseña corta.
    #
    # `validar_contrasena` lanza ValueError; se traduce a AuthError igual que
    # hace `registrar_usuario`, para que la capa de API vea un solo tipo.
    try:
        validar_contrasena(nueva_contrasena)
    except ValueError as exc:
        raise AuthError("contrasena_debil", str(exc)) from exc

    usuario = db.session.get(Usuario, id_usuario)
    usuario.set_password(nueva_contrasena)
    db.session.commit()
    log.info("restablecimiento_completado", id_usuario=id_usuario)


__all__ = ["solicitar", "restablecer", "TokenInvalido", "AuthError"]
