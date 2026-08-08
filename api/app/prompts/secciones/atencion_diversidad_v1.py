"""Sección ``atencion_diversidad``: DUA y orientaciones inclusivas (v1)."""
from __future__ import annotations

from textwrap import dedent

from ...ai.provider import LLMRequest
from ..contexto import ContextoGeneracion
from ._comun import SYSTEM_PROMPT, bloque_contexto_base


NOMBRE = "atencion_diversidad"
VERSION = "v1"


def build(ctx: ContextoGeneracion) -> LLMRequest:
    if ctx.es_adaptacion and ctx.tipo_adaptacion == "no_significativa":
        instruccion = dedent(
            """\
            ## Tu tarea

            Esta SA es una ADAPTACIÓN CURRICULAR NO SIGNIFICATIVA dirigida
            al alumno/a descrito. Redacta las ORIENTACIONES DE ATENCIÓN A
            LA DIVERSIDAD centradas EXCLUSIVAMENTE en lo que aplica a este
            alumno/a, partiendo del DUA. Sé concreto y realista.

            Estructura:
            - ``principios_dua``: 3-5 medidas DUA pensadas para que este
              alumno/a acceda al aprendizaje (representación, acción y
              expresión, implicación).
            - ``ajustes_no_significativos``: 4-6 ajustes específicos que se
              le aplican (apoyos visuales, tiempos extra, agrupamientos,
              materiales, andamiaje), SIN modificar criterios de evaluación.
            - ``ajustes_significativos``: deja la lista VACÍA (``[]``).
              Esta adaptación es NO significativa: no procede modificar
              criterios.

            Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

            ```json
            {
              "principios_dua": ["..."],
              "ajustes_no_significativos": ["..."],
              "ajustes_significativos": []
            }
            ```
            """
        ).strip()
    elif ctx.es_adaptacion and ctx.tipo_adaptacion == "significativa":
        instruccion = dedent(
            """\
            ## Tu tarea

            Esta SA es una ADAPTACIÓN CURRICULAR SIGNIFICATIVA dirigida al
            alumno/a descrito. Redacta las ORIENTACIONES DE ATENCIÓN A LA
            DIVERSIDAD centradas EXCLUSIVAMENTE en lo que aplica a este
            alumno/a, partiendo del DUA. Sé concreto y realista.

            Estructura:
            - ``principios_dua``: 3-5 medidas DUA pensadas para que este
              alumno/a acceda al aprendizaje.
            - ``ajustes_no_significativos``: deja la lista VACÍA (``[]``).
              Esta adaptación es significativa: los ajustes relevantes son
              modificaciones de criterios, no medidas de acceso.
            - ``ajustes_significativos``: 4-6 modificaciones aplicadas a
              este alumno/a, indicando qué se adapta (objetivos, criterios
              de evaluación, contenidos priorizados, evaluación
              alternativa) y por qué.

            Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

            ```json
            {
              "principios_dua": ["..."],
              "ajustes_no_significativos": [],
              "ajustes_significativos": ["..."]
            }
            ```
            """
        ).strip()
    else:
        instruccion = dedent(
            """\
            ## Tu tarea

            Redacta las ORIENTACIONES DE ATENCIÓN A LA DIVERSIDAD para la
            situación, partiendo del Diseño Universal para el Aprendizaje
            (DUA). Proporciona medidas concretas y realistas, no lugares
            comunes.

            Estructura:
            - ``principios_dua``: 3-5 medidas generales aplicables a toda la
              secuencia (múltiples formas de representación, acción y
              expresión, implicación).
            - ``ajustes_no_significativos``: 3-5 estrategias de refuerzo y
              ampliación sin modificar los criterios de evaluación (por
              ejemplo: apoyos visuales, tiempos extra, agrupamientos).
            - ``ajustes_significativos``: 2-4 propuestas para alumnado con
              necesidades específicas de apoyo educativo (NEAE) que sí
              modifican criterios, indicando qué se adapta.

            Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

            ```json
            {
              "principios_dua": ["..."],
              "ajustes_no_significativos": ["..."],
              "ajustes_significativos": ["..."]
            }
            ```
            """
        ).strip()

    user = "\n\n".join([bloque_contexto_base(ctx), instruccion])
    return LLMRequest(
        user=user,
        system=SYSTEM_PROMPT,
        temperature=0.5,
        response_format="json",
        metadata={"seccion": NOMBRE, "version": VERSION},
    )
