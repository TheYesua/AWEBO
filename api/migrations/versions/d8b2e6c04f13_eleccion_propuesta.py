"""eleccion_propuesta: registro de qué alternativa elige el docente

Tabla nueva. No hace falta para que la funcionalidad de doble propuesta
funcione, pero sin ella la elección no deja rastro y no hay forma de saber qué
prompt produce mejores redacciones. Ese dato es imposible de reconstruir
después, así que la tabla se crea a la vez que la funcionalidad.

Las dos claves ajenas van con ``SET NULL`` y no con ``CASCADE``. Un registro no
contiene contenido del docente —solo la sección, las versiones de prompt que
competían y el proveedor y modelo de cada una—, así que es señal anónima que
conviene conservar. Con ``CASCADE`` bastaría con borrar una situación para
perder lo que enseñó.

Revision ID: d8b2e6c04f13
Revises: c3f7a91d5e42
Create Date: 2026-08-03 21:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d8b2e6c04f13"
down_revision = "c3f7a91d5e42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "eleccion_propuesta",
        sa.Column("id_eleccion", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_situacion", sa.Integer(), nullable=True),
        sa.Column("id_usuario", sa.Integer(), nullable=True),
        sa.Column("seccion", sa.String(length=40), nullable=False),
        sa.Column("variante_elegida", sa.String(length=20), nullable=False),
        sa.Column("variante_descartada", sa.String(length=20), nullable=False),
        sa.Column("posicion_elegida", sa.String(length=15), nullable=False),
        sa.Column(
            "meta_elegida",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "meta_descartada",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "fecha",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["id_situacion"],
            ["situacion_aprendizaje.id_situacion"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["id_usuario"], ["usuario.id_usuario"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id_eleccion"),
    )
    with op.batch_alter_table("eleccion_propuesta") as b:
        b.create_index("ix_eleccion_propuesta_id_situacion", ["id_situacion"])
        b.create_index("ix_eleccion_seccion_variante", ["seccion", "variante_elegida"])
        b.create_index("ix_eleccion_usuario", ["id_usuario"])


def downgrade():
    with op.batch_alter_table("eleccion_propuesta") as b:
        b.drop_index("ix_eleccion_usuario")
        b.drop_index("ix_eleccion_seccion_variante")
        b.drop_index("ix_eleccion_propuesta_id_situacion")
    op.drop_table("eleccion_propuesta")
