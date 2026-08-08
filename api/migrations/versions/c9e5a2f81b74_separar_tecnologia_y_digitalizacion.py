"""Separa Tecnología y Digitalización de Tecnología.

Revision ID: c9e5a2f81b74
Revises: a71f4d9c2b06
Create Date: 2026-08-07

El BOE tiene dos materias distintas —Tecnología y Digitalización, de 2.º y
3.º, y Tecnología, de opción en 4.º— con siete y seis competencias específicas
respectivamente y textos que no se parecen. Los perfiles del extractor las
mapeaban a una sola etiqueta, "Tecnología".

Eso no era solo una simplificación de nombre. ``seed_curriculo`` identifica las
competencias por ``(codigo, materia)``, así que al cargar los ficheros por
orden alfabético la CE1 de 4.º **sobrescribía la descripción** de la CE1 de
2.º-3.º, y ``cursos_aplicables`` se fusionaba en 2.º-4.º. En la base de datos
quedaban siete competencias con la mitad de los textos del curso equivocado.

Esta migración deshace ese estropicio. No inventa datos: reetiqueta y
reconecta lo que hay, y deja las descripciones para que las corrija el
siguiente ``flask seed curriculo``, que es quien tiene la fuente.

**Hay que ejecutar el seed después de migrar.** Solo con la migración, las
descripciones siguen siendo las mezcladas.
"""
from alembic import op
import sqlalchemy as sa


revision = "c9e5a2f81b74"
down_revision = "a71f4d9c2b06"
branch_labels = None
depends_on = None


VIEJA = "Tecnología"
NUEVA = "Tecnología y Digitalización"
CUARTO = "4º ESO"


def upgrade() -> None:
    conexion = op.get_bind()

    # ------------------------------------------------------------------
    # 1) Criterios y saberes: se reetiquetan por curso.
    # ------------------------------------------------------------------
    # Estas filas nunca se fusionaron —su clave incluye cursos_aplicables— así
    # que basta con mirar en qué curso están. Las de 4.º se quedan como
    # Tecnología; el resto pasa a ser Tecnología y Digitalización.
    for tabla in ("criterio_evaluacion", "saber_basico"):
        conexion.execute(
            sa.text(
                f"""
                UPDATE {tabla}
                   SET materia = :nueva
                 WHERE materia = :vieja
                   AND NOT (cursos_aplicables @> CAST(:cuarto AS jsonb))
                """
            ),
            {"nueva": NUEVA, "vieja": VIEJA, "cuarto": f'["{CUARTO}"]'},
        )

    # ------------------------------------------------------------------
    # 2) Competencias: duplicar antes de repartir.
    # ------------------------------------------------------------------
    # Aquí sí hubo fusión, así que no se puede reetiquetar: hacen falta dos
    # juegos donde había uno. Se copian todas las de Tecnología a la materia
    # nueva; el seed posterior corregirá las descripciones de cada juego.
    conexion.execute(
        sa.text(
            """
            INSERT INTO competencia
                (codigo, tipo, materia, cursos_aplicables, descriptores, descripcion)
            SELECT codigo, tipo, :nueva, CAST(:cursos AS jsonb), descriptores, descripcion
              FROM competencia
             WHERE materia = :vieja
            """
        ),
        {"nueva": NUEVA, "vieja": VIEJA, "cursos": '["2º ESO", "3º ESO"]'},
    )

    # Los criterios que acaban de cambiar de materia siguen apuntando a la
    # competencia vieja. Se reconectan a su copia, emparejando por código.
    conexion.execute(
        sa.text(
            """
            UPDATE criterio_evaluacion AS cr
               SET id_competencia = nueva.id_competencia
              FROM competencia AS nueva,
                   competencia AS vieja
             WHERE cr.materia = :nueva
               AND cr.id_competencia = vieja.id_competencia
               AND vieja.materia = :vieja
               AND nueva.materia = :nueva
               AND nueva.codigo = vieja.codigo
            """
        ),
        {"nueva": NUEVA, "vieja": VIEJA},
    )

    # Las que se quedan como Tecnología son ya solo de cuarto.
    conexion.execute(
        sa.text(
            "UPDATE competencia SET cursos_aplicables = CAST(:cursos AS jsonb) "
            "WHERE materia = :vieja"
        ),
        {"vieja": VIEJA, "cursos": f'["{CUARTO}"]'},
    )

    # ------------------------------------------------------------------
    # 3) Fantasmas.
    # ------------------------------------------------------------------
    # Tecnología y Digitalización tiene siete competencias y Tecnología seis,
    # así que la CE7 se queda sin criterios y sin razón de existir en 4.º. Se
    # borra solo si de verdad no la referencia nadie: una situación de
    # aprendizaje ya creada pudo haberla seleccionado, y perder esa referencia
    # sería peor que dejar una fila de más.
    conexion.execute(
        sa.text(
            """
            DELETE FROM competencia AS c
             WHERE c.materia = :vieja
               AND NOT EXISTS (SELECT 1 FROM criterio_evaluacion cr
                                WHERE cr.id_competencia = c.id_competencia)
               AND NOT EXISTS (SELECT 1 FROM situacion_competencia sc
                                WHERE sc.id_competencia = c.id_competencia)
            """
        ),
        {"vieja": VIEJA},
    )

    # ------------------------------------------------------------------
    # 4) Situaciones de aprendizaje ya creadas.
    # ------------------------------------------------------------------
    # Una SA de "Tecnología · 2º ESO" dejaría de tener currículo al que
    # anclarse, y el formulario la marcaría como combinación inválida. Se
    # reetiqueta con la materia que de verdad cursaba.
    conexion.execute(
        sa.text(
            """
            UPDATE situacion_aprendizaje
               SET materia = :nueva
             WHERE materia = :vieja
               AND curso <> :cuarto
            """
        ),
        {"nueva": NUEVA, "vieja": VIEJA, "cuarto": CUARTO},
    )


def downgrade() -> None:
    """Vuelve a fusionar ambas materias bajo la etiqueta "Tecnología".

    Restaura el estado anterior, incluida su ambigüedad: las competencias
    duplicadas se eliminan y los criterios vuelven a colgar de las originales.
    Deshacer un arreglo de datos no puede recuperar lo que el arreglo corrigió,
    solo devolver la forma.
    """
    conexion = op.get_bind()

    conexion.execute(
        sa.text(
            "UPDATE situacion_aprendizaje SET materia = :vieja WHERE materia = :nueva"
        ),
        {"vieja": VIEJA, "nueva": NUEVA},
    )

    # Los criterios vuelven a la competencia homónima de Tecnología. Si ya no
    # existe (la borramos por fantasma), se queda donde está: es preferible a
    # dejar la clave ajena colgando.
    conexion.execute(
        sa.text(
            """
            UPDATE criterio_evaluacion AS cr
               SET id_competencia = vieja.id_competencia
              FROM competencia AS nueva,
                   competencia AS vieja
             WHERE cr.materia = :nueva
               AND cr.id_competencia = nueva.id_competencia
               AND nueva.materia = :nueva
               AND vieja.materia = :vieja
               AND vieja.codigo = nueva.codigo
            """
        ),
        {"nueva": NUEVA, "vieja": VIEJA},
    )

    conexion.execute(
        sa.text(
            """
            DELETE FROM competencia AS c
             WHERE c.materia = :nueva
               AND NOT EXISTS (SELECT 1 FROM criterio_evaluacion cr
                                WHERE cr.id_competencia = c.id_competencia)
               AND NOT EXISTS (SELECT 1 FROM situacion_competencia sc
                                WHERE sc.id_competencia = c.id_competencia)
            """
        ),
        {"nueva": NUEVA},
    )

    for tabla in ("criterio_evaluacion", "saber_basico", "competencia"):
        conexion.execute(
            sa.text(f"UPDATE {tabla} SET materia = :vieja WHERE materia = :nueva"),
            {"vieja": VIEJA, "nueva": NUEVA},
        )
