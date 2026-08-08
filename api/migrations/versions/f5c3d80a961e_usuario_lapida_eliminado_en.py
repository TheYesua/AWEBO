"""usuario: lápida (eliminado_en)

Añade ``eliminado_en``, nullable: NULL significa «cuenta viva», que es lo que
son todas las existentes. Ninguna fila necesita relleno.

Permite dar de baja una cuenta conservando su contenido. La alternativa era
hacer ``situacion_aprendizaje.id_usuario`` nullable, y eso obligaría a toda
consulta que filtra por propietario a contemplar el caso NULL, perdiendo la
invariante de que toda SA tiene dueño. Con la lápida, el contenido sigue
ligado y el purgado a los 90 días es un DELETE normal sobre ``usuario``, donde
el CASCADE que ya existe hace lo correcto.

El índice no es decorativo: la tarea periódica de purgado filtra por esta
columna, y sin él haría un recorrido completo de la tabla cada vez.

Revision ID: f5c3d80a961e
Revises: e4a1c93b7d20
Create Date: 2026-08-05 10:15:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f5c3d80a961e"
down_revision = "e4a1c93b7d20"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuario") as b:
        b.add_column(
            sa.Column("eliminado_en", sa.DateTime(timezone=True), nullable=True)
        )
        b.create_index("ix_usuario_eliminado_en", ["eliminado_en"])


def downgrade():
    with op.batch_alter_table("usuario") as b:
        b.drop_index("ix_usuario_eliminado_en")
        b.drop_column("eliminado_en")
