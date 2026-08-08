"""Sección ``objetivos``: objetivos didácticos de la SA (v1)."""
from __future__ import annotations

from textwrap import dedent

from ...ai.provider import LLMRequest
from ..contexto import ContextoGeneracion
from ._comun import SYSTEM_PROMPT, bloque_contexto_base, bloque_curriculo


NOMBRE = "objetivos"
VERSION = "v1"


def build(ctx: ContextoGeneracion) -> LLMRequest:
    instruccion = dedent(
        """\
        ## Tu tarea

        Redacta los OBJETIVOS DIDÁCTICOS de la situación (entre 4 y 7).
        Cada objetivo debe:

        - Empezar con un verbo en infinitivo observable (analizar, diseñar,
          comparar, producir, argumentar, etc. NO "conocer" o "aprender").
        - Estar formulado en positivo y ser evaluable.
        - Vincularse explícitamente a al menos una competencia específica
          del listado por su código (CE1, CE2...).

        Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

        ```json
        {
          "objetivos": [
            {
              "texto": "Analizar ... ",
              "competencias": ["CE1", "CE3"]
            }
          ]
        }
        ```
        """
    ).strip()

    user = "\n\n".join(
        [
            bloque_contexto_base(ctx),
            bloque_curriculo(ctx, incluir_saberes=False),
            instruccion,
        ]
    )
    return LLMRequest(
        user=user,
        system=SYSTEM_PROMPT,
        temperature=0.5,
        response_format="json",
        metadata={"seccion": NOMBRE, "version": VERSION},
    )
