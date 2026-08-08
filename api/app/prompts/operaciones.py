"""Operaciones sobre un bloque ya generado.

A diferencia de :mod:`app.prompts.secciones`, que **genera** contenido a partir
del currículo, aquí se **transforma** contenido que ya existe. La entrada es el
JSON de una sección y la salida debe ser ese mismo JSON con el texto cambiado.

Son cuatro. Tres **sustituyen** el contenido —resumir, expandir, traducir— y
la cuarta, ``alternativa``, deja una segunda redacción **junto a** la actual
para que el docente elija entre las dos.

La regla que gobierna a todas: **no se toca la forma, solo el texto**. El frontend pinta cada sección con un renderizador que espera unas
claves concretas (`objetivos`, `sesiones`, `instrumentos`…). Si una operación
devuelve otra estructura, la sección deja de renderizarse y acaba en el volcado
JSON. Por eso el esquema de salida no se describe en abstracto: se le enseña al
modelo el JSON real que debe devolver con el texto ya transformado.

Códigos curriculares
--------------------
Los códigos de competencias, criterios y saberes (``CE1``, ``1.1``, ``A.3``)
**no se tocan en ninguna operación**, tampoco al traducir ni al proponer una
alternativa: identifican apartados del Real Decreto y traducirlos o
reescribirlos los desconecta de la norma. Es la misma razón por la que el
catálogo LOMLOE no se traduce nunca.
"""
from __future__ import annotations

import json
from textwrap import dedent

from ..models import SituacionAprendizaje

from ..ai.provider import LLMRequest


RESUMIR = "resumir"
EXPANDIR = "expandir"
TRADUCIR = "traducir"

#: Genera una redacción distinta del mismo contenido, para que el docente
#: elija. No transforma el texto en una dirección concreta como las otras
#: tres: busca **otra manera de decir lo mismo**.
ALTERNATIVA = "alternativa"

OPERACIONES = (RESUMIR, EXPANDIR, TRADUCIR, ALTERNATIVA)

VERSION = "v1"

#: Secciones sobre las que cada operación tiene sentido.
#:
#: ``conexion_curricular`` queda fuera de las cuatro: es una tabla de códigos
#: con una justificación de una línea. Resumirla la vacía de contenido,
#: expandirla invita a inventar, traducirla rompe el anclaje normativo y
#: ofrecer «otra versión» de unos criterios oficiales no significa nada.
SECCIONES_APLICABLES: dict[str, frozenset[str]] = {
    RESUMIR: frozenset(
        {"descripcion", "objetivos", "secuencia_sesiones", "evaluacion",
         "atencion_diversidad"}
    ),
    EXPANDIR: frozenset(
        {"descripcion", "objetivos", "secuencia_sesiones", "evaluacion",
         "atencion_diversidad"}
    ),
    TRADUCIR: frozenset(
        {"descripcion", "objetivos", "secuencia_sesiones", "evaluacion",
         "atencion_diversidad"}
    ),
    # Misma lista que las anteriores, y por el mismo motivo: la conexión
    # curricular es una tabla de códigos del Real Decreto. Ofrecer «otra
    # versión» de unos criterios de evaluación no tiene sentido — o son los que
    # marca la norma o no lo son.
    ALTERNATIVA: frozenset(
        {"descripcion", "objetivos", "secuencia_sesiones", "evaluacion",
         "atencion_diversidad"}
    ),
}

#: Alias de la definición canónica del modelo. Antes era una copia, y una copia
#: de una lista de idiomas es una forma segura de que «traducir a euskera»
#: acabe diciéndole al modelo «traducir a eu».
IDIOMAS = SituacionAprendizaje.IDIOMAS


SYSTEM_PROMPT = dedent(
    """\
    Eres un asesor didáctico experto en el currículo LOMLOE de España.
    Recibes un fragmento de una Situación de Aprendizaje en formato JSON y
    debes devolverlo transformado según se te indique.

    Reglas que se aplican SIEMPRE:
    - Devuelve EXCLUSIVAMENTE un objeto JSON válido, sin texto alrededor.
    - Conserva EXACTAMENTE la misma estructura: las mismas claves, anidadas
      igual, y las listas con el mismo número de elementos salvo que se te
      pida lo contrario de forma explícita.
    - NO modifiques los códigos curriculares (por ejemplo "CE1", "1.1",
      "A.3"). Identifican apartados del Real Decreto: alterarlos o
      traducirlos los desconecta de la norma.
    - NO añadas información que no estuviera en el fragmento original.
    """
).strip()


def _instruccion(operacion: str, idioma: str) -> str:
    if operacion == RESUMIR:
        return dedent(
            """\
            ## Tu tarea

            RESUME el contenido. Cada texto debe quedar en torno a la mitad de
            su longitud, conservando lo esencial: qué se hace, para qué y con
            qué se evalúa.

            - No elimines elementos de las listas: resume cada uno.
            - Mantén los códigos curriculares intactos.
            - Prioriza cortar adjetivos y rodeos antes que información.
            """
        ).strip()

    if operacion == EXPANDIR:
        return dedent(
            """\
            ## Tu tarea

            DESARROLLA el contenido. Cada texto debe ganar concreción práctica:
            cómo se lleva al aula, con qué agrupamientos, con qué materiales,
            qué hace el alumnado paso a paso.

            - No añadas elementos nuevos a las listas: desarrolla los que hay.
            - Mantén los códigos curriculares intactos.
            - Nada de relleno: si no aportas concreción útil, deja el texto
              como estaba.
            """
        ).strip()

    if operacion == ALTERNATIVA:
        return dedent(
            """\
            ## Tu tarea

            Reescribe el contenido de OTRA MANERA. El docente va a ver las dos
            versiones una junto a otra y quedarse con la que prefiera, así que
            la tuya tiene que ser una alternativa real, no una variación
            cosmética.

            - Cambia el enfoque, el orden del discurso o los ejemplos.
            - Mantén el mismo alcance: ni más contenido ni menos. Para eso
              están «resumir» y «desarrollar».
            - Mantén los códigos curriculares intactos y las mismas
              vinculaciones: si un objetivo apuntaba a CE1 y CE3, sigue
              apuntando a CE1 y CE3.
            - Si la versión actual ya es buena, no la empeores por ser
              distinto: busca otra igual de válida.
            """
        ).strip()

    nombre = IDIOMAS.get(idioma, idioma)
    return dedent(
        f"""\
        ## Tu tarea

        TRADUCE al {nombre} todos los textos del fragmento.

        - Traduce solo el contenido redactado.
        - NO traduzcas los códigos curriculares ("CE1", "1.1", "A.3"): son
          identificadores del Real Decreto y deben quedar tal cual.
        - Usa la terminología didáctica propia del {nombre}, no una
          traducción literal.
        """
    ).strip()


def build(
    *,
    operacion: str,
    seccion: str,
    contenido: dict,
    idioma: str = "es",
) -> LLMRequest:
    """Construye la petición de transformación de un bloque.

    :param operacion: ``resumir``, ``expandir``, ``traducir`` o ``alternativa``.
    :param seccion: clave de la sección, solo para trazabilidad.
    :param contenido: JSON actual de la sección, sin ``_meta``.
    :param idioma: idioma destino; solo se usa al traducir.
    """
    if operacion not in OPERACIONES:
        raise ValueError(f"Operación no soportada: {operacion!r}")

    # El JSON real, no una descripción del esquema: es la forma más fiable de
    # que la respuesta conserve la estructura, porque el modelo ve exactamente
    # lo que tiene que devolver.
    fragmento = json.dumps(contenido, ensure_ascii=False, indent=2)

    user = "\n\n".join(
        [
            f"## Fragmento actual (sección «{seccion}»)\n\n```json\n{fragmento}\n```",
            _instruccion(operacion, idioma),
        ]
    )

    return LLMRequest(
        user=user,
        system=SYSTEM_PROMPT,
        # Baja en resumir, expandir y traducir: no se busca creatividad sino
        # una transformación fiel de un texto que el docente ya dio por bueno.
        # Más alta al pedir una alternativa: con 0.3 saldría casi el mismo
        # texto y la elección no tendría objeto.
        temperature=0.85 if operacion == ALTERNATIVA else 0.3,
        response_format="json",
        metadata={"operacion": operacion, "seccion": seccion, "version": VERSION},
    )


def aplicable(operacion: str, seccion: str) -> bool:
    """¿Tiene sentido esta operación sobre esta sección?"""
    return seccion in SECCIONES_APLICABLES.get(operacion, frozenset())
