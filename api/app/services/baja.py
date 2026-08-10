"""Baja de la propia cuenta, en dos pasos y con confirmación por correo.

POR QUÉ NO BASTA CON UN BOTÓN
------------------------------
Borrar la cuenta es lo más destructivo que un usuario puede pedir, y una sesión
abierta no prueba quién está delante: en un centro educativo el ordenador es
compartido y la sesión se queda abierta. Por eso se piden dos cosas que un
extraño no tiene a la vez: la **contraseña actual** y el **acceso al buzón**.

Ninguna de las dos sola basta. La contraseña sola no vale porque hasta ayer
cualquiera podía cambiarla desde el formulario de restablecer —ese agujero se
cerró en la tarea 11, y esta tarea depende de aquella justamente por eso—. El
correo solo tampoco: quien se deja la sesión abierta suele dejarse también el
correo abierto en la misma máquina.

LOS DOS MODOS
-------------
Son los mismos que tiene el administrador, decidido así a propósito y no por
inercia:

* **Conservando el contenido** pone la lápida. La cuenta deja de poder entrar,
  y sus situaciones siguen ahí, reclamables durante el plazo de gracia.
* **Total** borra la fila y el ``CASCADE`` se lleva el contenido de inmediato.
  No hay vuelta atrás ni reclamación posible, y la pantalla tiene que decirlo
  con todas las letras.

Cuál es «el correcto» depende de quién lo pida. Si es la propia persona
ejerciendo su derecho de supresión, conservar su contenido tres meses es
difícil de justificar; si es un administrador limpiando una cuenta inactiva, lo
que conviene es no perder el trabajo hecho. Como aquí quien pide es la persona,
la pantalla ofrece los dos pero el que se explica primero es el total.

LO QUE ESTE MÓDULO **NO** HACE
-------------------------------
No cierra la sesión. Eso es de la capa de API, y tiene su propia trampa: en la
tarea 7 se aprendió que invalidar al usuario en la base de datos no vacía la
caché de Flask-Login dentro de la misma petición (``g._login_user``).
"""
from __future__ import annotations

import structlog
from flask import current_app
from sqlalchemy import func, select

from ..extensions import db
from ..models import Rol, Usuario
from .tokens import CADUCIDAD_BAJA, TokenInvalido, generar_baja, leer_baja


log = structlog.get_logger(__name__)


class BajaError(Exception):
    """La baja no se puede hacer, y el motivo sí se le cuenta a quien la pide.

    Al revés que en el restablecimiento, aquí **sí** se distingue el caso: quien
    llama es un usuario con sesión iniciada pidiendo algo sobre su propia
    cuenta, así que no hay nada que filtrar que no supiera ya.
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _administradores_activos() -> int:
    """Cuántas cuentas de administrador quedan en pie.

    Cuenta solo las que no tienen lápida: una cuenta dada de baja no puede
    entrar, así que sumarla daría por cubierto un puesto que no lo está.
    """
    return db.session.scalar(
        select(func.count(Usuario.id_usuario))
        .join(Rol)
        .where(Rol.nombre == Rol.ADMINISTRADOR)
        .where(Usuario.eliminado_en.is_(None))
    ) or 0


def _comprobar_que_puede_irse(usuario: Usuario) -> None:
    """El último administrador no puede darse de baja.

    Si se le deja, la plataforma se queda sin nadie que apruebe reclamaciones
    de contenido ni gestione cuentas, y no hay forma de arreglarlo desde la web:
    haría falta entrar en la base de datos a mano.

    Se comprueba en los dos pasos, al pedir y al confirmar, y no solo en uno.
    Entre el correo y el clic pueden pasar treinta minutos, tiempo de sobra
    para que el otro administrador se dé de baja también. Comprobarlo solo al
    pedir dejaría pasar exactamente el caso que esta guarda existe para evitar.
    """
    if not usuario.es_administrador:
        return
    if _administradores_activos() > 1:
        return
    raise BajaError(
        "ultimo_administrador",
        "Eres la única cuenta de administración que queda. Nombra a otra "
        "persona administradora antes de darte de baja.",
    )


def _texto_del_correo(enlace: str, minutos: int, conservar: bool) -> tuple[str, str]:
    """Cuerpo del mensaje, en texto plano y en HTML.

    Como en el restablecimiento, no pasa por ``_()``: el envío ocurre en una
    tarea de Celery, fuera de una petición, y ahí no hay idioma de interfaz que
    consultar. Traducirlo pide guardar el idioma del usuario y activarlo dentro
    de la tarea; está anotado como lo que queda de la tarea 11.

    El texto **dice cuál de los dos modos se va a aplicar**. Sin eso, los dos
    correos serían idénticos y el enlace haría cosas distintas: quien lo abriera
    no tendría forma de saber cuál de las dos veces que pulsó es la que está
    confirmando.
    """
    if conservar:
        que_pasa = (
            "Tu cuenta dejará de poder entrar y tus situaciones de aprendizaje "
            f"se conservarán {Usuario.DIAS_DE_GRACIA} días, durante los cuales "
            "puedes recuperarlas volviendo a registrarte con este mismo correo."
        )
    else:
        que_pasa = (
            "Se borrarán tu cuenta y todas tus situaciones de aprendizaje de "
            "forma inmediata y definitiva. No se pueden recuperar después."
        )

    texto = (
        "Has pedido dar de baja tu cuenta de AWEBO.\n\n"
        f"{que_pasa}\n\n"
        f"Si es lo que quieres, abre este enlace para confirmarlo:\n{enlace}\n\n"
        f"El enlace caduca en {minutos} minutos y solo se puede usar una vez.\n\n"
        "Si no has sido tú, no hagas nada: mientras no se abra el enlace, tu "
        "cuenta sigue como estaba. Y cambia tu contraseña, porque para llegar "
        "hasta aquí alguien ha tenido que escribirla."
    )
    html = (
        "<p>Has pedido dar de baja tu cuenta de AWEBO.</p>"
        f"<p><strong>{que_pasa}</strong></p>"
        f'<p><a href="{enlace}">Confirmar la baja</a></p>'
        f"<p>El enlace caduca en {minutos} minutos y solo se puede usar una vez.</p>"
        "<p>Si no has sido tú, no hagas nada: mientras no se abra el enlace, tu "
        "cuenta sigue como estaba. Y cambia tu contraseña, porque para llegar "
        "hasta aquí alguien ha tenido que escribirla.</p>"
        f"<p style='color:#666;font-size:12px'>Si el enlace no funciona, copia "
        f"esta dirección en el navegador:<br>{enlace}</p>"
    )
    return texto, html


def solicitar(usuario: Usuario, contrasena: str, *, conservar_contenido: bool) -> None:
    """Primer paso: comprobar quién es y mandarle el enlace.

    Lanza :class:`BajaError` si la contraseña no es la suya o si es el último
    administrador. No devuelve nada: lo único que ocurre es que sale un correo.
    """
    # Importes tardíos: a nivel de módulo crearían un ciclo con Celery.
    from ..tasks import encolar
    from ..tasks.correo import enviar_correo

    if not usuario.check_password(contrasena):
        # Se cuenta el motivo, al contrario que en el restablecimiento: aquí ya
        # hay sesión iniciada, así que no se revela nada que no se supiera. Y
        # callarlo dejaría a quien se equivoca al teclear sin saber qué pasó.
        raise BajaError("contrasena_incorrecta", "La contraseña no es correcta")

    _comprobar_que_puede_irse(usuario)

    token = generar_baja(usuario, conservar_contenido=conservar_contenido)
    base = current_app.config["URL_BASE"].rstrip("/")
    enlace = f"{base}/baja?token={token}"
    minutos = max(1, CADUCIDAD_BAJA // 60)

    texto, html = _texto_del_correo(enlace, minutos, conservar_contenido)
    encolar(
        enviar_correo,
        destino=usuario.correo,
        asunto="Confirma la baja de tu cuenta de AWEBO",
        texto=texto,
        html=html,
    )
    log.info(
        "baja_solicitada",
        id_usuario=usuario.id_usuario,
        modo="lapida" if conservar_contenido else "total",
    )


def confirmar(token: str) -> dict:
    """Segundo paso: aplicar la baja del modo que diga el enlace.

    Lanza :class:`TokenInvalido` si el enlace no vale y :class:`BajaError` si
    entre medias la cuenta se ha quedado como única administradora.

    Devuelve un resumen con lo que se hizo, para que la interfaz pueda decir
    algo más útil que «hecho» — sobre todo en el modo total, donde conviene que
    conste cuántas situaciones se han ido.
    """
    id_usuario, conservar = leer_baja(token)   # lanza TokenInvalido

    usuario = db.session.get(Usuario, id_usuario)
    if usuario is None or usuario.esta_eliminado:
        # `leer_baja` ya lo comprueba; se repite porque entre esa lectura y
        # esta línea no hay transacción que lo garantice, y confirmar dos veces
        # el mismo enlace no debe reventar con un AttributeError.
        raise TokenInvalido("usuario_inexistente")

    _comprobar_que_puede_irse(usuario)

    resumen = {
        "id_usuario": usuario.id_usuario,
        "correo": usuario.correo,
        "situaciones": len(usuario.situaciones),
        "modo": "lapida" if conservar else "total",
        # Se calcula antes de borrar: después no hay a quién preguntárselo.
        "dias_de_gracia": Usuario.DIAS_DE_GRACIA if conservar else 0,
    }

    if conservar:
        usuario.marcar_eliminado()
    else:
        db.session.delete(usuario)
    db.session.commit()

    log.info("baja_confirmada", **resumen)
    return resumen


__all__ = ["solicitar", "confirmar", "BajaError", "TokenInvalido"]
