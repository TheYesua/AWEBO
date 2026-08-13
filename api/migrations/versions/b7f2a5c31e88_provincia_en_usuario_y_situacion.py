"""Provincia en Usuario y SituacionAprendizaje.

Revision ID: b7f2a5c31e88
Revises: a4c81e9d2f60
Create Date: 2026-08-13

QUÉ AÑADE
---------
La provincia es lo que el docente elige en el formulario; la comunidad —que es
la que decide el currículo— se deriva de ella. Ver `services/geografia.py`.

QUÉ HACE CON LO QUE YA HAY
---------------------------
Rellena `provincia` a partir de `comunidad_autonoma` **solo cuando la
correspondencia es inequívoca**: comunidades uniprovinciales y las dos ciudades
autónomas. Una fila que diga «Andalucía» se queda con la provincia en NULL,
porque Andalucía son ocho y elegir una sería inventarse un dato.

Eso no rompe nada: `geografia.comunidad_de` cae a `comunidad_autonoma` cuando
no hay provincia, así que esas filas siguen teniendo su currículo. Lo único que
les falta es el matiz local, y lo rellenará quien las edite.

Los datos reales de hoy son todos «Ceuta», así que en la práctica se convierten
todos. La tabla de correspondencias existe para que la migración siga siendo
correcta si alguien la ejecuta sobre otra base.
"""
from alembic import op
import sqlalchemy as sa


revision = "b7f2a5c31e88"
down_revision = "a4c81e9d2f60"
branch_labels = None
depends_on = None


#: nombre tal y como está escrito -> código de provincia.
#:
#: Solo las inequívocas. Se escriben en minúscula y sin tildes porque la
#: comparación se hace así: el campo ha sido texto libre y hay de todo.
INEQUIVOCAS = {
    "ceuta": "ceuta",
    "melilla": "melilla",
    "madrid": "madrid",
    "comunidad de madrid": "madrid",
    "murcia": "murcia",
    "region de murcia": "murcia",
    "navarra": "navarra",
    "la rioja": "la-rioja",
    "cantabria": "cantabria",
    "asturias": "asturias",
    "principado de asturias": "asturias",
    "baleares": "baleares",
    "islas baleares": "baleares",
    "illes balears": "baleares",
}


def upgrade() -> None:
    op.add_column(
        "usuario", sa.Column("provincia", sa.String(length=30), nullable=True)
    )
    op.create_index("ix_usuario_provincia", "usuario", ["provincia"])
    op.add_column(
        "situacion_aprendizaje",
        sa.Column("provincia", sa.String(length=30), nullable=True),
    )

    # `translate` quita las tildes en SQL. Se hace aquí y no en Python para no
    # traerse las filas a la aplicación: son pocas hoy, pero una migración que
    # carga toda una tabla en memoria envejece mal.
    for tabla in ("usuario", "situacion_aprendizaje"):
        for escrito, codigo in INEQUIVOCAS.items():
            op.execute(
                sa.text(
                    f"UPDATE {tabla} SET provincia = :codigo "  # noqa: S608
                    f"WHERE provincia IS NULL AND comunidad_autonoma IS NOT NULL "
                    f"AND translate(lower(trim(comunidad_autonoma)), "
                    f"'áéíóúàèìòùäëïöü', 'aeiouaeiouaeiou') = :escrito"
                ).bindparams(codigo=codigo, escrito=escrito)
            )


def downgrade() -> None:
    op.drop_column("situacion_aprendizaje", "provincia")
    op.drop_index("ix_usuario_provincia", table_name="usuario")
    op.drop_column("usuario", "provincia")
