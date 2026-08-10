"""Síntesis de voz con la API de OpenAI.

POR QUÉ ESTE PROVEEDOR EL PRIMERO
----------------------------------
Porque el proyecto ya tiene ``OPENAI_API_KEY`` y el cliente instalado para la
generación de texto, así que activarlo no añade ni una dependencia ni una
cuenta más. No es una recomendación sobre calidad: la interfaz existe
precisamente para que añadir otro sea un fichero, y hay opciones más baratas
—Google ronda los 4 dólares por millón de caracteres frente a los 15 de
OpenAI— si algún día el volumen lo justifica. Con una SA de unos diez mil
caracteres la diferencia es de céntimos, así que hoy no manda el precio.

EL IDIOMA NO SE LE PASA
------------------------
El modelo de voz de OpenAI deduce la lengua del propio texto, no admite un
parámetro de idioma. Eso es una ventaja aquí: las lenguas cooficiales no
dependen de que el proveedor tenga una voz declarada para ellas, que es
exactamente el problema que tiene ``SpeechSynthesis`` en el navegador. Se
registra el idioma de la locución de todos modos, porque si algún día suena
mal en gallego hay que poder saber qué se pidió.
"""
from __future__ import annotations

import logging

from flask import current_app

from .proveedor import Audio, Locucion, VozError


logger = logging.getLogger("voz.openai")

#: Tope de caracteres por petición que impone la API. Se comprueba aquí para
#: dar un error que se entienda en lugar del 400 del proveedor, que llega
#: envuelto en varias capas y no dice cuántos caracteres sobran.
LIMITE_CARACTERES = 4096


class ProveedorOpenAI:
    nombre = "openai"

    def sintetizar(self, locucion: Locucion) -> Audio:
        cfg = current_app.config
        clave = cfg.get("OPENAI_API_KEY", "")
        if not clave:
            raise VozError("OPENAI_API_KEY no está configurada")

        texto = locucion.texto.strip()
        if not texto:
            # Antes se llegaba a llamar con cadena vacía y el proveedor
            # devolvía un audio de cero bytes, que en el navegador es un
            # reproductor que no suena y no explica nada.
            raise VozError("No hay texto que leer")
        if len(texto) > LIMITE_CARACTERES:
            raise VozError(
                f"El texto tiene {len(texto)} caracteres y el máximo por "
                f"petición es {LIMITE_CARACTERES}. Hay que trocearlo antes."
            )

        # Importe tardío, como en `ai/openai_provider.py`: así los tests que no
        # tocan este camino no necesitan el paquete instalado.
        from openai import OpenAI

        cliente = OpenAI(api_key=clave, timeout=cfg.get("VOZ_TIMEOUT", 60))
        try:
            respuesta = cliente.audio.speech.create(
                model=cfg.get("VOZ_MODELO", "tts-1"),
                voice=cfg.get("VOZ_VOZ", "alloy"),
                input=texto,
                response_format="mp3",
            )
            datos = respuesta.read()
        except Exception as exc:
            # Solo el tipo de la excepción, como en `correo/smtp.py`: el
            # mensaje del proveedor puede llevar fragmentos del texto enviado,
            # y este log acaba en sitios donde no debería haber contenido de
            # las situaciones de nadie.
            logger.error("Fallo al sintetizar voz: %s", type(exc).__name__)
            raise VozError(f"Voz: {type(exc).__name__}") from exc

        if not datos:
            raise VozError("El proveedor devolvió un audio vacío")
        logger.info(
            "Audio generado: idioma=%s, %d caracteres, %d bytes",
            locucion.idioma, len(texto), len(datos),
        )
        return Audio(datos=datos, formato="mp3")
