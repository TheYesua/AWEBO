"""Dónde vive el audio generado y cómo se le pone nombre.

POR QUÉ EN DISCO Y NO EN LA BASE DE DATOS
------------------------------------------
Decidido el 10/08. Un audio de una SdA entera ronda el medio mega; guardarlos
en Postgres haría que cada volcado de respaldo pasara de kilobytes a cientos de
megas, y la restauración verificada —que es lo que hace útil al respaldo, ver
``respaldar.ps1``— se volvería demasiado lenta para lanzarla a menudo. Un
respaldo que no se prueba no es un respaldo.

POR QUÉ NO HAY TABLA DE AUDIOS
-------------------------------
Porque no hace falta, y en este proyecto ya hay cuatro tablas de enlace que
nadie escribe nunca: se crearon «por si acaso» y hoy son cuatro consultas
vacías por cada SdA que se abre. No se repite.

**El nombre del fichero es el estado.** Se calcula a partir del texto, así que:

* si el fichero existe, el audio está listo y corresponde a *ese* texto;
* si el texto cambia, el nombre cambia y el audio viejo deja de encontrarse
  solo, sin ningún campo que mantener sincronizado;
* no hay forma de que la base de datos diga «hay audio» y el disco diga que no.

Al escribir uno nuevo se borran los de la misma sección: así una SdA que se
edita diez veces no deja diez ficheros muertos.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from flask import current_app


logger = logging.getLogger("voz.audio")

#: Secciones válidas. Se valida contra esta lista y no contra «lo que llegue»
#: porque el nombre entra en una ruta de fichero: sin esto, una sección
#: `../../etc/passwd` escribiría donde no debe.
_SECCION_VALIDA = re.compile(r"^[a-z0-9_]{1,40}$")


def raiz() -> Path:
    return Path(current_app.config.get("VOZ_AUDIO_DIR", "/audio"))


def _huella(texto: str, idioma: str) -> str:
    """Identifica el contenido, no la situación.

    Incluye el idioma porque la misma sección leída en gallego y en castellano
    son dos audios distintos, y si compartieran nombre el segundo se serviría
    con la voz del primero.
    """
    return hashlib.sha256(f"{idioma}\x00{texto}".encode("utf-8")).hexdigest()[:16]


def ruta(id_situacion: int, seccion: str, texto: str, idioma: str) -> Path:
    """Dónde va —o de dónde se lee— el audio de una sección."""
    if not _SECCION_VALIDA.match(seccion or ""):
        raise ValueError(f"Nombre de sección no válido: {seccion!r}")
    return raiz() / str(int(id_situacion)) / f"{seccion}-{_huella(texto, idioma)}.mp3"


def guardar(id_situacion: int, seccion: str, texto: str, idioma: str, datos: bytes) -> Path:
    """Escribe el audio y limpia las versiones anteriores de esa sección."""
    destino = ruta(id_situacion, seccion, texto, idioma)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Primero a un fichero aparte y luego renombrar: si el proceso muere a
    # medias, no queda un MP3 truncado con el nombre bueno, que sería
    # indistinguible de uno completo y se serviría igual.
    provisional = destino.with_suffix(".parcial")
    provisional.write_bytes(datos)
    provisional.replace(destino)

    for viejo in destino.parent.glob(f"{seccion}-*.mp3"):
        if viejo != destino:
            viejo.unlink(missing_ok=True)
            logger.info("Audio anterior de la sección %s descartado", seccion)
    return destino


def borrar_los_de(id_situacion: int) -> int:
    """Se llama al borrar una SdA.

    Sin esto, el volumen acumularía el audio de situaciones que ya no existen:
    invisible desde la aplicación y creciendo. Devuelve cuántos se borraron
    para poder registrarlo.
    """
    carpeta = raiz() / str(int(id_situacion))
    if not carpeta.is_dir():
        return 0
    borrados = 0
    for fichero in carpeta.iterdir():
        fichero.unlink(missing_ok=True)
        borrados += 1
    carpeta.rmdir()
    return borrados
