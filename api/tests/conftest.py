"""Configuración común de pytest.

Apuntamos a la base de datos ``awebo_test`` (separada de la de desarrollo
``awebo``) para que los tests no toquen los datos manuales del usuario.
El esquema se crea con ``db.create_all()`` al arrancar la sesión y se
limpian las tablas volátiles antes de cada test.
"""
from __future__ import annotations

import re

import pytest
from flask import has_app_context
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers

from app import create_app, csrf
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
    SESSION_COOKIE_SECURE = False  # los tests no usan HTTPS

    # CSRF: aquí vivió `WTF_CSRF_ENABLED = False` desde antes de que existiera
    # ningún CSRF, y no hacía nada —Flask-WTF nunca se instaló, así que nadie
    # leía esa variable—. Parecía una decisión tomada y era una línea inerte;
    # de las peores, porque al leer el fichero daba por contestada una pregunta
    # que seguía abierta. La protección real está en `app/csrf.py`, va
    # **activada** también en los tests, y el token lo manda `ClienteConCSRF`.

    SQLALCHEMY_DATABASE_URI = _redirigir_a_test_db(Config.SQLALCHEMY_DATABASE_URI)

    # Clave fija y propia. Desde el 21/09 `Config.SECRET_KEY` no tiene valor
    # por defecto —era una clave publicada—, así que sin esto los tests se
    # quedarían con la del `.env` de quien lanza la batería, o sin ninguna.
    #
    # Es la misma lección que ya está escrita abajo dos veces, para el correo y
    # para la voz: **una batería cuyo resultado depende del entorno de quien la
    # lanza no dice nada sobre el código.** Aquí además tiene efecto propio:
    # las firmas de `services/tokens.py` salen deterministas.
    SECRET_KEY = "clave-solo-para-tests-no-sirve-para-nada-mas"

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

    # Voz: **la misma lección, repetida**. El 09/08 se fijó aquí el correo
    # porque `SMTP_SIN_TLS=1` del contenedor se colaba en los tests; el 11/08
    # pasó otra vez con `VOZ_PROVEEDOR=local`, que hizo fallar un test que
    # esperaba que la síntesis no estuviera disponible. La batería no puede
    # depender de lo que haya en el `.env` de quien la lanza: cada test que
    # quiera un proveedor concreto lo configura él.
    VOZ_PROVEEDOR = "nulo"
    VOZ_AHOTTS_DIR = "/no-existe-a-proposito"

    # Rate limiting deshabilitado por defecto: cada test concreto que
    # quiera verificarlo lo activará en su fixture local.
    RATELIMIT_ENABLED = False


class ClienteConCSRF(FlaskClient):
    """Cliente de pruebas que manda el token CSRF, como haría el navegador.

    POR QUÉ EL CSRF NO SE DESACTIVA EN LOS TESTS
    ---------------------------------------------
    Lo habitual es apagarlo con una variable y escribir cuatro tests que lo
    encienden para comprobar que bloquea. Funciona, y deja los 31 endpoints que
    cambian estado sin recorrer nunca el camino real: el que lleva la cabecera,
    la compara y decide. Es la clase de hueco que ya ha mordido dos veces esta
    semana —una comprobación que existe y no se ejercita—.

    Así, los 298 tests que hacen POST, PUT o DELETE pasan por la validación de
    verdad. Y si algún día el mecanismo se rompe, no lo dice un test suelto: lo
    dicen los 298.

    CÓMO
    ----
    Antes de cada petición se asegura de que la sesión tenga token y lo manda
    en la cabecera. Es lo mismo que hace el navegador, donde el token sale del
    `<meta>` de `base.html` y lo pone el envoltorio de `fetch` de `app.js`.

    Un test que quiera comprobar el rechazo tiene dos vías, y las dos se
    respetan: mandar `X-CSRF-Token` a mano —aunque sea vacío— o fijar otro
    token en la sesión con `session_transaction`.
    """

    #: Fijo, y no aleatorio, para que un fallo sea reproducible. No es un
    #: secreto: es el token de una sesión de pruebas.
    TOKEN = "token-csrf-de-pruebas"

    def open(self, *args, **kwargs):
        # RELLENA HUECOS, NO PISA NADA. Las dos comprobaciones de abajo dicen
        # «si el test no lo ha puesto», y no «si no vale». La diferencia la
        # descubrió la primera versión, que decía `if not cabeceras.get(...)` y
        # sobrescribía la cabecera vacía de un test que quería comprobar
        # justamente el rechazo: el CSRF pasaba, el login respondía 400 por el
        # cuerpo vacío, y el test fallaba acusando al código. Un ayudante de
        # tests que corrige al test en silencio es peor que no tenerlo.
        with self.session_transaction() as sesion:
            if csrf.CLAVE_SESION not in sesion:
                sesion[csrf.CLAVE_SESION] = self.TOKEN

        cabeceras = Headers(kwargs.get("headers") or {})
        # `not in` y no `not ...get()`: una cabecera presente y vacía es una
        # decisión del test, y una cadena vacía es falsa.
        if csrf.NOMBRE_CABECERA not in cabeceras:
            cabeceras.set(csrf.NOMBRE_CABECERA, self.TOKEN)
        kwargs["headers"] = cabeceras

        return super().open(*args, **kwargs)


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

    # En el fixture `app` y no en `client`: así lo hereda todo el que llame a
    # `app.test_client()` por su cuenta, que es como lo hacen varios tests.
    app.test_client_class = ClienteConCSRF

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
    """Cliente HTTP de pruebas. La clase la fija el fixture `app`."""
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

    ``comunidad`` por defecto «ceuta» porque es la de todas las SdA de prueba,
    que se crean con ``comunidad_autonoma="Ceuta"``. Desde que el catálogo
    guarda más de un currículo, sembrar en una comunidad y generar en otra deja
    el contexto vacío — que es lo correcto, pero desconcierta si se olvida.
    """
    from app.models import Competencia, CriterioEvaluacion, SaberBasico

    def _sembrar(
        materia: str = "Matemáticas",
        cursos: tuple[str, ...] = ("1º ESO", "2º ESO", "3º ESO"),
        codigo: str = "CE1",
        comunidad: str = "ceuta",
        idioma: str = "es",
    ) -> None:
        cursos = list(cursos)
        ce = Competencia(
            codigo=codigo,
            tipo=Competencia.ESPECIFICA,
            materia=materia,
            comunidad=comunidad,
            idioma=idioma,
            etapa="ESO",
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
                comunidad=comunidad,
                idioma=idioma,
                etapa="ESO",
                cursos_aplicables=cursos,
                descripcion="Criterio de evaluación de prueba.",
            )
        )
        db.session.add(
            SaberBasico(
                codigo="A.1",
                bloque="Bloque A",
                materia=materia,
                comunidad=comunidad,
                idioma=idioma,
                etapa="ESO",
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


def cerrar_transaccion_colgada() -> bool:
    """Cierra la transacción de la sesión si quedó abierta. Dice si la había.

    Está fuera del fixture para que se pueda probar: un fixture `autouse` solo
    se observa por sus efectos, y una guarda que no se ha visto en rojo no se
    sabe qué mide. Ver `tests/unit/test_guarda_de_transacciones.py`.
    """
    # Sin contexto de aplicación no hay sesión que mirar: el `scopefunc` de
    # Flask-SQLAlchemy lo exige y consultarlo reventaría. Pasa en los tests
    # puramente unitarios que corren antes de que nadie pida `app`.
    if not has_app_context():
        return False

    registro = _db.session.registry
    if not registro.has():
        return False

    # `registry.has()` antes de tocar nada: consultar la sesión la **crearía**,
    # y el instrumento de medida no puede fabricar aquello que mide. Es la
    # regla 15, aplicada a la propia guarda.
    abierta = registro().in_transaction()

    _db.session.rollback()
    _db.session.remove()
    return abierta


@pytest.fixture(autouse=True)
def _ninguna_transaccion_se_queda_abierta(request):
    """Ningún test deja una transacción viva detrás.

    EL DÍA QUE ESTO HIZO FALTA
    --------------------------
    El 20/09/2026 la batería se quedó **colgada al 74 %**, sin mensaje, dos
    ejecuciones seguidas; hubo que cortarlas a mano, la primera a los 29
    minutos. El test que se paraba era el primero de `test_i18n.py` que pide
    `db`, y no tenía nada que ver: la causa estaba ocho ficheros antes.

    Un test nuevo llamaba a un servicio que consulta la base de datos. Pudo
    hacerlo **sin pedir el fixture `db`** porque el fixture `app` es de ámbito
    sesión y mantiene un contexto de aplicación abierto durante toda la
    batería: cualquier test puede consultar, pero solo `db` limpia después.
    Aquella transacción se quedó abierta con su `ACCESS SHARE` sobre
    `situacion_aprendizaje`, y el `TRUNCATE ... CASCADE` del siguiente `db` se
    puso a esperar ese bloqueo para siempre.

    QUÉ HACE, Y POR QUÉ LAS DOS COSAS
    ----------------------------------
    **Limpia siempre**, que es lo que impide que vuelva a colgarse: con la
    transacción cerrada, el `TRUNCATE` siguiente no tiene a quién esperar.

    **Y además falla**, porque limpiar en silencio convierte un fallo en una
    costumbre. Un test que consulta la base de datos sin pedir `db` tampoco la
    encuentra limpia al empezar, así que lo que mide depende de lo que dejara
    el test anterior — el cuelgue era el síntoma ruidoso de algo que también
    hace daño callado.

    POR QUÉ LIMPIA TAMBIÉN AL EMPEZAR
    ----------------------------------
    Para que la culpa sea inequívoca. Sin esa limpieza previa, una transacción
    abierta por la siembra de la sesión —o por el test anterior, si la guarda
    se saltara— se le achacaría al primer test que pasara por aquí, que es
    exactamente el diagnóstico equivocado que costó las dos ejecuciones.

    NO PIDE `app` A PROPÓSITO
    -------------------------
    Sería lo natural y estaría mal: un `autouse` que dependa de `app` arrastra
    la sesión de base de datos a **todos** los tests, incluidos los puramente
    unitarios que hoy corren sin Postgres. La guarda se apaña mirando si hay
    contexto de aplicación, que es justo cuando hay algo que vigilar.
    """
    if has_app_context():
        _db.session.remove()

    yield

    if cerrar_transaccion_colgada():
        pytest.fail(
            f"{request.node.nodeid} terminó con una transacción abierta.\n"
            "Se ha cerrado para que no cuelgue la batería, pero hay que "
            "arreglar el test: si toca la base de datos, que pida el fixture "
            "`db` —es el que la deja limpia antes y la cierra después—. Si no "
            "pretendía tocarla, ahí está el fallo.\n"
            "Contexto: docs/DIARIO.md, entrada del 20/09/2026.",
            pytrace=False,
        )
