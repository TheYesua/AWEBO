"""usuario: preferencia de proveedor y modelo de IA

Añade ``proveedor_ia`` y ``modelo_ia`` a ``usuario``. Ambas nullables: NULL en
las dos significa «usar el proveedor configurado en el sistema», que es el
comportamiento que ha tenido la aplicación hasta ahora y por tanto el valor
correcto para todas las cuentas existentes. Por eso no hace falta rellenar
nada al aplicar la migración.

Los anchos salen del catálogo real, no de un número redondo: los nombres de
proveedor son identificadores cortos y controlados (``openai``, ``gemini``,
``fake``), mientras que los de modelo los publica cada proveedor y tienden a
crecer con sufijos de fecha y versión.

Revision ID: c3f7a91d5e42
Revises: b2c4d8e1f3a5
Create Date: 2026-08-02 20:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c3f7a91d5e42"
down_revision = "b2c4d8e1f3a5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuario") as b:
        b.add_column(sa.Column("proveedor_ia", sa.String(length=20), nullable=True))
        b.add_column(sa.Column("modelo_ia", sa.String(length=80), nullable=True))


def downgrade():
    with op.batch_alter_table("usuario") as b:
        b.drop_column("modelo_ia")
        b.drop_column("proveedor_ia")
