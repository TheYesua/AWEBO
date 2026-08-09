"""Elige el proveedor de correo según la configuración.

Mismo criterio que ``app/ai/factory.py``, con una diferencia importante en el
valor por defecto: aquí el defecto **no envía**. Ver ``consola.py``.
"""
from __future__ import annotations

import logging

from flask import current_app

from .consola import ProveedorConsola
from .proveedor import ProveedorCorreo
from .smtp import ProveedorSmtp


logger = logging.getLogger("correo.factoria")

_PROVEEDORES = {
    "consola": ProveedorConsola,
    "smtp": ProveedorSmtp,
}


def obtener_proveedor() -> ProveedorCorreo:
    """Devuelve el proveedor configurado en ``CORREO_PROVEEDOR``.

    Ante un nombre desconocido cae a consola y lo avisa, en lugar de reventar.
    Un error de tecleo en una variable de entorno no debe tumbar el arranque de
    la aplicación entera por algo que solo afecta al correo — pero tampoco debe
    pasar inadvertido, de ahí el aviso.
    """
    nombre = (current_app.config.get("CORREO_PROVEEDOR") or "consola").lower()
    clase = _PROVEEDORES.get(nombre)
    if clase is None:
        logger.warning(
            "CORREO_PROVEEDOR='%s' no existe; se usa 'consola'. Disponibles: %s",
            nombre,
            ", ".join(sorted(_PROVEEDORES)),
        )
        clase = ProveedorConsola
    return clase()
