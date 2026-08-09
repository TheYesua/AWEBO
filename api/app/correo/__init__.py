"""Envío de correo: interfaz, proveedores y factoría.

Ver ``proveedor.py`` para el porqué de la interfaz y ``consola.py`` para el
porqué de que el proveedor por defecto no envíe nada.
"""
from .factoria import obtener_proveedor
from .proveedor import CorreoError, Mensaje, ProveedorCorreo

__all__ = ["obtener_proveedor", "CorreoError", "Mensaje", "ProveedorCorreo"]
