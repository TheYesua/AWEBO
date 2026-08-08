"""Sección ``evaluacion``: instrumentos y rúbricas por criterio (v1)."""
from __future__ import annotations

from textwrap import dedent

from ...ai.provider import LLMRequest
from ..contexto import ContextoGeneracion
from ._comun import SYSTEM_PROMPT, bloque_contexto_base, bloque_curriculo


NOMBRE = "evaluacion"
VERSION = "v1"


def build(ctx: ContextoGeneracion) -> LLMRequest:
    instruccion = dedent(
        """\
        ## Tu tarea

        Diseña el PLAN DE EVALUACIÓN de la situación:

        - Para cada criterio de evaluación del listado que SE TRABAJE
          realmente, define una rúbrica de 4 niveles: iniciado (1),
          en_proceso (2), logrado (3), excelente (4). Cada nivel en una
          frase observable y distinguible.
        - Lista los instrumentos de evaluación utilizados (observación
          sistemática, producto final, rúbrica, diario, prueba, etc.).
        - Indica el momento (``inicial``, ``formativa`` o ``sumativa``) y
          el peso orientativo de cada instrumento (los pesos deben sumar
          100).

        Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

        ```json
        {
          "instrumentos": [
            {"nombre": "Rúbrica del producto final",
             "momento": "sumativa",
             "peso": 50}
          ],
          "rubricas": [
            {
              "criterio": "1.1",
              "niveles": {
                "iniciado": "...",
                "en_proceso": "...",
                "logrado": "...",
                "excelente": "..."
              }
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
        temperature=0.4,
        response_format="json",
        metadata={"seccion": NOMBRE, "version": VERSION},
    )
