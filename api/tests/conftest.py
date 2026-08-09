"""Configuración común de pytest.

Apuntamos a la base de datos ``awebo_test`` (separada de la de desarrollo
``awebo``) para que los tests no toquen los datos manuales del usuario.
El esquema se crea con ``db.create_all()`` al arrancar la sesión y se
limpian las tablas volátiles antes de cada test.
"""
from __future__ import annotations

import re

import pytest

from app import create_app
from app.config import Config
from app.extensions import db as _db
from app.seeds import seed_ods, seed_roles


def _redirigir_a_test_db(uri: str) -> str:
    """Sustituye el nombre de la BD por ``awebo_test`` preservando el resto."""
    # postgresql+psycopg://user:pass@host:port/dbname
    return re.sub(r"/[^/?]+(\?.*)?$", lambda m: "/awebo_test" + (m.group(1) or ""), uri, count=1)


class TestConfig(Config):
    """Configuración de tests: BD aislada `awebo_test`."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False  # los tests no usan HTTPS
    SQLALCHEMY_DATABASE_URI = _redirigir_a_test_db(Config.SQLALCHEMY_DATABASE_URI)

    # IA: siempre el proveedor fake (sin red) durante los tests.
    AI_PROVIDER = "fake"
    OPENAI_API_KEY = ""

    # Correo: igual que la IA, neutralizado. `Config` lee estas variables del
    # entorno del proceso, y el contenedor de desarrollo lleva `SMTP_SIN_TLS=1`
    # y `SMTP_HOST=mailpit` para el buzón de pruebas. Sin fijarlas aquí, esa
    # configuración se cuela en los tests: el 09/08/2026,
    # `test_el_puerto_465_usa_TLS_directo_y_el_587_STARTTLS` empezó a fallar en
    # Docker y a pasar fuera, por eso y no por el código.
    #
    # Lo importante no es el test que falló, sino la clase de fallo: una
    # batería cuyo resultado depende del `.env` de quien la lanza no dice nada
    # sobre el código. Cada test que quiera SMTP lo configura él.
    CORREO_PROVEEDOR = "consola"
    SMTP_HOST = ""
    SMTP_USER = ""
    SMTP_PASSWORD = ""
    SMTP_SIN_TLS = False

    # Rate limiting deshabilitado por defecto: cada test concreto que
    # quiera verificarlo lo activará en su fixture local.
    RATELIMIT_ENABLED = False


def _registrar_endpoints_de_test(app):
    """Registra rutas auxiliares usadas únicamente por los tests."""
    from flask import Blueprint, jsonify

    from app.security import role_required

    bp = Blueprint("_test_role", __name__, url_prefix="/_test")

    @bp.get("/solo-admin")
    @role_required("administrador")
    def _solo_admin():
        return jsonify({"ok": True}), 200

    @bp.get("/admin-o-docente")
    @role_required("administrador", "docente")
    def _admin_o_docente():
        return jsonify({"ok": True}), 200

    app.register_blueprint(bp)


@pytest.fixture(scope="session")
def app():
    """Aplicación Flask compartida durante toda la sesión de tests."""
    app = create_app(TestConfig)
    _registrar_endpoints_de_test(app)

    # Celery en modo síncrono: .delay() ejecuta la tarea en el proceso
    # actual y propaga excepciones, ideal para tests deterministas.
    from app.celery_app import celery_app

    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=True,
    )

    # Invalidar caché del proveedor IA por si el test anterior dejó uno.
    from app.ai.factory import reset_cache

    reset_cache()

    with app.app_context():
        # Materializamos el esquema en la BD de tests (no usamos migraciones
        # aquí: lo importante es que las tablas reflejen los modelos actuales).
        # drop_all previo para evitar esquemas obsoletos de ejecuciones previas.
        _db.drop_all()
        _db.create_all()
        # Seeds básicos disponibles en toda la sesión.
        seed_roles()
        seed_ods()
        yield app


# Tablas que se vacían entre tests. Las que NO aparecen aquí (rol, ods)
# contienen datos de referencia precargados por seeds y se preservan.
_TABLAS_VOLATILES = (
    # Se lista explícitamente aunque el CASCADE del TRUNCATE la vaciaría de
    # todos modos: depender de eso es frágil, y sus claves ajenas son SET NULL
    # precisamente para que la tabla NO muera con lo que apunta.
    "eleccion_propuesta",
    "version",
    "situacion_competencia",
    "situacion_criterio",
    "situacion_saber",
    "situacion_ods",
    "situacion_aprendizaje",
    "criterio_evaluacion",
    "saber_basico",
    "competencia",
    "usuario",
)


@pytest.fixture()
def db(app):
    """Cada test arranca con las tablas volátiles vacías y los seeds intactos."""
    with app.app_context():
        # Limpieza ANTES del test (idempotente y robusta ante fallos previos).
        from sqlalchemy import text

        _db.session.remove()
        _db.session.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(_TABLAS_VOLATILES)
                + " RESTART IDENTITY CASCADE"
            )
        )
        _db.session.commit()

        yield _db

        _db.session.remove()


@pytest.fixture()
def client(app):
    """Cliente HTTP de pruebas."""
    return app.test_client()


@pytest.fixture()
def sembrar_curriculo(db):
    """Devuelve una función que carga un mini-catálogo LOMLOE.

    Hace falta desde que generar exige que la SA tenga currículo al que
    anclarse. Antes de esa comprobación, la suite creaba situaciones de
    materias y cursos sin catálogo alguno y los tests pasaban igual, porque
    ``FakeProvider`` rellena las secciones venga o no currículo en el prompt.
    Es decir: ejercitaban precisamente el camino que resultó estar roto.

    Las tres tablas, no solo competencias: la comprobación exige las tres.
    """
    from app.models import Competencia, CriterioEvaluacion, SaberBasico

    def _sembrar(
        materia: str = "Matemáticas",
        cursos: tuple[str, ...] = ("1º ESO", "2º ESO", "3º ESO"),
        codigo: str = "CE1",
    ) -> None:
        cursos = list(cursos)
        ce = Competencia(
            codigo=codigo,
            tipo=Competencia.ESPECIFICA,
            materia=materia,
            cursos_aplicables=cursos,
            descriptores=["STEM1"],
            descripcion=f"Competencia específica de {materia}.",
        )
        db.session.add(ce)
        db.session.flush()
        db.session.add(
            CriterioEvaluacion(
                codigo=f"{codigo}.1",
                id_competencia=ce.id_competencia,
                materia=materia,
                cursos_aplicables=cursos,
                descripcion="Criterio de evaluación de prueba.",
            )
        )
        db.session.add(
            SaberBasico(
                codigo="A.1",
                bloque="Bloque A",
                materia=materia,
                cursos_aplicables=cursos,
                descripcion="Saber básico de prueba.",
            )
        )
        db.session.commit()

    return _sembrar


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Restaura limiter.enabled a False antes de cada test.

    Los tests de rate limit activan el limiter localmente; este fixture
    evita que su estado global contamine el resto de la suite.
    """
    from app.extensions import limiter

    limiter.enabled = False
    yield
