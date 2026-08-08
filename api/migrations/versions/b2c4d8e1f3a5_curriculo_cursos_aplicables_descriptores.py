"""curriculo: curso (varchar) -> cursos_aplicables (jsonb), añadir descriptores

Sustituye el campo ``curso`` por el array JSONB ``cursos_aplicables`` en las
tablas ``competencia``, ``criterio_evaluacion`` y ``saber_basico``. Añade
``descriptores`` (JSONB) en ``competencia`` para almacenar los códigos del
perfil de salida (CCL3, STEM2, ...). Añade ``codigo`` (varchar) en
``saber_basico`` y amplía el ancho de ``bloque``.

Esta migración asume que las tablas curriculares NO contienen datos en este
punto del desarrollo (todavía no se ha ejecutado ``flask seed curriculo``).
Si hubiese datos, se preservarían en una columna nueva derivando
``cursos_aplicables = [curso]`` antes del drop.

Revision ID: b2c4d8e1f3a5
Revises: a166a5664bf1
Create Date: 2026-05-11 16:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b2c4d8e1f3a5"
down_revision = "a166a5664bf1"
branch_labels = None
depends_on = None


JSONB_LIST_DEFAULT = sa.text("'[]'::jsonb")


def upgrade():
    # ---- competencia ----------------------------------------------------
    with op.batch_alter_table("competencia") as b:
        b.drop_index("ix_competencia_materia_curso")
        b.add_column(
            sa.Column(
                "cursos_aplicables",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=JSONB_LIST_DEFAULT,
            )
        )
        b.add_column(
            sa.Column(
                "descriptores",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=JSONB_LIST_DEFAULT,
            )
        )
        b.drop_column("curso")
        b.create_index("ix_competencia_materia", ["materia"], unique=False)
    # Quitamos el server_default ya aplicado para que el modelo de aplicación
    # controle el valor por defecto en filas nuevas.
    op.alter_column("competencia", "cursos_aplicables", server_default=None)
    op.alter_column("competencia", "descriptores", server_default=None)

    # ---- criterio_evaluacion -------------------------------------------
    with op.batch_alter_table("criterio_evaluacion") as b:
        b.drop_index("ix_criterio_materia_curso")
        b.add_column(
            sa.Column(
                "cursos_aplicables",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=JSONB_LIST_DEFAULT,
            )
        )
        b.drop_column("curso")
        b.create_index("ix_criterio_materia", ["materia"], unique=False)
    op.alter_column("criterio_evaluacion", "cursos_aplicables", server_default=None)

    # ---- saber_basico ---------------------------------------------------
    with op.batch_alter_table("saber_basico") as b:
        b.drop_index("ix_saber_materia_curso")
        b.add_column(
            sa.Column(
                "codigo",
                sa.String(length=20),
                nullable=False,
                server_default="",
            )
        )
        b.add_column(
            sa.Column(
                "cursos_aplicables",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=JSONB_LIST_DEFAULT,
            )
        )
        b.alter_column(
            "bloque",
            existing_type=sa.String(length=100),
            type_=sa.String(length=200),
            existing_nullable=False,
        )
        b.drop_column("curso")
        b.create_index("ix_saber_materia", ["materia"], unique=False)
    op.alter_column("saber_basico", "codigo", server_default=None)
    op.alter_column("saber_basico", "cursos_aplicables", server_default=None)


def downgrade():
    # ---- saber_basico ---------------------------------------------------
    with op.batch_alter_table("saber_basico") as b:
        b.drop_index("ix_saber_materia")
        b.add_column(
            sa.Column(
                "curso", sa.String(length=20), nullable=False, server_default=""
            )
        )
        b.alter_column(
            "bloque",
            existing_type=sa.String(length=200),
            type_=sa.String(length=100),
            existing_nullable=False,
        )
        b.drop_column("cursos_aplicables")
        b.drop_column("codigo")
        b.create_index("ix_saber_materia_curso", ["materia", "curso"], unique=False)

    # ---- criterio_evaluacion -------------------------------------------
    with op.batch_alter_table("criterio_evaluacion") as b:
        b.drop_index("ix_criterio_materia")
        b.add_column(
            sa.Column(
                "curso", sa.String(length=20), nullable=False, server_default=""
            )
        )
        b.drop_column("cursos_aplicables")
        b.create_index(
            "ix_criterio_materia_curso", ["materia", "curso"], unique=False
        )

    # ---- competencia ----------------------------------------------------
    with op.batch_alter_table("competencia") as b:
        b.drop_index("ix_competencia_materia")
        b.add_column(
            sa.Column("curso", sa.String(length=20), nullable=True)
        )
        b.drop_column("descriptores")
        b.drop_column("cursos_aplicables")
        b.create_index(
            "ix_competencia_materia_curso", ["materia", "curso"], unique=False
        )
