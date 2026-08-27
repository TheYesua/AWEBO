"""El nombre de la materia pasa de 50 a 120 caracteres.

Revision ID: c9e4f2a10b73
Revises: b7f2a5c31e88
Create Date: 2026-08-27

POR QUÉ
-------
Cargando el currículo vasco, el `seed` abortó con
`StringDataRightTruncation: value too long for type character varying(50)`.
Cuatro materias del Decreto 77/2023 pasan de 50 caracteres, y la más larga
llega a 57:

* GARAPEN PERTSONALARI ETA SOZIALARI APLIKATUTAKO FILOSOFIA — 57
* PRESTAKUNTZA ETA ORIENTAZIO PERTSONALA ETA PROFESIONALA — 55
* EUSKARA ETA LITERATURA ETA GAZTELANIA ETA LITERATURA — 52
* HEZKUNTZA PLASTIKOA, IKUSIZKOA ETA IKUS-ENTZUNEZKOA — 51

En las otras cuatro comunidades el nombre más largo mide 46, así que el límite
nunca se había rozado. No es que el euskera sea más largo: es que ahí donde el
castellano abrevia —«Filosofía aplicada»— el decreto vasco escribe el sintagma
entero, y ese es el nombre oficial.

LA ALTERNATIVA QUE SE DESCARTÓ
-------------------------------
Acortar los cuatro nombres para que cupieran. Se descarta porque el nombre de
la materia es **el que el docente cita en su programación**, y recortarlo sería
inventar una denominación que no está en ningún boletín — que es justo lo que
este proyecto lleva evitando desde los cursos de Llatí.

DÓNDE SE TOCA, Y LO QUE DE VERDAD IMPORTA
------------------------------------------
En las tres tablas del catálogo —`competencia`, `criterio`, `saber_basico`— y
**también en `situacion_aprendizaje`**, que es la que importa: el seed falló
antes de tocar esa, pero ahí es donde se guarda la materia que el docente elige
al crear una situación. Sin ampliarla, el fallo habría reaparecido más tarde y
ya no en un comando de carga sino **al guardar el trabajo de alguien**.

POR QUÉ 120 Y NO 60
--------------------
Sesenta bastaría para hoy y volvería a saltar con la primera comunidad que
escriba un nombre algo más largo. En PostgreSQL `VARCHAR(n)` no reserva espacio
—el límite es solo una comprobación—, así que un margen amplio no cuesta nada.
Se conserva un límite en vez de pasar a `TEXT` porque un nombre de materia no
es texto libre, y un tope sigue siendo útil para que un error de extracción no
meta un párrafo entero en el campo.

Es reversible: `downgrade` vuelve a 50, y solo funcionará si no hay ninguna
fila que ya exceda ese tamaño.
"""
from alembic import op
import sqlalchemy as sa


revision = "c9e4f2a10b73"
down_revision = "b7f2a5c31e88"
branch_labels = None
depends_on = None


#: (tabla, columna, admite NULL). `competencia.materia` es la única que lo
#: admite, y hay que decírselo a `alter_column` o la migración la volvería
#: NOT NULL de rebote.
#:
#: Los nombres son los de `__tablename__`, no los de la clase: la tabla del
#: criterio es `criterio_evaluacion` y la de la SdA `situacion_aprendizaje`.
_COLUMNAS = (
    ("competencia", "materia", True),
    ("criterio_evaluacion", "materia", False),
    ("saber_basico", "materia", False),
    ("situacion_aprendizaje", "materia", False),
)


def upgrade() -> None:
    for tabla, columna, nullable in _COLUMNAS:
        op.alter_column(
            tabla, columna,
            existing_type=sa.String(length=50),
            type_=sa.String(length=120),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    for tabla, columna, nullable in _COLUMNAS:
        op.alter_column(
            tabla, columna,
            existing_type=sa.String(length=120),
            type_=sa.String(length=50),
            existing_nullable=nullable,
        )
