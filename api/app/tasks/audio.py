"""Generación del audio en segundo plano.

POR QUÉ EN UNA TAREA Y NO EN LA PETICIÓN
-----------------------------------------
Sintetizar una sección tarda segundos y una SdA entera bastante más: el motor
es un binario que corre en la CPU. Hacerlo dentro de la petición dejaría la
pantalla colgada y, con varias personas a la vez, agotaría los trabajadores de
gunicorn — que son dos.

Al revés que el correo, aquí **el fallo sí se cuenta**. En el restablecimiento
callar era necesario para no revelar si una cuenta existe; aquí quien pulsó el
botón está esperando un audio y merece saber si no va a llegar.
"""
from __future__ import annotations

import structlog
from celery import shared_task

from ..services import audio as almacen
from ..voz import Locucion, VozError, obtener_proveedor


log = structlog.get_logger(__name__)


@shared_task(name="awebo.generar_audio", ignore_result=False)
def generar_audio(id_situacion: int, seccion: str, texto: str, idioma: str) -> dict:
    """Sintetiza una sección y la deja en el volumen de audio.

    No reintenta. Los fallos de este camino son deterministas —falta el modelo,
    falta el binario, el texto trae algo que el motor no sabe decir—, así que
    repetir da el mismo resultado tres veces más tarde. Es distinto de una red
    intermitente, que sí merece reintento.
    """
    try:
        audio = obtener_proveedor().sintetizar(Locucion(texto=texto, idioma=idioma))
    except VozError as exc:
        # El mensaje de VozError está escrito para que lo lea una persona y no
        # lleva contenido de la SdA: se puede registrar entero.
        log.warning(
            "audio_fallido", id_situacion=id_situacion, seccion=seccion,
            idioma=idioma, motivo=str(exc),
        )
        return {"ok": False, "motivo": str(exc)}

    ruta = almacen.guardar(id_situacion, seccion, texto, idioma, audio.datos)
    log.info(
        "audio_generado", id_situacion=id_situacion, seccion=seccion,
        idioma=idioma, bytes=len(audio.datos),
    )
    return {"ok": True, "bytes": len(audio.datos), "fichero": ruta.name}
