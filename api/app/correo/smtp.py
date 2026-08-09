"""Envío real por SMTP.

POR QUÉ SMTP Y NO EL SDK DE UN PROVEEDOR CONCRETO
--------------------------------------------------
Todos los servicios de envío transaccional ofrecen SMTP además de su API. Al
hablar SMTP, cambiar de proveedor son cuatro variables de entorno en lugar de
una clase nueva, una dependencia más y otro juego de errores que traducir.

Un servidor de correo propio se descartó por lo de siempre: reputación de IP,
SPF, DKIM, DMARC y listas negras son trabajo continuo, y si los mensajes acaban
en spam el restablecimiento no funciona igual. Con SMTP se puede usar cualquier
servicio transaccional sin atarse a ninguno.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

from .proveedor import CorreoError, Mensaje


logger = logging.getLogger("correo.smtp")


class ProveedorSmtp:
    nombre = "smtp"

    def enviar(self, mensaje: Mensaje) -> None:
        cfg = current_app.config
        servidor = cfg.get("SMTP_HOST", "")
        if not servidor:
            raise CorreoError("SMTP_HOST no está configurado")

        correo = EmailMessage()
        correo["From"] = cfg.get("CORREO_REMITENTE") or cfg.get("SMTP_USER", "")
        correo["To"] = mensaje.destino
        correo["Subject"] = mensaje.asunto
        correo.set_content(mensaje.texto)
        if mensaje.html:
            correo.add_alternative(mensaje.html, subtype="html")

        puerto = int(cfg.get("SMTP_PORT", 587))
        usuario = cfg.get("SMTP_USER", "")
        clave = cfg.get("SMTP_PASSWORD", "")
        sin_tls = bool(cfg.get("SMTP_SIN_TLS", False))

        # Sin cifrado y con credenciales es la peor combinación posible: el
        # LOGIN de SMTP manda usuario y contraseña en base64, que no es cifrado
        # sino codificación, legible por cualquiera en el camino. Se corta aquí
        # en vez de enviarlas, porque quien active SMTP_SIN_TLS lo hará para el
        # buzón local —donde no hay credenciales— y encontrarse esa variable
        # puesta contra un proveedor real es un accidente, no una intención.
        if sin_tls and usuario:
            raise CorreoError(
                "SMTP_SIN_TLS con SMTP_USER: se enviarían las credenciales en "
                "claro. Quita SMTP_SIN_TLS o quita el usuario."
            )
        # Un tiempo de espera corto y explícito. Sin él, smtplib puede quedarse
        # colgado hasta el tiempo de espera del sistema operativo —minutos— y,
        # como el envío va dentro de una tarea Celery, dejaría un worker
        # bloqueado sin que nadie lo note.
        espera = int(cfg.get("SMTP_TIMEOUT", 15))

        try:
            # El puerto 465 habla TLS desde el primer byte; el 587 empieza en
            # claro y sube con STARTTLS. Confundirlos da un error de protocolo
            # que no dice nada, así que se elige por el puerto.
            if puerto == 465:
                contexto = ssl.create_default_context()
                with smtplib.SMTP_SSL(servidor, puerto, timeout=espera,
                                      context=contexto) as cliente:
                    if usuario:
                        cliente.login(usuario, clave)
                    cliente.send_message(correo)
            else:
                with smtplib.SMTP(servidor, puerto, timeout=espera) as cliente:
                    if not sin_tls:
                        cliente.starttls(context=ssl.create_default_context())
                    if usuario:
                        cliente.login(usuario, clave)
                    cliente.send_message(correo)
        except (smtplib.SMTPException, OSError) as exc:
            # El mensaje del error puede llevar la dirección de destino, y este
            # log acaba en sitios donde no debería haber correos de usuarios.
            logger.error("Fallo al enviar por SMTP: %s", type(exc).__name__)
            raise CorreoError(f"SMTP: {type(exc).__name__}") from exc
