"""El título del bloque de saberes pasa de 200 a 1000 caracteres.

Revision ID: f3a8c25e71bd
Revises: a2f6b91c7e34
Create Date: 2026-09-18

POR QUÉ
-------
Cargando el Bachillerato de Ceuta y Melilla, `test_el_catalogo_cabe_en_la_bd`
avisó de que cuatro bloques de la Orden EFP/755 no caben en `varchar(200)`:

* Literatura Dramática, bloque A                      — 390
* Literatura Universal, bloque A                      — 381
* Lengua Castellana y Literatura I y II, bloque D     — 294 (×2)

No es un fallo de extracción: se comprobó contra el XML y cada uno es **un solo
`<p>` del boletín**. En las materias literarias el BOE no titula el bloque con
una etiqueta sino con la frase entera que introduce sus saberes, y que acaba en
dos puntos:

    A. Construcción guiada y compartida de la interpretación de algunos textos
    relevantes de la literatura dramática inscritos en itinerarios temáticos
    que establezcan relaciones intertextuales entre obras y fragmentos de
    diferentes géneros, épocas, contextos culturales y códigos artísticos, así
    como con sus respectivos contextos de producción, de acuerdo a los
    siguientes ejes y estrategias:

De los 2745 bloques de las nueve salidas, esos cuatro son los únicos que pasan
de 200. El máximo anterior era 171, del País Vasco.

LA ALTERNATIVA QUE SE DESCARTÓ
-------------------------------
Recortar los cuatro títulos. Mismo motivo que en `c9e4f2a10b73`, que amplió el
nombre de la materia en vez de acortarlo: lo que se guarda es el texto oficial,
y recortarlo sería redactar un título que no está en ningún boletín. Además, el
`bloque` es lo que se le enseña al modelo junto a cada saber, así que recortarlo
no ahorra una molestia de esquema: quita contexto a la generación.

POR QUÉ 1000 Y NO 400
----------------------
Cuatrocientos bastaría para hoy y volvería a saltar con el primer boletín que
escriba una frase algo más larga — que es exactamente lo que acaba de pasar:
el tope de 200 se fijó con 171 como máximo observado y aguantó hasta que llegó
una fuente con 390, más del doble. Queda Galicia por cargar.

En PostgreSQL `VARCHAR(n)` no reserva espacio —el límite es solo una
comprobación—, así que un margen amplio no cuesta nada. Se conserva un límite en
vez de pasar a `TEXT` por la misma razón que allí: sigue sirviendo para que un
error de extracción que vuelque medio anexo en el campo se note.

LO QUE FALTABA, Y ES LO QUE DE VERDAD IMPORTA
----------------------------------------------
`test_hay_margen_de_sobra_y_no_justo` existe para avisar **antes** de que un
límite salte, y solo vigilaba `materia`. `bloque` estaba al 85 % de su tope
—171 de 200— y nadie lo dijo. Ese test pasa ahora también por `bloque`, así que
la próxima vez el aviso llega con margen y no en mitad de una carga.

Es reversible: `downgrade` vuelve a 200, y solo funcionará si no queda ninguna
fila que exceda ese tamaño — es decir, habiendo quitado antes el currículo de
Bachillerato de Ceuta y Melilla.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "f3a8c25e71bd"
down_revision: str | None = "a2f6b91c7e34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "saber_basico",
        "bloque",
        existing_type=sa.String(length=200),
        type_=sa.String(length=1000),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "saber_basico",
        "bloque",
        existing_type=sa.String(length=1000),
        type_=sa.String(length=200),
        existing_nullable=False,
    )
