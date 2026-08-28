"""La etapa entra en el currículo: sin ella, Bachillerato pisa la ESO.

Revision ID: d1a7b4e62c95
Revises: c9e4f2a10b73
Create Date: 2026-08-28

POR QUÉ
-------
El upsert de competencias casa por **`(comunidad, codigo, materia)`**, y esas
tres cosas coinciden entre etapas: «Matemáticas» existe en la ESO y en
Bachillerato, en la misma comunidad, y sus competencias específicas se numeran
`1`, `2`, `3`… en las dos. Cargar Bachillerato **sobrescribiría** las de la ESO
una por una, sin error y sin aviso: el seed las contaría como «actualizadas».

Y no lo arregla `cursos_aplicables`. Los criterios y los saberes sí lo llevan
en su clave —«1º ESO» y «1º Bachillerato» son distintos— pero las competencias
no, **y es a propósito**: son comunes a toda la etapa, así que el seed fusiona
sus cursos en vez de crear una fila por curso (`_union_cursos`). Meterlos en la
clave rompería esa fusión, que es correcta *dentro* de una etapa.

Lo que faltaba, entonces, es el eje que separa las dos: la etapa.

POR QUÉ EN LAS TRES TABLAS Y NO SOLO EN COMPETENCIA
----------------------------------------------------
La colisión solo se da en `competencia`, así que bastaría con añadirla ahí. Se
añade a las tres porque el campo no es solo una pieza de la clave: es **de qué
etapa es esta fila**, y esa pregunta tiene respuesta para un criterio y para un
saber igual que para una competencia. Tenerla en una sola obligaría a deducirla
de `cursos_aplicables` en las otras dos —analizando la cadena «1º ESO»—, que es
justo el tipo de dato derivado que acaba divergiendo.

QUÉ HACE CON LO QUE YA HAY
---------------------------
Todo lo cargado hoy es ESO: las cinco comunidades salen de decretos de
Educación Secundaria Obligatoria. Se rellena con `'ESO'` y **luego se quita el
`server_default`**, para que una inserción que olvide la etapa falle en vez de
colarse con un valor plausible. Es el mismo patrón que usó `a4c81e9d2f60` con
`comunidad`, y por el mismo motivo.
"""
from alembic import op
import sqlalchemy as sa


revision = "d1a7b4e62c95"
down_revision = "c9e4f2a10b73"
branch_labels = None
depends_on = None


_TABLAS = ("competencia", "criterio_evaluacion", "saber_basico")


def upgrade() -> None:
    for tabla in _TABLAS:
        # Con `server_default` para poder rellenar las filas que ya existen:
        # la columna es NOT NULL y sin un valor por defecto la propia adición
        # fallaría sobre una tabla con datos.
        op.add_column(
            tabla,
            sa.Column("etapa", sa.String(length=20), nullable=False,
                      server_default="ESO"),
        )
        # Y se retira acto seguido. Dejarlo permitiría que un extractor nuevo
        # olvidara la etapa y sus filas entraran como de la ESO en silencio —
        # exactamente el fallo que esta migración viene a impedir.
        op.alter_column(tabla, "etapa", server_default=None)

    # El índice de saberes ya filtraba por (comunidad, materia); la etapa entra
    # en las mismas consultas, así que se rehace con las tres.
    op.drop_index("ix_saber_comunidad_materia", table_name="saber_basico")
    op.create_index(
        "ix_saber_comunidad_etapa_materia",
        "saber_basico",
        ["comunidad", "etapa", "materia"],
    )


def downgrade() -> None:
    op.drop_index("ix_saber_comunidad_etapa_materia", table_name="saber_basico")
    op.create_index(
        "ix_saber_comunidad_materia", "saber_basico", ["comunidad", "materia"]
    )
    for tabla in _TABLAS:
        op.drop_column(tabla, "etapa")
