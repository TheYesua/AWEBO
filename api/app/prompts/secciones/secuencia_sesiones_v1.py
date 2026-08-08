"""Sección ``secuencia_sesiones``: planificación sesión a sesión (v1)."""
from __future__ import annotations

from textwrap import dedent

from ...ai.provider import LLMRequest
from ..contexto import ContextoGeneracion
from ._comun import SYSTEM_PROMPT, bloque_contexto_base, bloque_curriculo


NOMBRE = "secuencia_sesiones"
VERSION = "v1"


def build(ctx: ContextoGeneracion) -> LLMRequest:
    num = ctx.num_sesiones or 6
    duracion = ctx.duracion_sesion_minutos or 55

    instruccion = dedent(
        f"""\
        ## Tu tarea

        Planifica la SECUENCIA DE SESIONES ({num} sesiones de
        {duracion} minutos aproximadamente cada una). La secuencia debe
        seguir una progresión pedagógica coherente: activación → desarrollo
        → cierre/transferencia.

        Para cada sesión indica:
        - Un título breve.
        - La fase pedagógica (``apertura`` | ``desarrollo`` | ``cierre``).
        - El tiempo estimado en minutos.
        - 2-4 actividades con una descripción operativa (qué hace el
          alumnado, qué hace el docente).
        - Los recursos/materiales necesarios.
        - Los criterios de evaluación del listado trabajados (códigos).

        Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

        ```json
        {{
          "sesiones": [
            {{
              "numero": 1,
              "titulo": "...",
              "fase": "apertura",
              "duracion_minutos": {duracion},
              "actividades": [
                {{"descripcion": "...", "agrupamiento": "individual | parejas | pequeño_grupo | gran_grupo"}}
              ],
              "recursos": ["..."],
              "criterios": ["1.1", "2.3"]
            }}
          ]
        }}
        ```
        """
    ).strip()

    user = "\n\n".join(
        [
            bloque_contexto_base(ctx),
            bloque_curriculo(ctx, incluir_saberes=True),
            instruccion,
        ]
    )
    return LLMRequest(
        user=user,
        system=SYSTEM_PROMPT,
        temperature=0.6,
        response_format="json",
        metadata={"seccion": NOMBRE, "version": VERSION},
    )
