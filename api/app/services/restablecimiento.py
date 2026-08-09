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
"""
from __future__ import annotations

import structlog
from flask import current_app
from sqlalchemy import select

from ..extensions import db
from ..models import Usuario
from .auth_service import AuthError, validar_contrasena
from .tokens import CADUCIDAD_RESTABLECER, TokenInvalido, generar_restablecimiento, leer_restablecimiento


log = structlog.get_logger(__name__)


def _texto_del_correo(enlace: str, horas: int) -> tuple[str, str]:
    """Cuerpo del mensaje, en texto plano y en HTML.

    No se traduce con ``_()``. El correo se envía desde una tarea de Celery,
    fuera de una petición, así que ahí no hay idioma de interfaz que consultar.
    Traducirlo bien exige guardar el idioma del usuario y activarlo en la
    tarea, y eso es trabajo de la misma tarea 11 pero de otro paso; escribirlo
    a medias daría correos en el idioma de quien lanzó el worker.
    """
    texto = (
        "Has pedido restablecer tu contraseña en AWEBO.\n\n"
        f"Abre este enlace para elegir una nueva:\n{enlace}\n\n"
        f"El enlace caduca en {horas} hora(s) y solo se puede usar una vez.\n\n"
        "Si no has sido tú, no hace falta que hagas nada: mientras no se abra "
        "el enlace, tu contraseña sigue siendo la de siempre."
    )
    html = (
        "<p>Has pedido restablecer tu contraseña en AWEBO.</p>"
        f'<p><a href="{enlace}">Elegir una contraseña nueva</a></p>'
        f"<p>El enlace caduca en {horas} hora(s) y solo se puede usar una vez.</p>"
        "<p>Si no has sido tú, no hace falta que hagas nada: mientras no se "
        "abra el enlace, tu contraseña sigue siendo la de siempre.</p>"
        f"<p style='color:#666;font-size:12px'>Si el enlace no funciona, "
        f"copia esta dirección en el navegador:<br>{enlace}</p>"
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
    usuario = db.session.scalar(select(Usuario).where(Usuario.correo == normalizado))

    if usuario is None or usuario.esta_eliminado:
        # Se registra para poder diagnosticar «no me llega el correo», pero no
        # se le cuenta a quien lo pidió.
        log.info("restablecimiento_sin_destinatario")
        return

    token = generar_restablecimiento(usuario)
    base = current_app.config["URL_BASE"].rstrip("/")
    enlace = f"{base}/restablecer-contrasena?token={token}"
    horas = max(1, CADUCIDAD_RESTABLECER // 3600)

    texto, html = _texto_del_correo(enlace, horas)
    # `encolar` en vez de `.delay`: propaga el request_id a las cabeceras de
    # Celery, que es lo que permite seguir en el log del worker qué petición
    # originó el envío. Es la convención del proyecto.
    encolar(
        enviar_correo,
        destino=usuario.correo,
        asunto="Restablecer tu contraseña de AWEBO",
        texto=texto,
        html=html,
    )
    log.info("restablecimiento_solicitado", id_usuario=usuario.id_usuario)


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
