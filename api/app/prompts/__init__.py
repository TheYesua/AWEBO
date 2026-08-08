"""Sistema de prompts versionados por sección (LOMLOE-first).

La generación de una Situación de Aprendizaje se descompone en 6 secciones
LOMLOE; cada una tiene su propio módulo ``secciones/<nombre>_v<N>.py`` con:

* ``NOMBRE``: clave estable usada por ``contenido[NOMBRE]``.
* ``VERSION``: identificador de versión (``"v1"``, ``"v2"``...).
* ``build(contexto) -> LLMRequest``: construye la petición al LLM.

El registro :data:`SECCIONES` mapea clave → función constructora y
versión activa. Para evolucionar un prompt:

1. Crear ``<nombre>_v2.py`` con la nueva lógica.
2. Actualizar :data:`SECCIONES` para apuntar al v2.
3. Los SA ya generados conservan su contenido; sólo los futuros usan v2.
"""
from __future__ import annotations

from typing import Callable

from .contexto import ContextoGeneracion, construir_contexto
from .secciones import (
    atencion_diversidad_v1,
    conexion_curricular_v1,
    descripcion_v1,
    evaluacion_v1,
    objetivos_v1,
    secuencia_sesiones_v1,
)


# --- Registro de secciones activas ---------------------------------------

_MODULOS = (
    descripcion_v1,
    objetivos_v1,
    conexion_curricular_v1,
    secuencia_sesiones_v1,
    evaluacion_v1,
    atencion_diversidad_v1,
)


#: Orden canónico de generación. Es el orden en que se invocan y también el
#: orden en que aparecen las claves en ``contenido``.
ORDEN_SECCIONES: tuple[str, ...] = tuple(m.NOMBRE for m in _MODULOS)


#: Mapa {nombre_seccion: (version, build_func)} para consumo por las tareas.
SECCIONES: dict[str, tuple[str, Callable]] = {
    m.NOMBRE: (m.VERSION, m.build) for m in _MODULOS
}


__all__ = [
    "ContextoGeneracion",
    "construir_contexto",
    "ORDEN_SECCIONES",
    "SECCIONES",
]
