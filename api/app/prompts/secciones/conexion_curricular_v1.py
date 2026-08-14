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
        - No inventes códigos, y NO LES CAMBIES EL FORMATO. Copia cada
          código EXACTAMENTE como aparece en el listado de arriba: si el
          listado dice "1", escribe "1" y no "CE1"; si dice "CE1", escribe
          "CE1". Añadir o quitar un prefijo hace que el código deje de
          casar con el catálogo aunque el contenido sea correcto.
        - Prioriza cobertura realista: 2-4 competencias, 3-6 criterios y
          4-8 saberes. No listes todo si la situación no los trabaja.
        - Cada criterio debe apuntar a UNA competencia del listado por su
          código.

        Devuelve EXCLUSIVAMENTE un objeto JSON con el esquema:

        ```json
        {
          "competencias": [
            {"codigo": "<código tal cual del listado>",
             "justificacion": "texto breve (1 frase)"}
          ],
          "criterios": [
            {"codigo": "<código tal cual>",
             "competencia": "<código de competencia tal cual>",
             "justificacion": "..."}
          ],
          "saberes": [
            {"codigo": "<código tal cual>", "justificacion": "..."}
          ]
        }
        ```
        """
    # POR QUÉ EL EJEMPLO NO LLEVA CÓDIGOS DE VERDAD
    # ----------------------------------------------
    # Llevaba "CE1", "1.1" y "A.3", que son los del currículo de Ceuta. Al
    # cargar Cataluña —cuyas competencias se numeran "1".."9", sin prefijo— la
    # misma situación generada dos veces salió con dos convenciones distintas:
    # la versión en catalán citó "1, 2, 5, 7" siguiendo el dato, y la española
    # "CE1, CE2…" siguiendo el ejemplo. El prefijo inventado **no casa con el
    # catálogo**, así que `flask curriculo enlazar` no puede anclar esa SdA.
    #
    # Un ejemplo con valores concretos enseña dos cosas a la vez: la forma del
    # JSON y el formato de los códigos. Lo segundo no queríamos enseñarlo, y no
    # se vio hasta que hubo una segunda comunidad con otra convención.
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
