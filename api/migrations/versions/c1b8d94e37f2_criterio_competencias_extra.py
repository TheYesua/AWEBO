"""El criterio guarda los objetivos de más que le asigna su boletín.

Revision ID: c1b8d94e37f2
Revises: f3a8c25e71bd
Create Date: 2026-09-20

POR QUÉ
-------
Preparando el Bacharelato de Galicia apareció un criterio con **dos**
objetivos. La Guía LOMLOE escribe en la celda «Obxectivos» de CA1.3 y CA1.4 de
Lingua Galega e Literatura de 1.º:

    OBX1 10

que son OBX1 y OBX10, sin repetir el prefijo. El modelo guardaba un objetivo
por criterio, así que la competencia salía como la cadena «1 10», que no existe
en ninguna parte — y el `seed` **omite el criterio entero** cuando no encuentra
su competencia. Los dos criterios no llegaban a la base de datos.

Son 2 de los 1717 de esa etapa. Los otros 1715, y los 1785 de la ESO gallega,
citan un solo objetivo, igual que las ocho comunidades restantes.

POR QUÉ UNA COLUMNA Y NO UN MANY-TO-MANY
-----------------------------------------
El modelo correcto, si esto fuera común, sería una tabla de asociación
criterio–competencia. Se midió lo que costaba: `criterio_evaluacion.id_competencia`
es una FK única y NOT NULL que leen el API en dos sitios, el prompt, el seed y
las dos rutas de exportación, y el campo `competencia` es una **cadena en los
10 944 criterios de las nueve salidas**. Cambiar todo eso por dos registros no
sale a cuenta, y además obligaría a decidir qué enseña la tabla del PDF cuando
hay dos.

Así que `id_competencia` se queda como la relación —el primer objetivo, que es
el que el boletín pone delante— y esta columna guarda los códigos restantes.
La información se conserva entera y el criterio se carga.

Es la misma forma que `saber_basico.codigos_items`, que existe porque solo el
BOJA numera sus saberes: un campo que casi siempre está vacío y que evita
perder lo que una sola fuente sí dice.

QUÉ NO ES
---------
No es una clave ajena. Son códigos tal y como los escribe el boletín, del mismo
tipo que el `competencia` del JSON, y no se resuelven contra la tabla
`competencia`. Si algún día hay que navegarlos, entonces sí toca el
many-to-many — y entonces habrá más de dos filas que lo justifiquen.

`server_default='[]'` para que las filas que ya están no queden a NULL: la
columna es NOT NULL y hay 10 944 criterios cargados.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1b8d94e37f2"
down_revision: str | None = "f3a8c25e71bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "criterio_evaluacion",
        sa.Column(
            "competencias_extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("criterio_evaluacion", "competencias_extra")
