"""Sección ``descripcion``: descripción narrativa de la SA (v1)."""
from __future__ import annotations

from textwrap import dedent

from ...ai.provider import LLMRequest
from ..contexto import ContextoGeneracion
from ._comun import SYSTEM_PROMPT, bloque_contexto_base, bloque_curriculo


NOMBRE = "descripcion"
VERSION = "v1"


def build(ctx: ContextoGeneracion) -> LLMRequest:
    instruccion = dedent(
        """\
        ## Tu tarea

        Redacta la DESCRIPCIÓN DE LA SITUACIÓN DE APRENDIZAJE: un texto
        de 120-200 palabras que responda a:

        - ¿De qué trata la situación? (reto, pregunta guía o contexto real)
        - ¿Por qué es relevante para el alumnado de este curso?
        - ¿Qué producto final o evidencia se espera construir?
        - ¿Cómo se conecta con la materia y los aprendizajes previos?

        Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

        ```json
        {
          "texto": "párrafo único en prosa, sin listas",
          "producto_final": "nombre corto del entregable esperado",
          "pregunta_guia": "una sola pregunta que enmarque la situación"
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
        temperature=0.6,
        response_format="json",
        metadata={"seccion": NOMBRE, "version": VERSION},
    )
