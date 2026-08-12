"""Correo de respaldo: ponerlo, cambiarlo y quitarlo.

QUÉ PROBLEMA RESUELVE
---------------------
Los correos institucionales se reciclan. Cuando una cuenta se da de baja
conservando su contenido, sus situaciones quedan reclamables 90 días; si en ese
plazo alguien se registra con la misma dirección puede pedirlas, y esa persona
puede ser perfectamente el docente nuevo que heredó `jperez@ies.es`.

El respaldo es una dirección **personal**, que no se recicla al cambiar de
centro. La reclamación se confirma contra el respaldo de la cuenta original, no
contra la dirección reclamada, así que quien contesta es la persona de antes y
no quien acaba de heredar el buzón.

Se descartó antes una propuesta más simple —verificar por correo la dirección
reclamada— porque no resolvía nada: el enlace habría llegado precisamente a
quien no debía confirmarlo. Queda escrito en la hoja de ruta para no volver a
plantearla.

LA REGLA QUE LO SOSTIENE
------------------------
**Cambiar el respaldo exige confirmarlo desde el respaldo actual.** Sin ella,
quien se apodere del correo del centro podría restablecer la contraseña, entrar,
poner su propio respaldo y quedarse la cuenta para siempre: toda la protección
se evaporaría en tres pasos. Con ella, ese atacante se queda encerrado fuera de
la única vía que probaría identidad.

Poner el **primero** no lo exige, porque no hay nada anterior que proteger.

DECISIONES
----------
* El respaldo **no puede ser el correo principal de la propia cuenta**: sería un
  ancla que se recicla igual que el original, es decir, ninguna.
* **No es único.** Dos cuentas pueden compartir una dirección personal, y
  rechazarla contaría que existe una cuenta con ese respaldo.
* Un respaldo **sin verificar no cuenta para nada**. Si contara, cualquiera
  podría poner la dirección de otra persona y hacer que a esa persona le
  lleguen enlaces de una cuenta ajena.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from flask import current_app
from flask_babel import gettext as _

from ..extensions import db
from ..models import Usuario
from .tokens import CADUCIDAD_RESPALDO, TokenInvalido, generar_respaldo, leer_respaldo


log = structlog.get_logger(__name__)


class RespaldoError(Exception):
    """No se puede hacer, y el motivo sí se cuenta.

    Como en la baja: quien llama tiene sesión iniciada y habla de su propia
    cuenta, así que no hay nada que ocultar y sí algo que explicar.
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def _texto_del_correo(enlace: str, horas: int, es_cambio: bool) -> tuple[str, str]:
    """Cuerpo del mensaje, en texto y en HTML, en el idioma de la interfaz.

    Distingue poner de cambiar. En el segundo caso el mensaje llega a la
    dirección **anterior**, y quien lo lee necesita saber que alguien está
    intentando dejarla fuera: si no ha sido él, eso significa que su cuenta está
    comprometida y el aviso es lo único que se lo va a decir.

    OJO CON EL IDIOMA DE ESTE EN CONCRETO
    --------------------------------------
    Sale en el idioma que tuviera la página **quien pidió el cambio**, que no
    tiene por qué ser quien lo recibe: en un cambio, el destinatario es el dueño
    del respaldo anterior. Es lo mejor que se puede hacer sin guardar un idioma
    por cuenta, y en el caso que importa —un intruso pidiendo el cambio— el
    aviso llega igual: el enlace, el nombre de AWEBO y la estructura se
    reconocen aunque el texto no se entienda del todo.
    """
    caduca = _("El enlace caduca en {horas} horas.").format(horas=horas)

    if es_cambio:
        texto = "\n\n".join([
            _("Se ha pedido cambiar el correo de respaldo de tu cuenta de AWEBO."),
            _("Si has sido tú, confírmalo aquí:") + f"\n{enlace}",
            caduca,
            _(
                "SI NO HAS SIDO TÚ, alguien tiene acceso a tu cuenta. Este correo "
                "es el único aviso que vas a recibir: entra en AWEBO, cambia tu "
                "contraseña y avisa a la administración. Mientras no abras el "
                "enlace, tu respaldo sigue siendo este."
            ),
        ])
        html = (
            f"<p>{_('Se ha pedido cambiar el correo de respaldo de tu cuenta de AWEBO.')}</p>"
            f'<p><a href="{enlace}">{_("Si has sido tú, confírmalo aquí")}</a>.</p>'
            f"<p>{caduca}</p>"
            f"<p><strong>{_('Si no has sido tú, alguien tiene acceso a tu cuenta.')}</strong> "
            f"{_('Entra en AWEBO, cambia tu contraseña y avisa a la administración. Mientras no abras el enlace, tu respaldo sigue siendo este.')}</p>"
        )
    else:
        para_que = _(
            "Sirve para recuperar tu cuenta si pierdes el correo del centro, y "
            "para demostrar que tus situaciones de aprendizaje son tuyas si "
            "alguna vez hay que reclamarlas."
        )
        si_no = _(
            "Si no has sido tú, ignora este mensaje: sin abrir el enlace no se "
            "guarda nada."
        )
        texto = "\n\n".join([
            _("Has añadido esta dirección como correo de respaldo de tu cuenta de AWEBO."),
            _("Confírmalo abriendo este enlace:") + f"\n{enlace}",
            caduca,
            para_que,
            si_no,
        ])
        html = (
            f"<p>{_('Has añadido esta dirección como correo de respaldo de tu cuenta de AWEBO.')}</p>"
            f'<p><a href="{enlace}">{_("Confirmar esta dirección")}</a></p>'
            f"<p>{caduca}</p>"
            f"<p>{para_que}</p>"
            f"<p>{si_no}</p>"
        )
    return texto, html


def enmascarar(correo: str | None) -> str | None:
    """`ana.perez@ejemplo.es` → `a******z@ejemplo.es`.

    POR QUÉ NO SE ENSEÑA ENTERO, SIENDO DATO DEL PROPIO DUEÑO
    ---------------------------------------------------------
    Parecía teatro —quien mira el perfil tiene sesión, y con sesión ya lo tiene
    todo—, pero aquí no lo es, y el motivo es justo lo que hace útil al
    respaldo: **es lo único que la sesión no da**. Cambiarlo exige abrir un
    enlace enviado al respaldo actual, así que quien roba una sesión no puede
    tocarlo.

    Lo que sí podría hacer es *leerlo*, y entonces sabría a qué buzón atacar
    para completar el robo. Enmascararlo no le quita nada al dueño, que
    reconoce su propia dirección con ver el dominio y las puntas, y le quita al
    intruso el siguiente objetivo.

    El dominio se deja a la vista a propósito: es lo que permite reconocerla de
    un vistazo, y es lo menos identificativo de la dirección.
    """
    if not correo:
        return None
    local, arroba, dominio = correo.partition("@")
    if not arroba:
        return "*" * len(correo)
    if len(local) <= 2:
        oculto = local[:1] + "*"
    else:
        oculto = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{oculto}@{dominio}"


def solicitar(usuario: Usuario, correo_nuevo: str) -> str:
    """Manda el enlace de confirmación y dice **a qué dirección** se envió.

    Devolver el destino no es un detalle: cuando es un cambio, el correo va a
    la dirección **anterior**, y quien lo pide desde el perfil tiene que saber
    dónde mirar. Sin eso, estaría esperando un mensaje en un buzón al que no va
    a llegar.
    """
    from ..tasks import encolar
    from ..tasks.correo import enviar_correo

    nuevo = (correo_nuevo or "").strip().lower()
    if not nuevo:
        raise RespaldoError("correo_vacio", "Escribe una dirección de correo")
    if nuevo == (usuario.correo or "").lower():
        raise RespaldoError(
            "igual_al_principal",
            "El correo de respaldo tiene que ser distinto del de tu cuenta: "
            "si fuera el mismo no serviría para recuperarla.",
        )
    if usuario.tiene_respaldo and nuevo == usuario.correo_respaldo.lower():
        raise RespaldoError(
            "sin_cambios", "Esa dirección ya es tu correo de respaldo"
        )

    # LA REGLA. El enlace va al respaldo actual si lo hay, y solo al nuevo
    # cuando no hay nada que proteger todavía.
    es_cambio = usuario.tiene_respaldo
    destino = usuario.correo_respaldo if es_cambio else nuevo

    token = generar_respaldo(usuario, nuevo)
    base = current_app.config["URL_BASE"].rstrip("/")
    enlace = f"{base}/correo-de-respaldo?token={token}"
    horas = max(1, CADUCIDAD_RESPALDO // 3600)

    texto, html = _texto_del_correo(enlace, horas, es_cambio)
    encolar(
        enviar_correo,
        destino=destino,
        asunto=(_("Confirma el cambio de tu correo de respaldo")
                if es_cambio else _("Confirma tu correo de respaldo en AWEBO")),
        texto=texto,
        html=html,
    )
    log.info(
        "respaldo_solicitado", id_usuario=usuario.id_usuario, es_cambio=es_cambio
    )
    return destino


def confirmar(token: str) -> Usuario:
    """Aplica el respaldo que venga firmado en el enlace."""
    id_usuario, correo = leer_respaldo(token)   # lanza TokenInvalido

    usuario = db.session.get(Usuario, id_usuario)
    if usuario is None or usuario.esta_eliminado:
        raise TokenInvalido("usuario_inexistente")

    usuario.correo_respaldo = correo
    usuario.correo_respaldo_verificado_en = datetime.now(timezone.utc)
    db.session.commit()
    log.info("respaldo_confirmado", id_usuario=usuario.id_usuario)
    return usuario


def quitar(usuario: Usuario, contrasena: str) -> None:
    """Deja la cuenta sin respaldo.

    Pide la contraseña actual y **no** manda ningún enlace, al revés que
    cambiarlo. Es deliberado y conviene entender la asimetría: cambiar el
    respaldo por otro es lo que permitiría a un intruso quedarse la cuenta,
    porque acabaría controlando la vía de recuperación. Quitarlo solo deja a la
    cuenta como estaba antes de tenerlo — más desprotegida, pero sin entregarle
    nada a nadie.

    Exigir el enlace también para quitarlo tendría un efecto perverso: quien
    perdiera el acceso a su correo personal no podría cambiarlo **ni quitarlo**,
    y se quedaría con un respaldo muerto para siempre.
    """
    if not usuario.check_password(contrasena):
        raise RespaldoError("contrasena_incorrecta", "La contraseña no es correcta")

    usuario.correo_respaldo = None
    usuario.correo_respaldo_verificado_en = None
    db.session.commit()
    log.info("respaldo_retirado", id_usuario=usuario.id_usuario)


__all__ = [
    "solicitar", "confirmar", "quitar", "enmascarar",
    "RespaldoError", "TokenInvalido",
]
