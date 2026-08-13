"""Comunidad e idioma en las tres tablas de currículo.

Revision ID: a4c81e9d2f60
Revises: d1a7f36c8b95
Create Date: 2026-08-13

QUÉ RESUELVE
------------
La base de datos guardaba **un único currículo**, implícitamente el de Ceuta en
castellano. `Competencia`, `CriterioEvaluacion` y `SaberBasico` se identificaban
por `codigo`, `materia` y `cursos_aplicables`, y nada más. Cargar el decreto de
una segunda comunidad habría mezclado sus criterios con los actuales sin forma
de distinguirlos, y una SdA de Ceuta habría acabado citando criterios catalanes.

POR QUÉ LAS COLUMNAS NACEN CON VALOR Y LUEGO SE VUELVEN OBLIGATORIAS
---------------------------------------------------------------------
`ALTER TABLE ... ADD COLUMN ... NOT NULL` sin defecto falla en cuanto hay una
sola fila, y aquí hay unas 2.400. Así que se hace en tres pasos: añadir como
nullable, rellenar, y entonces exigir NOT NULL.

El `server_default` se **retira** al final a propósito. Dejarlo puesto haría que
una inserción que se olvide de la comunidad acabe silenciosamente en Ceuta, que
es exactamente el error que esta migración existe para hacer imposible. El
defecto es una muleta para poblar lo viejo, no una política para lo nuevo.

LOS ÍNDICES
-----------
`ix_*_materia` se sustituye por uno compuesto `(comunidad, materia)`: toda
consulta real filtra por las dos cosas a la vez desde este cambio, y un índice
solo por materia obligaría a recorrer todas las comunidades para cada búsqueda.
"""
from alembic import op
import sqlalchemy as sa


revision = "a4c81e9d2f60"
down_revision = "d1a7f36c8b95"
branch_labels = None
depends_on = None


#: Lo ya cargado sale de la Orden EFP/754, que es la del ámbito de gestión del
#: Ministerio —Ceuta y Melilla—, publicada en castellano.
COMUNIDAD_EXISTENTE = "ceuta"
IDIOMA_EXISTENTE = "es"

_TABLAS = (
    ("competencia", "ix_competencia_materia", "ix_competencia_comunidad_materia"),
    ("criterio_evaluacion", "ix_criterio_materia", "ix_criterio_comunidad_materia"),
    ("saber_basico", "ix_saber_materia", "ix_saber_comunidad_materia"),
)


def upgrade() -> None:
    for tabla, indice_viejo, indice_nuevo in _TABLAS:
        # 1) Nullable con defecto de servidor: es lo que permite añadirla sobre
        #    filas que ya existen sin que el motor se queje.
        op.add_column(
            tabla,
            sa.Column(
                "comunidad",
                sa.String(length=20),
                nullable=True,
                server_default=COMUNIDAD_EXISTENTE,
            ),
        )
        op.add_column(
            tabla,
            sa.Column(
                "idioma",
                sa.String(length=5),
                nullable=True,
                server_default=IDIOMA_EXISTENTE,
            ),
        )

        # 2) Rellenar lo existente. El server_default solo se aplica a filas
        #    nuevas, así que las viejas siguen en NULL hasta este UPDATE.
        op.execute(
            sa.text(
                f"UPDATE {tabla} SET comunidad = :c, idioma = :i "  # noqa: S608
                f"WHERE comunidad IS NULL OR idioma IS NULL"
            ).bindparams(c=COMUNIDAD_EXISTENTE, i=IDIOMA_EXISTENTE)
        )

        # 3) Ahora sí, obligatorias, y sin defecto: una inserción que olvide la
        #    comunidad tiene que fallar, no caer en Ceuta sin avisar.
        op.alter_column(tabla, "comunidad", nullable=False, server_default=None)
        op.alter_column(tabla, "idioma", nullable=False, server_default=None)

        op.drop_index(indice_viejo, table_name=tabla)
        op.create_index(indice_nuevo, tabla, ["comunidad", "materia"])


def downgrade() -> None:
    for tabla, indice_viejo, indice_nuevo in _TABLAS:
        op.drop_index(indice_nuevo, table_name=tabla)
        op.create_index(indice_viejo, tabla, ["materia"])
        op.drop_column(tabla, "idioma")
        op.drop_column(tabla, "comunidad")
