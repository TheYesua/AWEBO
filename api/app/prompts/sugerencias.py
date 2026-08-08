"""Prompt de sugerencia inicial de temáticas.

A diferencia de los módulos de :mod:`app.prompts.secciones`, esto **no es una
sección LOMLOE**: no forma parte de ``contenido`` ni aparece en
``ORDEN_SECCIONES``. Es un paso previo a la creación de la SA, pensado para
resolver el problema de la página en blanco: el docente describe su situación
en una frase y recibe varias temáticas entre las que elegir.

Consecuencias de no ser una sección:

* No recibe un :class:`ContextoGeneracion` (no hay SA todavía, ni currículo
  cargado). El contexto es lo poco que el docente haya escrito.
* Como el catálogo LOMLOE no está disponible aquí, el prompt prohíbe
  explícitamente citar códigos de competencias, criterios o saberes: sin
  catálogo delante, el modelo solo podría inventárselos. El anclaje curricular
  llega después, durante la generación de la SA propiamente dicha.
"""
from __future__ import annotations

from textwrap import dedent

from ..ai.provider import LLMRequest


NOMBRE = "sugerencias"
VERSION = "v1"

#: Número de propuestas por defecto. Suficiente para elegir sin abrumar.
NUM_PROPUESTAS_DEFECTO = 3

#: Cota superior. Más propuestas alargan la espera de una llamada síncrona y
#: empeoran la decisión en lugar de mejorarla.
NUM_PROPUESTAS_MAX = 5


SYSTEM_PROMPT = dedent(
    """\
    Eres un asesor didáctico experto en el currículo LOMLOE de España
    (Real Decreto 217/2022 y Orden EFP/754/2022 para Ceuta y Melilla).
    Ayudas a docentes de Educación Secundaria Obligatoria a encontrar el
    punto de partida de una Situación de Aprendizaje.

    Debes:
    - Proponer temáticas concretas, realizables en un aula real y adecuadas
      a la edad y al nivel del curso indicado.
    - Anclar cada propuesta en un contexto reconocible para el alumnado
      (un reto, un problema local, una necesidad real).
    - Redactar en un estilo profesional, claro y directo, sin lenguaje
      comercial ni ornamental.
    - Devolver EXCLUSIVAMENTE un objeto JSON válido, sin explicaciones
      fuera del JSON.

    NO debes:
    - Citar códigos de competencias específicas, criterios de evaluación ni
      saberes básicos. En esta fase no dispones del catálogo curricular y
      cualquier código que escribieras sería inventado. El anclaje al
      currículo se hace en un paso posterior.
    - Proponer temáticas que requieran medios inaccesibles para un centro
      público ordinario.
    """
).strip()


def build(
    *,
    curso: str,
    materia: str,
    contexto: str | None = None,
    idioma: str = "es",
    num_propuestas: int = NUM_PROPUESTAS_DEFECTO,
) -> LLMRequest:
    """Construye la petición de sugerencia de temáticas.

    :param curso: curso de ESO, p. ej. ``"3º ESO"``.
    :param materia: materia, p. ej. ``"Tecnología"``.
    :param contexto: texto libre del docente. Opcional: sin él, las
        propuestas se apoyan solo en curso y materia.
    :param idioma: código de idioma de redacción (``es``, ``en``, ``fr``, ``ar``).
    :param num_propuestas: cuántas temáticas devolver.
    """
    n = max(1, min(int(num_propuestas), NUM_PROPUESTAS_MAX))

    datos = [
        "## Datos de partida",
        f"- Curso: {curso}",
        f"- Materia: {materia}",
        f"- Idioma de redacción: {idioma}",
    ]
    if contexto:
        datos.append(f"- Lo que busca el docente: {contexto}")
    else:
        datos.append(
            "- El docente no ha dado más contexto: propón temáticas variadas "
            "entre sí, para que pueda escoger dirección."
        )

    instruccion = dedent(
        f"""\
        ## Tu tarea

        Propón {n} temáticas DISTINTAS entre sí para una Situación de
        Aprendizaje. Cada una debe poder desarrollarse después como SA
        completa, así que necesita tener recorrido suficiente.

        Para cada propuesta:

        - `titulo`: enunciado atractivo y concreto, de 3 a 10 palabras. Sirve
          tal cual como título de la SA.
        - `resumen`: 2 o 3 frases explicando de qué trata y por qué conecta
          con el alumnado de este curso.
        - `producto_final`: qué construye o entrega el alumnado al terminar.
        - `pregunta_guia`: una sola pregunta que enmarque el reto.

        Que las {n} propuestas exploren enfoques diferentes (por ejemplo:
        una centrada en un problema local, otra en un producto tangible,
        otra en un análisis o investigación). No repitas la misma idea con
        distintas palabras.

        Devuelve EXCLUSIVAMENTE un objeto JSON con este esquema:

        ```json
        {{
          "propuestas": [
            {{
              "titulo": "...",
              "resumen": "...",
              "producto_final": "...",
              "pregunta_guia": "..."
            }}
          ]
        }}
        ```
        """
    ).strip()

    return LLMRequest(
        user="\n".join(datos) + "\n\n" + instruccion,
        system=SYSTEM_PROMPT,
        # Más alta que en las secciones (0.5-0.6): aquí se busca variedad
        # entre propuestas, no precisión curricular.
        temperature=0.9,
        response_format="json",
        metadata={"prompt": NOMBRE, "version": VERSION},
    )
