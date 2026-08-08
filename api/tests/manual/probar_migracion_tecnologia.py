"""Arnés manual: ejecuta la migración c9e5a2f81b74 contra un Postgres de usar y tirar.

**No forma parte de `pytest`.** La batería normal crea el esquema con
``db.create_all()``, así que no pasa por las migraciones y no habría detectado
nada de esto. Este script levanta su propio Postgres, reproduce el estado que
dejó el seed antiguo para Tecnología —incluida la fusión de competencias— y
comprueba qué queda después de ``upgrade()`` y de ``downgrade()``.

Se conserva porque ya sirvió: la migración usaba ``:parametro::jsonb``, que
SQLAlchemy no bindea —el ``::`` rompe el reconocimiento del parámetro— y habría
petado en la máquina de Rosa. Leer el SQL no lo habría enseñado.

Cómo ejecutarlo::

    pip install pgserver alembic "psycopg[binary]" sqlalchemy
    python api/tests/manual/probar_migracion_tecnologia.py

Devuelve 0 si todo cuadra.
"""
import importlib.util
import pathlib
import sys

import tempfile

import pgserver
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

RUTA_MIGRACION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "c9e5a2f81b74_separar_tecnologia_y_digitalizacion.py"
)

ESQUEMA = """
DROP TABLE IF EXISTS situacion_competencia, situacion_aprendizaje,
                     criterio_evaluacion, saber_basico, competencia CASCADE;

CREATE TABLE competencia (
    id_competencia   serial PRIMARY KEY,
    codigo           varchar(10) NOT NULL,
    tipo             varchar(20) NOT NULL,
    materia          varchar(50),
    cursos_aplicables jsonb NOT NULL DEFAULT '[]',
    descriptores     jsonb NOT NULL DEFAULT '[]',
    descripcion      text NOT NULL
);
CREATE TABLE criterio_evaluacion (
    id_criterio      serial PRIMARY KEY,
    codigo           varchar(20) NOT NULL,
    id_competencia   integer NOT NULL REFERENCES competencia(id_competencia),
    materia          varchar(50) NOT NULL,
    cursos_aplicables jsonb NOT NULL DEFAULT '[]',
    descripcion      text NOT NULL
);
CREATE TABLE saber_basico (
    id_saber         serial PRIMARY KEY,
    codigo           varchar(20) NOT NULL,
    bloque           varchar(200) NOT NULL,
    materia          varchar(50) NOT NULL,
    cursos_aplicables jsonb NOT NULL DEFAULT '[]',
    descripcion      text NOT NULL
);
CREATE TABLE situacion_aprendizaje (
    id_situacion serial PRIMARY KEY,
    titulo  varchar(255) NOT NULL,
    curso   varchar(20)  NOT NULL,
    materia varchar(50)  NOT NULL
);
CREATE TABLE situacion_competencia (
    id_situacion  integer NOT NULL REFERENCES situacion_aprendizaje(id_situacion),
    id_competencia integer NOT NULL REFERENCES competencia(id_competencia),
    PRIMARY KEY (id_situacion, id_competencia)
);
"""


def sembrar_estado_antiguo(conn):
    """Lo que dejó el seed cuando las dos materias compartían etiqueta.

    Siete competencias bajo "Tecnología": las seis primeras con la descripción
    de 4.º (el último fichero cargado gana) y cursos fusionados 2.º-4.º; la
    séptima, que solo existe en 2.º-3.º, con su texto y cursos correctos.
    """
    for n in range(1, 7):
        conn.execute(sa.text(
            "INSERT INTO competencia (codigo, tipo, materia, cursos_aplicables,"
            " descriptores, descripcion) VALUES (:c,'especifica','Tecnología',"
            " '[\"2º ESO\",\"3º ESO\",\"4º ESO\"]', '[]', :d)"
        ), {"c": f"CE{n}", "d": f"TEXTO DE 4º PISANDO AL DE 2-3 (CE{n})"})
    conn.execute(sa.text(
        "INSERT INTO competencia (codigo, tipo, materia, cursos_aplicables,"
        " descriptores, descripcion) VALUES ('CE7','especifica','Tecnología',"
        " '[\"2º ESO\",\"3º ESO\"]', '[]', 'solo existe en TyD')"
    ))

    ids = dict(conn.execute(sa.text(
        "SELECT codigo, id_competencia FROM competencia WHERE materia='Tecnología'"
    )).all())

    # Criterios: los de 2.º y 3.º son de TyD; los de 4.º, de Tecnología.
    for curso, codigos in (("2º ESO", range(1, 8)),
                           ("3º ESO", range(1, 8)),
                           ("4º ESO", range(1, 7))):
        for n in codigos:
            conn.execute(sa.text(
                "INSERT INTO criterio_evaluacion (codigo, id_competencia, materia,"
                " cursos_aplicables, descripcion)"
                " VALUES (:cod, :idc, 'Tecnología', CAST(:cur AS jsonb), :desc)"
            ), {"cod": f"{n}.1", "idc": ids[f"CE{n}"], "cur": f'["{curso}"]',
                "desc": f"criterio {n}.1 de {curso}"})

    for curso in ("2º ESO", "3º ESO", "4º ESO"):
        conn.execute(sa.text(
            "INSERT INTO saber_basico (codigo, bloque, materia, cursos_aplicables,"
            " descripcion) VALUES ('A.1','Bloque A','Tecnología', CAST(:cur AS jsonb), :d)"
        ), {"cur": f'["{curso}"]', "d": f"saber de {curso}"})

    # Dos situaciones ya creadas: una de 2.º y otra de 4.º, la de 2.º con una
    # competencia seleccionada.
    conn.execute(sa.text(
        "INSERT INTO situacion_aprendizaje (id_situacion, titulo, curso, materia)"
        " VALUES (1,'Robótica','2º ESO','Tecnología'),"
        "        (2,'Domótica','4º ESO','Tecnología')"
    ))
    conn.execute(sa.text(
        "INSERT INTO situacion_competencia (id_situacion, id_competencia)"
        " VALUES (1, :idc)"
    ), {"idc": ids["CE1"]})


def main() -> int:
    srv = pgserver.get_server(tempfile.mkdtemp(prefix="awebo-pg-"))
    motor = sa.create_engine(srv.get_uri().replace("postgresql://", "postgresql+psycopg://"))

    spec = importlib.util.spec_from_file_location("migracion", str(RUTA_MIGRACION))
    migracion = importlib.util.module_from_spec(spec)
    sys.modules["migracion"] = migracion

    fallos = []

    def comprobar(condicion, mensaje):
        print(("   ok   " if condicion else "  FALLO ") + mensaje)
        if not condicion:
            fallos.append(mensaje)

    with motor.begin() as conn:
        for sentencia in ESQUEMA.strip().split(";\n\n"):
            if sentencia.strip():
                conn.execute(sa.text(sentencia))
        sembrar_estado_antiguo(conn)

    def ejecutar(sentido):
        with motor.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                spec.loader.exec_module(migracion)
                getattr(migracion, sentido)()

    print("\n=== ANTES ===")
    with motor.connect() as conn:
        for fila in conn.execute(sa.text(
            "SELECT materia, count(*) FROM competencia GROUP BY 1 ORDER BY 1"
        )):
            print("  competencias:", fila)

    ejecutar("upgrade")

    print("\n=== DESPUÉS DE upgrade() ===")
    with motor.connect() as conn:
        comp = dict(conn.execute(sa.text(
            "SELECT materia, count(*) FROM competencia GROUP BY 1")).all())
        print("  competencias por materia:", comp)
        comprobar(comp.get("Tecnología y Digitalización") == 7,
                  "TyD tiene sus 7 competencias")
        comprobar(comp.get("Tecnología") == 6,
                  "Tecnología se queda con 6 (la CE7 fantasma se borró)")

        crit = dict(conn.execute(sa.text(
            "SELECT materia, count(*) FROM criterio_evaluacion GROUP BY 1")).all())
        print("  criterios por materia:", crit)
        comprobar(crit.get("Tecnología y Digitalización") == 14, "14 criterios de TyD")
        comprobar(crit.get("Tecnología") == 6, "6 criterios de Tecnología")

        cruzados = conn.execute(sa.text(
            """SELECT count(*) FROM criterio_evaluacion cr
                 JOIN competencia c ON c.id_competencia = cr.id_competencia
                WHERE cr.materia <> c.materia"""
        )).scalar()
        comprobar(cruzados == 0,
                  f"ningún criterio cuelga de una competencia de otra materia ({cruzados})")

        sab = dict(conn.execute(sa.text(
            "SELECT materia, count(*) FROM saber_basico GROUP BY 1")).all())
        print("  saberes por materia:", sab)
        comprobar(sab.get("Tecnología y Digitalización") == 2 and sab.get("Tecnología") == 1,
                  "saberes repartidos por curso")

        cursos = dict(conn.execute(sa.text(
            "SELECT materia, cursos_aplicables::text FROM competencia GROUP BY 1,2")).all())
        print("  cursos:", cursos)
        comprobar('4º ESO' in cursos.get("Tecnología", "") and '2º' not in cursos.get("Tecnología", ""),
                  "Tecnología ya solo aplica a 4.º")

        sas = dict(conn.execute(sa.text(
            "SELECT titulo, materia FROM situacion_aprendizaje")).all())
        print("  situaciones:", sas)
        comprobar(sas["Robótica"] == "Tecnología y Digitalización",
                  "la SA de 2.º pasa a Tecnología y Digitalización")
        comprobar(sas["Domótica"] == "Tecnología",
                  "la SA de 4.º se queda en Tecnología")

        enlaces = conn.execute(sa.text(
            "SELECT count(*) FROM situacion_competencia")).scalar()
        comprobar(enlaces == 1, "no se perdió la competencia elegida por la SA")

    ejecutar("downgrade")

    print("\n=== DESPUÉS DE downgrade() ===")
    with motor.connect() as conn:
        comp = dict(conn.execute(sa.text(
            "SELECT materia, count(*) FROM competencia GROUP BY 1")).all())
        print("  competencias por materia:", comp)
        comprobar(set(comp) == {"Tecnología"}, "vuelve a existir una sola materia")
        crit = dict(conn.execute(sa.text(
            "SELECT materia, count(*) FROM criterio_evaluacion GROUP BY 1")).all())
        comprobar(set(crit) == {"Tecnología"}, "los criterios vuelven a Tecnología")
        huerfanos = conn.execute(sa.text(
            """SELECT count(*) FROM criterio_evaluacion cr
                LEFT JOIN competencia c ON c.id_competencia = cr.id_competencia
                WHERE c.id_competencia IS NULL""")).scalar()
        comprobar(huerfanos == 0, f"ninguna clave ajena colgando ({huerfanos})")

    print(f"\n{'TODO OK' if not fallos else str(len(fallos)) + ' FALLOS'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
