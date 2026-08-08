"""Utilidades compartidas por todos los prompts de sección."""
from __future__ import annotations

from textwrap import dedent

from ...models import SituacionAprendizaje
from ..contexto import ContextoGeneracion


# Mensaje de sistema común a todas las secciones.
SYSTEM_PROMPT = dedent(
    """\
    Eres un asesor didáctico experto en el currículo LOMLOE de España
    (Real Decreto 217/2022 y Orden EFP/754/2022 para Ceuta y Melilla).
    Tu tarea es ayudar a un docente de Educación Secundaria Obligatoria
    a diseñar una Situación de Aprendizaje alineada con la normativa.

    Debes:
    - Ceñirte estrictamente a las competencias específicas, criterios de
      evaluación y saberes básicos que te proporcione el usuario.
    - Redactar en el idioma solicitado con un estilo profesional, claro
      y directo, sin lenguaje comercial ni ornamental.
    - Cuando se te pida JSON, devolver EXCLUSIVAMENTE un objeto JSON
      válido, sin explicaciones fuera del JSON.
    - No inventar códigos de competencias, criterios o saberes que no
      aparezcan en el contexto.
    """
).strip()


def bloque_contexto_base(ctx: ContextoGeneracion) -> str:
    """Renderiza la cabecera de contexto que precede a cada instrucción.

    Si ``ctx.es_adaptacion`` es verdadero, añade un bloque de
    INSTRUCCIONES DE ADAPTACIÓN para que la sección se genere ya
    adaptada al perfil del alumnado indicado.
    """
    partes: list[str] = [
        "## Datos de la situación de aprendizaje",
        f"- Título: {ctx.titulo}",
        f"- Materia: {ctx.materia}",
        f"- Curso: {ctx.curso}",
        # El NOMBRE, no el código. «Idioma de redacción: eu» obliga al modelo a
        # adivinar; «euskera» no deja lugar a dudas. Con `es`/`en` daba igual,
        # pero al añadir las lenguas cooficiales los códigos son menos obvios.
        f"- Idioma de redacción: {SituacionAprendizaje.IDIOMAS.get(ctx.idioma, ctx.idioma)}",
    ]
    if ctx.metodologia:
        partes.append(f"- Metodología preferida: {ctx.metodologia}")
    if ctx.num_sesiones:
        partes.append(f"- Número de sesiones: {ctx.num_sesiones}")
    if ctx.duracion_sesion_minutos:
        partes.append(f"- Duración por sesión: {ctx.duracion_sesion_minutos} minutos")
    if ctx.descripcion:
        partes.append(f"- Descripción breve del docente: {ctx.descripcion}")
    if ctx.perfil_aula:
        partes.append(f"- Perfil del aula: {ctx.perfil_aula}")
    if ctx.materiales_contexto:
        partes.append(f"- Materiales / contexto adicional: {ctx.materiales_contexto}")

    if ctx.es_adaptacion:
        partes.append("")
        partes.append(bloque_adaptacion(ctx))

    return "\n".join(partes)


def bloque_adaptacion(ctx: ContextoGeneracion) -> str:
    """Bloque que indica al LLM que debe ADAPTAR el contenido a un alumno/a."""
    if ctx.tipo_adaptacion == "significativa":
        regla = dedent(
            """\
            Tipo: ADAPTACIÓN CURRICULAR SIGNIFICATIVA (ACS).
            DEBES modificar lo necesario (objetivos, criterios de evaluación,
            contenidos, metodología, materiales, tiempos y evaluación) para
            que el alumno/a pueda alcanzar aprendizajes adecuados a su nivel
            de competencia curricular real, JUSTIFICANDO cada modificación.
            Reformula los objetivos, prioriza saberes esenciales y diseña
            instrumentos de evaluación alternativos cuando sea preciso.
            """
        ).strip()
    else:
        regla = dedent(
            """\
            Tipo: ADAPTACIÓN CURRICULAR NO SIGNIFICATIVA (ACNS).
            NO modifiques los objetivos, criterios de evaluación ni saberes
            básicos del currículo ordinario. Ajusta SOLO la metodología, los
            tiempos, los agrupamientos, los materiales y los apoyos para que
            el alumno/a pueda acceder al mismo aprendizaje.
            """
        ).strip()

    partes: list[str] = [
        "## INSTRUCCIONES DE ADAPTACIÓN CURRICULAR",
        regla,
        "",
        f"### Alumno/a destinatario\n{ctx.perfil_alumnado or '(no especificado)'}",
    ]
    if ctx.titulo_origen:
        partes.append(
            f"\n### SA de origen\nEsta es una adaptación de la SA «{ctx.titulo_origen}»."
        )
    if ctx.contenido_origen_resumen:
        partes.append(
            "\n### Contenido de la SA original (referencia)\n"
            + ctx.contenido_origen_resumen
        )
    partes.append(
        "\nIMPORTANTE: cada apartado que generes debe estar YA ADAPTADO "
        "al alumno/a indicado, no produzcas el mismo contenido que la SA "
        "original. Si es ACS, refleja explícitamente las modificaciones "
        "respecto al currículo ordinario."
    )
    return "\n".join(partes)


def bloque_curriculo(ctx: ContextoGeneracion, *, incluir_saberes: bool = True) -> str:
    """Serializa competencias, criterios y (opcionalmente) saberes."""
    lineas: list[str] = ["## Currículo aplicable (fuente: BOE)"]

    lineas.append("### Competencias específicas")
    if ctx.competencias:
        for c in ctx.competencias:
            descriptores = ", ".join(c["descriptores"]) if c["descriptores"] else "-"
            lineas.append(f"- {c['codigo']} [{descriptores}]: {c['descripcion']}")
    else:
        lineas.append("- (ninguna cargada)")

    lineas.append("")
    lineas.append("### Criterios de evaluación")
    if ctx.criterios:
        for cr in ctx.criterios:
            lineas.append(f"- {cr['codigo']} (→{cr['competencia']}): {cr['descripcion']}")
    else:
        lineas.append("- (ninguno cargado)")

    if incluir_saberes:
        lineas.append("")
        lineas.append("### Saberes básicos")
        if ctx.saberes:
            for s in ctx.saberes:
                lineas.append(f"- {s['codigo']} [{s['bloque']}]: {s['descripcion']}")
        else:
            lineas.append("- (ninguno cargado)")

    return "\n".join(lineas)
