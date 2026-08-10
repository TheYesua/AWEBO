"""El proveedor por defecto: no sintetiza nada.

POR QUÉ EL DEFECTO ES ESTE Y NO UNO QUE FUNCIONE
-------------------------------------------------
Es la misma decisión que en ``app/correo/consola.py``, por el mismo motivo y
con una vuelta de tuerca. Allí el riesgo era mandar un correo real a una
dirección de prueba; aquí es **gastar dinero sin querer**: la síntesis se
factura por caracteres, una SA completa ronda los diez mil, y basta con que
alguien arranque el entorno con una clave heredada para que cada clic en
«generar audio» tenga precio.

Al revés no pasa nada: si el defecto no genera, lo peor que ocurre es que haya
que poner una variable para activarlo, y eso se descubre en el primer intento.

NO SE DEVUELVE UN AUDIO FALSO
------------------------------
La tentación es devolver un MP3 de silencio para que «no falle». Sería la misma
trampa que ``create=True`` en un mock: todo verde y nada funcionando. Quien
pida audio sin proveedor configurado recibe un error claro que dice qué
variable falta.
"""
from __future__ import annotations

import logging

from .proveedor import Audio, Locucion, VozError


logger = logging.getLogger("voz.nulo")


class ProveedorNulo:
    nombre = "nulo"

    def sintetizar(self, locucion: Locucion) -> Audio:
        # Se registra el intento: en desarrollo es la única señal de que el
        # camino se recorrió entero y de que lo único que falta es configurar
        # un proveedor.
        logger.warning(
            "AUDIO NO GENERADO (proveedor nulo). Idioma=%s, %d caracteres. "
            "Configura VOZ_PROVEEDOR para generarlo de verdad.",
            locucion.idioma,
            len(locucion.texto),
        )
        raise VozError(
            "No hay proveedor de voz configurado. Define VOZ_PROVEEDOR en el "
            "entorno para poder generar audio."
        )
