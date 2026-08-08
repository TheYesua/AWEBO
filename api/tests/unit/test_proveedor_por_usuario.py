"""Tests de la elección de proveedor y modelo por usuario.

Cubre las tres piezas: el catálogo (qué se puede elegir), la factoría (cómo se
resuelve la elección) y la propagación al worker de Celery, que es la parte
que no era evidente — el worker corre en otro proceso, sin sesión ni petición.
"""
from __future__ import annotations

import pytest

from app.ai import catalogo
from app.ai.factory import (
    _cache,
    get_provider,
    get_provider_para,
    reset_cache,
)
from app.models import Rol, Usuario


#: Claves de configuración que estos tests manipulan. La fixture ``app`` es de
#: sesión, así que sin restaurarlas un test dejaría el despliegue alterado para
#: todos los siguientes — y el fallo aparecería en un fichero distinto.
_CLAVES_IA = (
    "AI_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_MODELOS",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_MODELOS",
)


@pytest.fixture(autouse=True)
def _entorno_ia_aislado(app):
    """Caché de proveedores vacía y configuración de IA restaurada al salir."""
    reset_cache()
    previo = {k: app.config.get(k) for k in _CLAVES_IA}
    yield
    for k, v in previo.items():
        if v is None:
            app.config.pop(k, None)
        else:
            app.config[k] = v
    reset_cache()


@pytest.fixture()
def usuario(db):
    """Docente sin preferencia de IA (el estado de toda cuenta nueva)."""
    rol = db.session.query(Rol).filter_by(nombre="docente").one()
    u = Usuario(id_rol=rol.id_rol, correo="ia@test.com", nombre="Docente IA")
    u.set_password("ContraSegura1!")
    db.session.add(u)
    db.session.commit()
    return u


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------


class TestCatalogo:
    def test_solo_ofrece_proveedores_con_clave(self, app):
        """Ofrecer uno sin clave llevaría a elegir algo que cae al simulado."""
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = ""
            app.config["GEMINI_API_KEY"] = ""
            nombres = {p.nombre for p in catalogo.disponibles()}
            assert "openai" not in nombres
            assert "gemini" not in nombres

    def test_el_simulado_solo_aparece_si_es_el_del_sistema(self, app):
        with app.test_request_context():
            app.config["AI_PROVIDER"] = "fake"
            assert "fake" in {p.nombre for p in catalogo.disponibles()}

            app.config["AI_PROVIDER"] = "gemini"
            assert "fake" not in {p.nombre for p in catalogo.disponibles()}

    def test_los_modelos_salen_de_la_configuracion(self, app):
        """Nada de listas de modelos incrustadas en el código: caducarían."""
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            app.config["GEMINI_MODEL"] = "modelo-base"
            app.config["GEMINI_MODELOS"] = "modelo-extra-1, modelo-extra-2"

            gemini = next(p for p in catalogo.disponibles() if p.nombre == "gemini")
            assert gemini.ids == ["modelo-base", "modelo-extra-1", "modelo-extra-2"]
            # El configurado va primero: es el que se sabe que funciona aquí.
            assert gemini.modelo_por_defecto == "modelo-base"

    def test_no_se_repite_el_modelo_configurado(self, app):
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            app.config["GEMINI_MODEL"] = "repetido"
            app.config["GEMINI_MODELOS"] = "repetido, otro"

            gemini = next(p for p in catalogo.disponibles() if p.nombre == "gemini")
            assert gemini.ids == ["repetido", "otro"]


    def test_una_entrada_puede_llevar_etiqueta_legible(self, app):
        """El docente ve la etiqueta; a la API viaja el id."""
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            app.config["GEMINI_MODEL"] = "modelo-base"
            app.config["GEMINI_MODELOS"] = "modelo-x|Modelo X — el rápido"

            gemini = next(p for p in catalogo.disponibles() if p.nombre == "gemini")
            etiquetas = {m.id: m.etiqueta for m in gemini.modelos}
            assert etiquetas["modelo-x"] == "Modelo X — el rápido"
            # Sin etiqueta, se muestra el propio id: menos amable, pero usable.
            assert etiquetas["modelo-base"] == "modelo-base"

    def test_la_etiqueta_no_afecta_a_la_validacion(self, app):
        """Se valida contra el id, no contra el texto que ve el usuario."""
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            app.config["GEMINI_MODEL"] = "modelo-base"
            app.config["GEMINI_MODELOS"] = "modelo-x|Modelo X — el rápido"
            assert catalogo.validar("gemini", "modelo-x") == ("gemini", "modelo-x")
            assert catalogo.validar("gemini", "Modelo X — el rápido") == (
                "gemini",
                "modelo-base",
            )


class TestValidacion:
    def test_sin_eleccion_devuelve_el_del_sistema(self, app):
        with app.test_request_context():
            assert catalogo.validar(None, None) == (None, None)
            assert catalogo.validar("", "") == (None, None)

    def test_proveedor_inexistente_cae_al_del_sistema(self, app):
        with app.test_request_context():
            assert catalogo.validar("proveedor-inventado", "x") == (None, None)

    def test_proveedor_que_dejo_de_estar_disponible_no_rompe_la_cuenta(self, app):
        """Quitar una clave del .env no debe dejar inservible a quien la eligió."""
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = ""
            assert catalogo.validar("gemini", "gemini-3.5-flash") == (None, None)

    def test_modelo_invalido_cae_al_por_defecto_del_proveedor(self, app):
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            app.config["GEMINI_MODEL"] = "modelo-bueno"
            app.config["GEMINI_MODELOS"] = ""
            assert catalogo.validar("gemini", "modelo-que-ya-no-existe") == (
                "gemini",
                "modelo-bueno",
            )

    def test_proveedor_sin_modelo_usa_el_por_defecto(self, app):
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            app.config["GEMINI_MODEL"] = "modelo-bueno"
            assert catalogo.validar("gemini", None) == ("gemini", "modelo-bueno")


# ---------------------------------------------------------------------------
# Factoría
# ---------------------------------------------------------------------------


class TestFactoria:
    def test_sin_argumentos_se_comporta_como_antes(self, app):
        """Compatibilidad: hay llamadas sin usuario (CLI, healthcheck)."""
        with app.test_request_context():
            assert get_provider().nombre == "fake"

    def test_la_cache_distingue_modelos_del_mismo_proveedor(self, app):
        """El modelo se fija al construir el cliente, así que forma parte de
        la clave. Con la clave anterior —solo el nombre— dos docentes con el
        mismo proveedor y distinto modelo habrían compartido instancia."""
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            p1 = get_provider("gemini", "modelo-a")
            p2 = get_provider("gemini", "modelo-b")
            p3 = get_provider("gemini", "modelo-a")

            assert p1.modelo == "modelo-a"
            assert p2.modelo == "modelo-b"
            assert p1 is p3, "misma pareja debería reutilizar la instancia"
            assert p1 is not p2

    def test_proveedor_desconocido_es_error(self, app):
        with app.test_request_context():
            with pytest.raises(ValueError):
                get_provider("proveedor-inventado")

    def test_sin_clave_cae_al_simulado(self, app):
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = ""
            assert get_provider("gemini").nombre == "fake"


class TestResolucionPorUsuario:
    def test_usuario_sin_preferencia_usa_el_del_sistema(self, app, usuario):
        with app.test_request_context():
            assert get_provider_para(usuario).nombre == "fake"

    def test_usuario_none_no_revienta(self, app):
        """Hay caminos sin usuario asociado; deben seguir funcionando."""
        with app.test_request_context():
            assert get_provider_para(None).nombre == "fake"

    def test_se_respeta_la_preferencia_del_usuario(self, app, db, usuario):
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = "clave-de-prueba"
            app.config["GEMINI_MODEL"] = "modelo-elegido"
            usuario.proveedor_ia = "gemini"
            usuario.modelo_ia = "modelo-elegido"

            provider = get_provider_para(usuario)
            assert provider.nombre == "gemini"
            assert provider.modelo == "modelo-elegido"

    def test_preferencia_obsoleta_cae_al_del_sistema(self, app, db, usuario):
        """La validación se hace en cada uso, no solo al guardar el perfil."""
        with app.test_request_context():
            app.config["GEMINI_API_KEY"] = ""      # se retiró la clave
            usuario.proveedor_ia = "gemini"
            usuario.modelo_ia = "lo-que-sea"
            assert get_provider_para(usuario).nombre == "fake"


# ---------------------------------------------------------------------------
# Propagación al worker
# ---------------------------------------------------------------------------


class TestPropagacionAlWorker:
    """La parte que no era evidente.

    El worker de Celery corre en otro proceso: no tiene sesión ni petición, y
    por tanto tampoco ``current_user``. La preferencia se lee del PROPIETARIO
    de la situación, que la tarea ya tiene cargado.
    """

    def test_la_tarea_usa_el_proveedor_del_propietario(self, app, db, monkeypatch):
        from app.models import SituacionAprendizaje
        from app.tasks import generacion

        rol = db.session.query(Rol).filter_by(nombre="docente").one()
        dueño = Usuario(id_rol=rol.id_rol, correo="dueno@test.com", nombre="Dueño")
        dueño.set_password("ContraSegura1!")
        dueño.proveedor_ia = "gemini"
        dueño.modelo_ia = "modelo-del-dueno"
        db.session.add(dueño)
        db.session.flush()

        sa = SituacionAprendizaje(
            id_usuario=dueño.id_usuario,
            titulo="SA de prueba",
            curso="2º ESO",
            materia="Matemáticas",
        )
        db.session.add(sa)
        db.session.commit()

        id_sa = sa.id_situacion
        recibidos = {}

        def _espia(usuario):
            recibidos["proveedor"] = getattr(usuario, "proveedor_ia", None)
            recibidos["modelo"] = getattr(usuario, "modelo_ia", None)
            from app.ai import FakeProvider

            return FakeProvider()

        monkeypatch.setattr(generacion, "get_provider_para", _espia)

        # ``.apply()`` y no una llamada directa: la tarea usa
        # ``self.update_state(...)``, que necesita un task_id real.
        with app.app_context():
            generacion.generar_situacion_completa.apply(args=(id_sa,)).get()

        assert recibidos["proveedor"] == "gemini", (
            "la tarea debe leer la preferencia del propietario de la SA; "
            "el worker no tiene current_user"
        )
        assert recibidos["modelo"] == "modelo-del-dueno"


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------


def _registrar(client, correo="perfil@test.com"):
    res = client.post(
        "/auth/register",
        json={"correo": correo, "contrasena": "ContraSegura1!", "nombre": "Docente"},
    )
    assert res.status_code in (200, 201)


class TestPerfil:
    def test_el_catalogo_requiere_sesion(self, client, db):
        assert client.get("/me/ia/catalogo").status_code == 401

    def test_el_catalogo_incluye_el_del_sistema(self, client, db):
        _registrar(client)
        cuerpo = client.get("/me/ia/catalogo").get_json()
        assert "proveedores" in cuerpo
        assert cuerpo["sistema"]["proveedor"] == "fake"

    def test_cuenta_nueva_no_tiene_preferencia(self, client, db):
        _registrar(client)
        cuerpo = client.get("/me").get_json()
        assert cuerpo["proveedor_ia"] is None
        assert cuerpo["modelo_ia"] is None

    def test_se_puede_volver_al_del_sistema(self, client, db):
        """Enviar null debe borrar la preferencia, no ignorarse."""
        _registrar(client)
        client.put("/me", json={"proveedor_ia": "fake", "modelo_ia": "fake"})
        cuerpo = client.put(
            "/me", json={"proveedor_ia": None, "modelo_ia": None}
        ).get_json()
        assert cuerpo["proveedor_ia"] is None

    def test_una_eleccion_invalida_no_da_error_sino_el_del_sistema(self, client, db):
        """No es culpa del usuario que un proveedor deje de estar disponible."""
        _registrar(client)
        res = client.put("/me", json={"proveedor_ia": "proveedor-inventado"})
        assert res.status_code == 200
        assert res.get_json()["proveedor_ia"] is None

    def test_guardar_otros_campos_no_toca_la_preferencia(self, client, db):
        _registrar(client)
        client.put("/me", json={"proveedor_ia": "fake", "modelo_ia": "fake"})
        cuerpo = client.put("/me", json={"nombre": "Nombre Nuevo"}).get_json()
        assert cuerpo["nombre"] == "Nombre Nuevo"
        assert cuerpo["proveedor_ia"] == "fake"
