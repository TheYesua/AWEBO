"""Proveedor de correo que no envía nada: lo escribe en el registro.

Es el proveedor **por defecto**, y esa decisión es deliberada. Si el defecto
fuera SMTP, bastaría con que alguien arrancase el entorno con unas credenciales
heredadas para mandar correo de verdad a direcciones de prueba. Al revés no
pasa nada: quien quiera enviar de verdad tiene que pedirlo.

En desarrollo cumple además una función práctica. El enlace de
restablecimiento aparece en el log del contenedor, así que el flujo completo se
puede probar sin servidor de correo:

    docker compose logs -f api | Select-String "enlace"
"""
from __future__ import annotations

import logging

from .proveedor import Mensaje


logger = logging.getLogger("correo.consola")


class ProveedorConsola:
    nombre = "consola"

    def enviar(self, mensaje: Mensaje) -> None:
        # A nivel WARNING y no INFO a propósito: en desarrollo el log lleva
        # mucho ruido de peticiones, y esto hay que encontrarlo. Es la única
        # forma de completar un restablecimiento sin servidor de correo.
        logger.warning(
            "CORREO NO ENVIADO (proveedor de consola)\n"
            "  Para:   %s\n"
            "  Asunto: %s\n"
            "  --- texto ---\n%s\n  -------------",
            mensaje.destino,
            mensaje.asunto,
            mensaje.texto,
        )
