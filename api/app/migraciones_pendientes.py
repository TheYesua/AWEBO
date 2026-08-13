"""Avisar al arrancar si la base de datos va por detrás del código.

POR QUÉ EXISTE
--------------
El 13/08/2026, tras añadir la columna `provincia`, la aplicación entera devolvía
**Internal Server Error**: portada, login, formulario, todo. El motivo era que
la migración no se había aplicado, así que cada consulta a `usuario` pedía una
columna que no existía.

El fallo no tiene nada de sutil, pero **su síntoma no dice nada**. Un 500 en
todas las páginas se parece mucho a «he roto algo gordo», y lo que hacía falta
era una orden de una línea. La diferencia entre las dos cosas estaba enterrada
en el log del contenedor.

QUÉ HACE, Y QUÉ NO
------------------
Compara la revisión que dice la base de datos con la que espera el código y, si
no coinciden, lo **registra como error** con el comando exacto que lo arregla.

**No impide arrancar.** Se pensó y se descartó: una aplicación que se niega a
levantarse es peor de diagnosticar que una que levanta quejándose, sobre todo en
Docker, donde un contenedor que muere en bucle esconde su propio motivo. Y hay
un caso legítimo en el que no coinciden: mientras se está migrando.

Tampoco toca la base de datos. Solo lee `alembic_version`, que es una tabla de
una fila.
"""
from __future__ import annotations

import structlog


log = structlog.get_logger(__name__)


def _revision_del_codigo(app) -> str | None:
    """La cabeza de `migrations/versions/`, según Alembic."""
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(app.root_path).replace("/app", "") + "/migrations")
    script = ScriptDirectory.from_config(cfg)
    cabezas = script.get_heads()
    return cabezas[0] if len(cabezas) == 1 else None


def comprobar(app) -> None:
    """Registra un error si faltan migraciones. Nunca lanza.

    Que esta comprobación tumbe el arranque sería el colmo de la ironía: una
    ayuda de diagnóstico que impide diagnosticar. Cualquier problema aquí
    —Alembic mal configurado, base de datos aún no disponible— se traga con un
    aviso de nivel bajo.
    """
    try:
        from sqlalchemy import inspect, text

        from .extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            if "alembic_version" not in inspector.get_table_names():
                log.warning(
                    "sin_tabla_de_migraciones",
                    detalle=(
                        "La base de datos no tiene alembic_version. Si es nueva, "
                        "ejecuta: docker compose exec api flask db upgrade"
                    ),
                )
                return

            actual = db.session.scalar(text("SELECT version_num FROM alembic_version"))
            esperada = _revision_del_codigo(app)

        if esperada and actual != esperada:
            log.error(
                "migraciones_pendientes",
                revision_en_la_base_de_datos=actual,
                revision_que_espera_el_codigo=esperada,
                detalle=(
                    "La aplicación va a fallar en cuanto toque una tabla que "
                    "haya cambiado. Ejecuta: "
                    "docker compose exec api flask db upgrade"
                ),
            )
    except Exception:  # noqa: BLE001
        log.debug("no_se_pudo_comprobar_migraciones", exc_info=True)


__all__ = ["comprobar"]
