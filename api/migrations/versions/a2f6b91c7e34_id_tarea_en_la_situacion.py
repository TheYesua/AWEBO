"""El identificador de la tarea que genera, en la situación de aprendizaje.

Revision ID: a2f6b91c7e34
Revises: e5b93c47da10
Create Date: 2026-09-17

POR QUÉ
-------
Para que la barra de progreso avance también cuando **no ha sido esta página
quien lanzó la generación**.

El identificador de la tarea Celery lo devuelve el POST que la encola, y con él
el navegador puede sondear `/api/tasks/<id>` y saber por qué sección va. Pero
quien encola no siempre es quien mira: al crear una SdA con la casilla de IA
marcada, el formulario encola y **redirige al detalle**, que nunca ve esa
respuesta. Lo mismo al abrir desde el listado una SdA que está generando, o al
recargar la página.

En esos casos el detalle solo podía sondear el estado de la SdA —que sí es
recuperable—, así que la barra iba en indeterminado, con la sección en «—» y el
contador clavado en «0 / 6» hasta que la generación terminaba de golpe. No
mentía, pero tampoco informaba, y es el camino por el que pasa el docente que
marca la casilla al crear: el más común de los tres.

POR QUÉ UNA COLUMNA Y NO UNA CLAVE EN REDIS
--------------------------------------------
Se consideró que la tarea publicara su progreso en `progreso:sa:<id>`, que el
detalle sí puede pedir sin conocer el identificador. Habría evitado esta
migración, pero añade un segundo canal de estado al lado del que Celery ya
mantiene, y se pierde si Redis se reinicia. La columna es un dato más de la SdA,
que es donde ya vive `estado`, y sobrevive a cualquier reinicio.

NULLABLE, Y SIN RELLENAR NADA
------------------------------
Es un dato transitorio: solo significa algo mientras el estado es `generando`.
Las filas existentes se quedan en NULL y el detalle cae en el sondeo por estado,
que es exactamente lo que hacía antes — así que esta migración no puede empeorar
ninguna SdA ya creada.

No se limpia al terminar, a propósito: deja el rastro de qué tarea la generó, y
`estado` ya dice si sigue en curso.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a2f6b91c7e34"
down_revision: str | None = "e5b93c47da10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "situacion_aprendizaje",
        sa.Column("id_tarea", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("situacion_aprendizaje", "id_tarea")
