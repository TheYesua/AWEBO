"""Elige el proveedor de voz según la configuración.

Mismo criterio que `app/correo/factoria.py`, incluido el valor por defecto:
aquí el defecto **no genera nada**. Ver `nulo.py` para el motivo.
"""
from __future__ import annotations

import logging

from flask import current_app

from .local import ProveedorLocal
from .nulo import ProveedorNulo
from .openai_voz import ProveedorOpenAI
from .proveedor import ProveedorVoz


logger = logging.getLogger("voz.factoria")

_PROVEEDORES = {
    "nulo": ProveedorNulo,
    "local": ProveedorLocal,
    "openai": ProveedorOpenAI,
}


def obtener_proveedor() -> ProveedorVoz:
    """Devuelve el proveedor configurado en ``VOZ_PROVEEDOR``.

    Ante un nombre desconocido cae al nulo y lo avisa, en vez de reventar: una
    errata en una variable de entorno no debe tumbar el arranque por algo que
    solo afecta al audio. Pero tampoco pasar inadvertida.
    """
    nombre = (current_app.config.get("VOZ_PROVEEDOR") or "nulo").lower()
    clase = _PROVEEDORES.get(nombre)
    if clase is None:
        logger.warning(
            "VOZ_PROVEEDOR='%s' no existe; se usa 'nulo'. Disponibles: %s",
            nombre,
            ", ".join(sorted(_PROVEEDORES)),
        )
        clase = ProveedorNulo
    return clase()
