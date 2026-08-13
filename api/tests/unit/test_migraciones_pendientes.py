"""El aviso que convierte un 500 mudo en una orden de una línea.

QUÉ PASÓ
--------
El 13/08/2026, tras añadir la columna `provincia`, la aplicación entera devolvía
Internal Server Error: portada, login, formulario. La migración no se había
aplicado, así que cada consulta a `usuario` pedía una columna inexistente.

El fallo no tiene nada de sutil; **su síntoma sí**. Un 500 en todas las páginas
se parece mucho a «he roto algo gordo», cuando lo que faltaba era
`flask db upgrade`. La diferencia estaba enterrada en el log del contenedor.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def con_alembic(app, db):
    """Crea `alembic_version` a mano y devuelve un setter de la revisión.

    La suite construye el esquema con `create_all()`, no con Alembic, así que
    esa tabla **no existe** en los tests. Es el detalle que hizo fallar la
    primera versión de este fichero: suponía una tabla que solo aparece cuando
    las migraciones han corrido de verdad.
    """
    from sqlalchemy import text

    from app.extensions import db as base

    with app.app_context():
        base.session.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        ))
        base.session.commit()

    def fijar(revision: str) -> None:
        with app.app_context():
            base.session.execute(text("DELETE FROM alembic_version"))
            base.session.execute(
                text("INSERT INTO alembic_version VALUES (:r)").bindparams(r=revision)
            )
            base.session.commit()

    yield fijar

    with app.app_context():
        base.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        base.session.commit()


class TestNoPuedeTumbarElArranque:
    """Una ayuda de diagnóstico que impide diagnosticar sería el colmo."""

    def test_si_algo_falla_dentro_no_propaga(self, app):
        from app import migraciones_pendientes

        with patch("sqlalchemy.inspect", side_effect=RuntimeError("lo que sea")):
            migraciones_pendientes.comprobar(app)   # no debe lanzar

    def test_sin_tabla_de_migraciones_avisa_pero_no_falla(self, app, db, caplog):
        """Es el caso de una base de datos recién creada: no hay
        `alembic_version` porque nadie ha migrado nunca."""
        from app import migraciones_pendientes

        with caplog.at_level("WARNING"):
            migraciones_pendientes.comprobar(app)

        assert "sin_tabla_de_migraciones" in caplog.text
        assert "flask db upgrade" in caplog.text


class TestAvisaCuandoToca:
    def test_con_la_base_de_datos_por_detras_lo_dice_como_error(
        self, app, db, con_alembic, caplog
    ):
        """Nivel `error` y no `warning`: la aplicación **va** a fallar, no es
        una posibilidad remota."""
        from app import migraciones_pendientes

        con_alembic("revision-vieja")
        with patch.object(
            migraciones_pendientes, "_revision_del_codigo", return_value="revision-futura"
        ):
            with caplog.at_level("ERROR"):
                migraciones_pendientes.comprobar(app)

        assert "migraciones_pendientes" in caplog.text
        assert "flask db upgrade" in caplog.text, "hay que dar el comando, no solo el diagnóstico"

    def test_al_dia_no_dice_nada(self, app, db, con_alembic, caplog):
        """Un aviso que sale siempre se aprende a ignorar, y entonces no avisa
        el día que importa."""
        from app import migraciones_pendientes

        con_alembic("la-misma")
        with patch.object(
            migraciones_pendientes, "_revision_del_codigo", return_value="la-misma"
        ):
            with caplog.at_level("ERROR"):
                migraciones_pendientes.comprobar(app)

        assert "migraciones_pendientes" not in caplog.text
