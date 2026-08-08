"""Tests de la configuración de logging.

Motivo de existir: durante meses la configuración combinó
``PrintLoggerFactory`` con el processor ``structlog.stdlib.add_logger_name``,
que son incompatibles — el primero devuelve un ``PrintLogger`` sin atributo
``.name`` y el segundo lo exige. Cualquier llamada a un logger de structlog
abortaba con ``AttributeError``.

Pasó desapercibido porque los dos únicos usos de structlog en el código
heredado estaban en rutas de error, así que el fallo solo aparecía cuando algo
ya iba mal — y entonces sustituía el diagnóstico real por el AttributeError.

Estos tests fijan lo mínimo para que no vuelva: que loguear no reviente.
"""
from __future__ import annotations

import logging

import pytest
import structlog

from app.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _restaurar_configuracion():
    """Devuelve el logging al estado que deja la app-factory.

    ``configure_logging`` toca estado global (root handlers y la config de
    structlog); sin esto, un test de aquí alteraría los siguientes.
    """
    yield
    structlog.reset_defaults()
    configure_logging(json_logs=False)


class TestNoRevienta:
    """Lo esencial: emitir un log no debe lanzar excepciones."""

    @pytest.mark.parametrize("json_logs", [True, False])
    def test_logger_de_structlog_con_nombre(self, json_logs):
        configure_logging(json_logs=json_logs)
        structlog.get_logger("services.prueba").info("evento", clave="valor")

    @pytest.mark.parametrize("json_logs", [True, False])
    def test_logger_de_structlog_sin_nombre(self, json_logs):
        configure_logging(json_logs=json_logs)
        structlog.get_logger().info("evento")

    @pytest.mark.parametrize("json_logs", [True, False])
    def test_logger_de_stdlib(self, json_logs):
        """Flask, SQLAlchemy y Celery loguean por stdlib, no por structlog."""
        configure_logging(json_logs=json_logs)
        logging.getLogger("libreria.ajena").warning("aviso")

    def test_logger_exception_dentro_de_un_except(self):
        """La ruta que ocultaba el fallo original: registrar una excepción."""
        configure_logging(json_logs=True)
        try:
            raise ValueError("algo se rompió")
        except ValueError:
            structlog.get_logger("tasks.prueba").exception("fallo", id=7)


class TestFactoryCompatible:
    def test_el_factory_devuelve_loggers_con_nombre(self):
        """Fija la causa raíz, no solo el síntoma.

        ``add_logger_name`` lee ``logger.name``. Si alguien vuelve a poner un
        factory cuyos loggers no lo tengan, esto falla aquí en lugar de en
        producción y dentro de un ``except``.
        """
        configure_logging(json_logs=False)
        interno = structlog.get_logger("services.prueba").bind()._logger
        assert hasattr(interno, "name"), (
            f"{type(interno).__name__} no tiene .name; "
            "add_logger_name abortará en cuanto se emita un log"
        )


class TestSalida:
    def test_el_evento_llega_a_stderr_con_su_nombre_y_contexto(self, capfd):
        configure_logging(json_logs=True)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="abc-123")
        try:
            structlog.get_logger("services.prueba").info("evento_de_prueba", n=3)
        finally:
            structlog.contextvars.clear_contextvars()

        salida = capfd.readouterr().err
        assert "evento_de_prueba" in salida
        assert "services.prueba" in salida
        # El request_id que inyecta el middleware debe viajar en cada evento.
        assert "abc-123" in salida
        # Las claves internas del ProcessorFormatter no deben filtrarse.
        assert "_from_structlog" not in salida
