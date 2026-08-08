"""Sección ``conexion_curricular``: mapa competencias↔criterios↔saberes (v1)."""
from __future__ import annotations

from textwrap import dedent

from ...ai.provider import LLMRequest
from ..contexto import ContextoGeneracion
from ._comun import SYSTEM_PROMPT, bloque_contexto_base, bloque_curriculo


NOMBRE = "conexion_curricular"
VERSION = "v1"


def build(ctx: ContextoGeneracion) -> LLMRequest:
    instruccion = dedent(
        """\
        ## Tu tarea

        Selecciona las competencias específicas, criterios de evaluación
        y saberes básicos QUE REALMENTE se trabajan en esta situación,
        justificando brevemente la elección.

        Reglas:
        - No inventes códigos. Usa únicamente los códigos del listado
          anterior tal y como aparecen ("CE1", "1.1", "A.3", etc.).
        - Prioriza cobertura realista: 2-4 competencias, 3-6 criterios y
          4-8 saberes. No listes todo si la situación no los trabaja.
        - Cada criterio debe apuntar a UNA competencia del listado por su
          código.

        Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

        ```json
        {
          "competencias": [
            {"codigo": "CE1", "justificacion": "texto breve (1 frase)"}
          ],
          "criterios": [
            {"codigo": "1.1", "competencia": "CE1", "justificacion": "..."}
          ],
          "saberes": [
            {"codigo": "A.3", "justificacion": "..."}
          ]
        }
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
        temperature=0.3,  # queremos fidelidad al currículo, no creatividad
        response_format="json",
        metadata={"seccion": NOMBRE, "version": VERSION},
    )
