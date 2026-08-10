"""Interfaz común para la síntesis de voz (tarea 8b).

Mismo patrón que ``app/ai/provider.py`` y ``app/correo/proveedor.py``: el
proveedor concreto se elige por configuración y cambiarlo no debe tocar nada
más que una variable de entorno.

QUÉ HUECO VIENE A CUBRIR
-------------------------
La tarea 8a lee las secciones en voz alta con ``SpeechSynthesis``, que es
gratis y no sale del navegador. Pero solo funciona si el sistema tiene una voz
instalada para el idioma de la SA, y ``detalle.html`` **oculta el botón cuando
no la hay**. Eso pasa justo con catalán, gallego y euskera en buena parte de
los equipos: la lectura falla precisamente donde más falta hace, y quien la
necesita no ve un error, ve que el botón no está.

La síntesis de servidor cubre ese hueco y, de paso, deja un fichero que se
puede descargar, compartir o escuchar sin conexión — cosa que
``SpeechSynthesis`` no permite, porque solo suena mientras la pestaña vive.

POR QUÉ EL AUDIO SÍ Y EL VÍDEO NO
----------------------------------
La pregunta que había que responder antes de programar era qué problema de
accesibilidad resuelve el vídeo que no resuelva el audio. No se encontró
ninguno: lo que produce AWEBO es un documento de programación docente, y un
documento se escucha. El vídeo queda descartado por escrito en la hoja de ruta.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class VozError(Exception):
    """No se ha podido sintetizar el audio.

    Se distingue del silencio a propósito. Al contrario que en el correo —donde
    un fallo no debe cambiar lo que ve quien lo provocó—, aquí la persona está
    esperando un audio: si no se puede, hay que decírselo. Callarlo dejaría un
    botón que no hace nada, que es el mismo problema que esta tarea viene a
    arreglar.
    """


@dataclass(frozen=True)
class Locucion:
    """Lo que hay que decir y en qué lengua.

    ``idioma`` es el de la situación de aprendizaje, no el de la interfaz. Son
    cosas distintas: alguien puede tener AWEBO en castellano y estar
    escribiendo una SA en gallego, y el audio tiene que sonar en gallego o no
    sirve para nada.
    """

    texto: str
    idioma: str


@dataclass(frozen=True)
class Audio:
    """El resultado: los bytes y de qué formato son.

    Se devuelven los bytes en lugar de escribir un fichero desde el proveedor.
    Quién decide dónde vive el audio es la capa que lo pide, y así el proveedor
    se puede probar sin tocar el disco.
    """

    datos: bytes
    formato: str = "mp3"

    @property
    def tipo_mime(self) -> str:
        return {"mp3": "audio/mpeg", "wav": "audio/wav", "opus": "audio/ogg"}.get(
            self.formato, "application/octet-stream"
        )


class ProveedorVoz(Protocol):
    """Lo único que el resto de la aplicación necesita saber."""

    nombre: str

    def sintetizar(self, locucion: Locucion) -> Audio:
        """Devuelve el audio. Lanza :class:`VozError` si no puede."""
        ...
