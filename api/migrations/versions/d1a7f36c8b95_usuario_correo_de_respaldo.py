"""Correo de respaldo del usuario (tarea 13).

Dos columnas nuevas en ``usuario``:

* ``correo_respaldo`` — una dirección **personal**, distinta de la del centro.
* ``correo_respaldo_verificado_en`` — cuándo se confirmó.

POR QUÉ NO ES ÚNICA
-------------------
Dos cuentas pueden compartir una dirección personal, y prohibirlo tendría un
efecto peor que el problema: al rechazar «esa dirección ya está en uso» se
estaría contando que existe una cuenta con ese respaldo, que es justo el tipo
de filtración que el flujo de restablecimiento evita con tanto cuidado.

Cuando una dirección corresponde a varias cuentas, cada una recibe su enlace.

POR QUÉ HAY COLUMNA DE VERIFICACIÓN Y NO UN BOOLEANO
-----------------------------------------------------
Una marca de tiempo responde «¿está verificado?» igual de bien que un booleano
—basta con preguntar si es nula— y además responde «¿desde cuándo?», que es lo
que hace falta si algún día hay que investigar una reclamación disputada. Un
booleano no se puede convertir en fecha después; una fecha sí se puede leer
como booleano.

Ambas nacen nulas: el respaldo es opcional. Las cuentas que ya existen se
quedan sin él y la interfaz se lo ofrecerá.

Revision ID: d1a7f36c8b95
Revises: c9e5a2f81b74
"""
from alembic import op
import sqlalchemy as sa


revision = "d1a7f36c8b95"
down_revision = "c9e5a2f81b74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuario",
        sa.Column("correo_respaldo", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "usuario",
        sa.Column(
            "correo_respaldo_verificado_en",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Índice porque se busca por esta columna en cada restablecimiento: la
    # consulta pasa a ser «correo = X **o** correo_respaldo = X», y sin índice
    # la segunda mitad recorrería la tabla entera.
    op.create_index(
        "ix_usuario_correo_respaldo", "usuario", ["correo_respaldo"]
    )


def downgrade() -> None:
    op.drop_index("ix_usuario_correo_respaldo", table_name="usuario")
    op.drop_column("usuario", "correo_respaldo_verificado_en")
    op.drop_column("usuario", "correo_respaldo")
