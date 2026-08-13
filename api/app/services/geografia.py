"""Fijar la provincia de una cuenta o de una SdA, y derivar su comunidad.

POR QUÉ HAY UNA FUNCIÓN Y NO UNA ASIGNACIÓN
---------------------------------------------
Porque hay dos columnas —`provincia` y `comunidad_autonoma`— y una sola
decisión. La provincia es lo que el docente elige; la comunidad es lo que
decide qué currículo se aplica, y **se calcula**. Nunca al revés.

Tener las dos guardadas es redundante y por tanto peligroso: el día que alguien
escriba una sin la otra, tendremos una SdA que dice ser de Sevilla y usar el
currículo de Cataluña, y no habrá forma de saber cuál de los dos campos miente.
Este módulo es el único sitio que las escribe, así que no pueden divergir.

POR QUÉ NO SE ELIMINA `comunidad_autonoma`
--------------------------------------------
Se planteó, y habría sido más limpio: una sola columna y la comunidad derivada
al vuelo en cada consulta. Se descartó porque ese campo aparece en veinte
sitios —esquemas, panel de administración, prompt, cinco filtros de currículo—
y renombrarlo en todos a la vez es un cambio grande y de riesgo alto para lo
que aporta. Queda anotado como deuda: la fuente de verdad es `provincia`.
"""
from __future__ import annotations

import structlog

from ..curriculo import comunidades, provincias


log = structlog.get_logger(__name__)


def fijar_provincia(objeto, valor: str | None) -> str | None:
    """Escribe ``provincia`` y la ``comunidad_autonoma`` que le corresponde.

    Devuelve el código de provincia guardado, o ``None`` si no se reconoció.

    Con un valor irreconocible **se limpian las dos columnas** en vez de dejar
    la anterior puesta. Quedarse con la vieja daría un objeto que dice ser de
    un sitio y genera contra el currículo de otro, que es justo la incoherencia
    que este módulo existe para impedir.
    """
    codigo = provincias.normalizar(valor)

    if codigo is None:
        if valor:
            log.info("provincia_no_reconocida", valor=valor)
        objeto.provincia = None
        objeto.comunidad_autonoma = None
        return None

    objeto.provincia = codigo
    # El **nombre** de la comunidad, no su código: `comunidad_autonoma` lleva
    # nombres desde el TFG y el prompt lo lee para contárselo al modelo.
    # `comunidades.normalizar` lo vuelve a convertir en código donde hace falta.
    objeto.comunidad_autonoma = comunidades.nombre(provincias.comunidad_de(codigo))
    return codigo


def comunidad_de(objeto) -> str | None:
    """Código de comunidad de una cuenta o SdA, mirando primero la provincia.

    El orden importa. La provincia es la fuente de verdad desde que existe,
    pero las filas anteriores solo tienen `comunidad_autonoma` —texto libre—,
    así que se cae a ella. Al revés, una SdA migrada se quedaría sin currículo.
    """
    if getattr(objeto, "provincia", None):
        derivada = provincias.comunidad_de(objeto.provincia)
        if derivada:
            return derivada
    return comunidades.normalizar(getattr(objeto, "comunidad_autonoma", None))


__all__ = ["fijar_provincia", "comunidad_de"]
