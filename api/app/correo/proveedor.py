"""Interfaz común para el envío de correo.

Mismo patrón que ``app/ai/provider.py``, y por el mismo motivo: el proveedor
concreto se elige por configuración y cambiarlo no debe tocar nada más que una
variable de entorno.

POR QUÉ UNA INTERFAZ Y NO LLAMAR A smtplib DIRECTAMENTE
-------------------------------------------------------
En desarrollo no debe salir ni un correo. Los datos de prueba llevan
direcciones con pinta de reales —``docente1@ejemplo.es`` es inofensivo, pero
alguien acabará poniendo la suya— y un envío accidental a una dirección ajena
no se puede deshacer. Con la interfaz, el desarrollo usa el proveedor de
consola y para mandar de verdad hay que pedirlo explícitamente.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CorreoError(Exception):
    """No se ha podido entregar el mensaje al servidor de salida.

    Que un envío falle **no debe** cambiar lo que ve quien lo provocó: en el
    restablecimiento de contraseña la respuesta es la misma exista o no la
    cuenta, y añadir un error de envío rompería esa indistinguibilidad.
    Quien captura esta excepción la registra y sigue.
    """


@dataclass(frozen=True)
class Mensaje:
    """Un correo listo para enviar.

    Se manda siempre en texto plano además de HTML. No es cortesía: hay
    clientes que bloquean el HTML por defecto, y un enlace de restablecimiento
    que no se puede pulsar deja la cuenta inaccesible.
    """

    destino: str
    asunto: str
    texto: str
    html: str | None = None


class ProveedorCorreo(Protocol):
    """Lo único que el resto de la aplicación necesita saber."""

    nombre: str

    def enviar(self, mensaje: Mensaje) -> None:
        """Entrega ``mensaje``. Lanza :class:`CorreoError` si no puede."""
        ...
