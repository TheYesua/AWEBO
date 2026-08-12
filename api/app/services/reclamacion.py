"""Recuperar el contenido de una cuenta dada de baja.

EL PROBLEMA
-----------
Una cuenta con lápida conserva sus situaciones 90 días. Si en ese plazo alguien
se registra con la misma dirección, puede pedirlas. Pero los correos
institucionales se reciclan: quien lo pide puede ser perfectamente el docente
nuevo que heredó `jperez@ies.es`, convencido de buena fe de que ese contenido
es suyo porque la dirección lo es.

QUIÉN PUEDE APROBARLA, Y POR QUÉ EN ESE ORDEN
----------------------------------------------
1. **La persona anterior, desde su correo de respaldo.** Es la mejor prueba
   posible: el respaldo es personal y no se recicla, así que quien lee ese
   buzón es quien era. Si quien reclama es la misma persona —cambió de centro y
   perdió la dirección—, sigue leyéndolo y confirma. Si es quien heredó la
   dirección, el enlace llega a otro sitio y no pasa nada.
2. **Un administrador**, cuando no hay respaldo o se ha perdido el acceso.
   Decide con lo que ve —correo, centro, cuántas SdA— y puede preguntar.

El orden importa: el administrador queda como **último recurso**, no como
trámite obligatorio. Antes era lo único que había.

POR QUÉ NO VALÍA VERIFICAR LA DIRECCIÓN RECLAMADA
--------------------------------------------------
Fue mi primera propuesta y era mala: el enlace habría ido a la dirección en
disputa, que es la que controla quien acaba de heredarla. Verificar un buzón
demuestra que controlas ese buzón, no que seas la misma persona. Queda escrito
para no volver a plantearla.
"""
from __future__ import annotations

import structlog
from flask import current_app
from flask_babel import gettext as _
from sqlalchemy import select

from ..extensions import db
from ..models import Rol, Usuario
from .tokens import (
    CADUCIDAD_RECLAMACION,
    TokenInvalido,
    generar_reclamacion,
    leer_reclamacion,
)


log = structlog.get_logger(__name__)


class ReclamacionError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def aplicar(usuario: Usuario) -> dict:
    """Convierte la solicitud pendiente en la cuenta de quien la pidió.

    Vive aquí y no en `admin_service` porque ahora hay **dos** vías que acaban
    en esto —el administrador y el correo de respaldo—, y tener dos copias de
    la asignación de campos es una invitación a que una se quede corta. En este
    proyecto ya pasó con la regla de `es_adaptacion`, duplicada en el modelo y
    en el prompt.
    """
    solicitud = usuario.reclamacion_pendiente
    if not solicitud:
        raise ReclamacionError("sin_reclamacion", "No hay ninguna solicitud pendiente")

    rol = db.session.scalar(
        select(Rol).where(Rol.nombre == solicitud.get("rol", Rol.DOCENTE))
    )
    if rol is None:
        raise ReclamacionError("rol_inexistente", "El rol solicitado ya no existe")

    # El rol sale de la solicitud, que a su vez lo fijó el registro. Nunca del
    # que tuviera la cuenta anterior: heredarlo convertiría el formulario
    # público en una escalada de privilegios si la cuenta era administradora.
    usuario.id_rol = rol.id_rol
    usuario.contrasena_hash = solicitud["contrasena_hash"]
    usuario.nombre = solicitud["nombre"]
    usuario.centro_educativo = solicitud.get("centro_educativo")
    usuario.especialidad = solicitud.get("especialidad")
    usuario.comunidad_autonoma = solicitud.get("comunidad_autonoma")

    # Preferencias de la persona anterior: se limpian. Son suyas, no del
    # correo, y dejarlas puestas haría que la cuenta generase con un proveedor
    # que quien la usa no ha elegido.
    usuario.proveedor_ia = None
    usuario.modelo_ia = None
    usuario.idioma_interfaz = None

    # Y el respaldo también, por el mismo motivo y con más razón: es la
    # dirección personal de **otra persona**. Dejarlo puesto daría a quien se
    # marchó una vía permanente para restablecer la contraseña de una cuenta
    # que ya no es suya.
    usuario.correo_respaldo = None
    usuario.correo_respaldo_verificado_en = None

    usuario.eliminado_en = None
    usuario.reclamacion_pendiente = None
    db.session.commit()

    resumen = {
        "id_usuario": usuario.id_usuario,
        "correo": usuario.correo,
        "situaciones": len(usuario.situaciones),
    }
    log.info("reclamacion_aplicada", **resumen)
    return resumen


def descartar(usuario: Usuario) -> None:
    """Borra la solicitud. El contenido sigue con su lápida hasta que venza."""
    usuario.reclamacion_pendiente = None
    db.session.commit()
    log.info("reclamacion_descartada", id_usuario=usuario.id_usuario)


def avisar_al_respaldo(usuario: Usuario) -> str | None:
    """Pide a la persona anterior que apruebe, si dejó correo de respaldo.

    Devuelve la dirección avisada, o ``None`` si no hay respaldo — y entonces
    la solicitud espera a un administrador, como antes.

    **El correo no dice quién reclama.** Ni su nombre ni su centro: quien lo
    recibe ya no usa AWEBO y no tiene por qué enterarse de con quién comparte
    dirección institucional ahora. Basta con que sepa qué se le pide.
    """
    from ..tasks import encolar
    from ..tasks.correo import enviar_correo

    if not usuario.tiene_respaldo:
        return None

    token = generar_reclamacion(usuario)
    base = current_app.config["URL_BASE"].rstrip("/")
    enlace = f"{base}/reclamacion?token={token}"
    dias = max(1, CADUCIDAD_RECLAMACION // 86400)
    cuantas = len(usuario.situaciones)

    cabecera = _(
        "Alguien se ha registrado en AWEBO con la dirección de una cuenta que "
        "diste de baja, y ha pedido recuperar su contenido: {cuantas} "
        "situación(es) de aprendizaje."
    ).format(cuantas=cuantas)
    si_eres = _(
        "SI ERES TÚ —por ejemplo, has cambiado de centro y vuelves con otra "
        "dirección— confírmalo aquí:"
    )
    si_no = _(
        "SI NO ERES TÚ, no hagas nada. Sin tu confirmación, ese contenido no se "
        "entrega: seguirá retenido hasta que venza el plazo y se borre. Si "
        "quieres, puedes avisar a la administración de AWEBO."
    )
    caduca = _("El enlace caduca en {dias} días.").format(dias=dias)

    texto = "\n\n".join([cabecera, si_eres + f"\n{enlace}", caduca, si_no])
    html = (
        f"<p>{cabecera}</p>"
        f"<p><strong>{_('Si eres tú')}</strong> "
        f"{_('—por ejemplo, has cambiado de centro y vuelves con otra dirección—')} "
        f'<a href="{enlace}">{_("confírmalo aquí")}</a>.</p>'
        f"<p>{caduca}</p>"
        f"<p><strong>{_('Si no eres tú, no hagas nada.')}</strong> "
        f"{_('Sin tu confirmación ese contenido no se entrega: seguirá retenido hasta que venza el plazo y se borre.')}</p>"
    )
    encolar(
        enviar_correo,
        destino=usuario.correo_respaldo,
        asunto=_("¿Autorizas recuperar el contenido de tu cuenta de AWEBO?"),
        texto=texto,
        html=html,
    )
    log.info("reclamacion_enviada_al_respaldo", id_usuario=usuario.id_usuario)
    return usuario.correo_respaldo


def aprobar_por_token(token: str) -> dict:
    """Aprueba la reclamación desde el enlace que recibió el dueño anterior."""
    id_usuario = leer_reclamacion(token)   # lanza TokenInvalido

    usuario = db.session.get(Usuario, id_usuario)
    if usuario is None:
        raise TokenInvalido("usuario_inexistente")
    if not usuario.reclamacion_pendiente:
        # Puede pasar sin que nadie haya hecho nada raro: un administrador la
        # resolvió antes, o quien reclamaba se registró de otra forma. Se dice
        # tal cual en vez de fingir un token inválido, porque quien abre el
        # enlace es la persona legítima y merece saber qué pasó.
        raise ReclamacionError(
            "sin_reclamacion",
            "Esa solicitud ya se resolvió; no queda nada que autorizar.",
        )

    resumen = aplicar(usuario)
    log.info("reclamacion_aprobada_por_respaldo", id_usuario=usuario.id_usuario)
    return resumen


__all__ = [
    "aplicar", "descartar", "avisar_al_respaldo", "aprobar_por_token",
    "ReclamacionError", "TokenInvalido",
]
