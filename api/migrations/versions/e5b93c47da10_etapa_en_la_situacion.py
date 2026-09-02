"""La etapa entra en la situación de aprendizaje.

Revision ID: e5b93c47da10
Revises: d1a7b4e62c95
Create Date: 2026-09-02

POR QUÉ
-------
Con Bachillerato cargado, el buscador tiene que poder responder «enséñame mis
SdA de Bachillerato». Hoy no puede: la situación guarda `curso`, `materia` y
`comunidad_autonoma`, y la etapa no está en ninguna parte.

Se podría **deducir** del curso, porque la cadena la lleva dentro —«1º ESO»,
«2º Bachillerato»—. No se hace, y es la misma razón por la que
`d1a7b4e62c95` puso la etapa en las tres tablas del currículo en vez de en la
única que la necesitaba: un dato deducido de una cadena de texto es un dato que
acaba divergiendo. Basta con que mañana entre «1º Bachillerato (LOE)», o un
ciclo de FP, o una comunidad que escriba «1.º» con punto, para que el filtro
empiece a mentir sin fallar.

Y hay una razón de consulta además de la de modelo: filtrar por etapa deducida
significa un `LIKE '%Bachillerato%'` sobre `curso` en cada búsqueda, que no usa
índice. Una columna con su índice sí.

QUÉ HACE CON LO QUE YA HAY
---------------------------
Todas las SdA existentes son de la ESO —hasta el 02/09/2026 no había ninguna
otra etapa cargada en el catálogo—, pero **no se rellenan con una constante**:
se derivan del propio `curso` de cada fila. Cuesta lo mismo y deja de ser una
suposición para pasar a ser un dato leído.

Después se retira el `server_default`, como en `d1a7b4e62c95` y por lo mismo:
un defecto que se queda en el esquema permite que una inserción que olvide la
etapa entre como ESO sin que nada falle, que es justo lo que la columna viene a
impedir.

La derivación busca «Bachillerato» dentro del curso. Es deliberadamente laxa
—vale para «1º Bachillerato» y para cualquier variante que apareciera— porque
aquí solo se ejecuta una vez, sobre datos que ya existen, y errar hacia la ESO
en una fila rara es preferible a que la migración se plante.
"""
from alembic import op
import sqlalchemy as sa


revision = "e5b93c47da10"
down_revision = "d1a7b4e62c95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "situacion_aprendizaje",
        sa.Column("etapa", sa.String(length=20), nullable=False,
                  server_default="ESO"),
    )
    # El backfill, leyendo el curso en vez de suponer la etapa.
    op.execute(
        """
        UPDATE situacion_aprendizaje
           SET etapa = 'Bachillerato'
         WHERE curso ILIKE '%Bachillerato%'
        """
    )
    op.alter_column("situacion_aprendizaje", "etapa", server_default=None)
    # El buscador filtra por etapa junto al usuario, que es como se listan
    # siempre las situaciones: nadie busca en las de otro.
    op.create_index(
        "ix_situacion_usuario_etapa",
        "situacion_aprendizaje",
        ["id_usuario", "etapa"],
    )


def downgrade() -> None:
    op.drop_index("ix_situacion_usuario_etapa",
                  table_name="situacion_aprendizaje")
    op.drop_column("situacion_aprendizaje", "etapa")
