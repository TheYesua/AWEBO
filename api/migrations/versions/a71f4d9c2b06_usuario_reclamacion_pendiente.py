"""usuario: solicitud de reclamación pendiente

Añade ``reclamacion_pendiente`` (JSONB, nullable). NULL = sin solicitud, que es
el estado de todas las cuentas existentes.

Guarda los datos con los que alguien pide recuperar una cuenta dada de baja,
**sin aplicarlos**, a la espera de que un administrador lo apruebe. Aplicarlos
antes de la aprobación destruiría el nombre y la contraseña de la persona
anterior, que es justo a quien protege este paso.

Sin índice: se consulta siempre junto a su usuario, nunca como filtro de una
búsqueda propia.

Revision ID: a71f4d9c2b06
Revises: f5c3d80a961e
Create Date: 2026-08-05 13:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a71f4d9c2b06"
down_revision = "f5c3d80a961e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuario") as b:
        b.add_column(
            sa.Column("reclamacion_pendiente", postgresql.JSONB(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("usuario") as b:
        b.drop_column("reclamacion_pendiente")
