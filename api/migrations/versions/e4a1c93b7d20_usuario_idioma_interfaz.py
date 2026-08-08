"""usuario: idioma de la interfaz

Añade ``idioma_interfaz``, nullable: NULL significa «deducirlo del navegador»,
que es lo que hacía la aplicación hasta ahora (mostrarlo todo en castellano)
y por tanto el valor correcto para las cuentas existentes.

Va en el perfil y no en una cookie —al contrario que el tema— porque el idioma
es propiedad de la persona, no del dispositivo.

Revision ID: e4a1c93b7d20
Revises: d8b2e6c04f13
Create Date: 2026-08-03 22:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "e4a1c93b7d20"
down_revision = "d8b2e6c04f13"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuario") as b:
        b.add_column(sa.Column("idioma_interfaz", sa.String(length=5), nullable=True))


def downgrade():
    with op.batch_alter_table("usuario") as b:
        b.drop_column("idioma_interfaz")
