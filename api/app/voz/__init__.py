"""Síntesis de voz de servidor (tarea 8b).

Cubre el hueco que deja la lectura del navegador de la tarea 8a: cuando el
sistema no tiene voz instalada para el idioma de la SA, el botón de escuchar
desaparece — y eso ocurre justo con las lenguas cooficiales.

El proveedor por defecto **no genera nada**: la síntesis se factura por
caracteres y un entorno de desarrollo con una clave heredada no debe poder
gastar dinero por accidente.
"""
from .factoria import obtener_proveedor
from .proveedor import Audio, Locucion, ProveedorVoz, VozError

__all__ = ["obtener_proveedor", "Audio", "Locucion", "ProveedorVoz", "VozError"]
