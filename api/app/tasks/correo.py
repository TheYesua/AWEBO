"""Envío de correo en segundo plano.

POR QUÉ EN UNA TAREA Y NO EN LA PETICIÓN
-----------------------------------------
Hablar con un servidor SMTP puede tardar segundos, y con el servidor caído
tarda hasta agotar el tiempo de espera. Si eso ocurriera dentro de la petición,
la pantalla de «he olvidado la contraseña» se quedaría pensando —y, peor, el
tiempo de respuesta delataría si la cuenta existe: rápido cuando no hay nada
que enviar, lento cuando sí. La respuesta tiene que ser indistinguible en
contenido **y** en tiempo.

El envío es «dispara y olvida» a propósito. Que un correo no salga no debe
cambiar lo que ve quien lo pidió, porque contárselo sería contarle si la cuenta
existe. Queda en el registro, que es donde se mira cuando alguien avisa de que
no le llega nada.
"""
from __future__ import annotations

import structlog
from celery import shared_task

from ..correo import CorreoError, Mensaje, obtener_proveedor


log = structlog.get_logger(__name__)


@shared_task(name="awebo.enviar_correo", ignore_result=True)
def enviar_correo(destino: str, asunto: str, texto: str, html: str | None = None) -> None:
    """Entrega un correo con el proveedor configurado.

    No reintenta. Un reintento automático de un enlace de restablecimiento es
    contraproducente: el enlace caduca en una hora, y reintentar veinte minutos
    después manda a alguien a una página que le dirá que el enlace ya no vale.
    Si el envío falla, lo suyo es que la persona vuelva a pedirlo.
    """
    try:
        obtener_proveedor().enviar(
            Mensaje(destino=destino, asunto=asunto, texto=texto, html=html)
        )
    except CorreoError as exc:
        # Sin la dirección: este registro acaba en sitios donde no debería
        # haber correos de usuarios.
        log.error("correo_no_enviado", motivo=str(exc), asunto=asunto)
