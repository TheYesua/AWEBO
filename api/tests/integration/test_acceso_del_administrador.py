"""El administrador puede leerlo todo, y eso va acompañado de tres piezas.

LA DECISIÓN Y SU PRECIO
------------------------
El principio original era **gestión sin lectura**: administrar cuentas sin
poder abrir su contenido. Se revisó el 10/08/2026 y se cambió, porque cerrado
resultaba peor de lo que parecía sobre el papel — quien administra deja de
poder reproducir un fallo que le reportan.

Pero el cambio no es neutro: el panel pasa a ser una vía de acceso a trabajo
ajeno. Se aceptó con **tres condiciones**, y las tres son lo que impide que
sea una puerta silenciosa:

1. Decirlo en el portal de ayuda.
2. Advertirlo en el registro, **antes** de crear la cuenta.
3. Dejar traza de quién abre qué, y no solo de quién borra qué.

Este fichero existe porque las tres son fáciles de perder sin que nada se
rompa. Si mañana desaparece el aviso del registro, la aplicación funciona
igual de bien; lo único que cambia es que la gente deja de saberlo. Un fallo
que no produce ningún síntoma necesita un test o no existe.
"""
from __future__ import annotations

import pytest


CLAVE_ADMIN = "ContrasenaAdmin1"
CLAVE_DOC = "ContrasenaDoc1"


@pytest.fixture
def docente_con_sda(db):
    from app.models import Rol, SituacionAprendizaje, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="ajena@ies.es", nombre="Ajena", id_rol=rol.id_rol)
    u.set_password(CLAVE_DOC)
    db.session.add(u)
    db.session.commit()

    s = SituacionAprendizaje(
        titulo="Trabajo de otra persona", materia="Matemáticas A", curso="4º ESO",
        id_usuario=u.id_usuario, contenido={},
    )
    db.session.add(s)
    db.session.commit()
    return u, s


@pytest.fixture
def admin(db):
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="administrador").first()
    a = Usuario(correo="admin.acceso@ies.es", nombre="Admin", id_rol=rol.id_rol)
    a.set_password(CLAVE_ADMIN)
    db.session.add(a)
    db.session.commit()
    return a


class TestPuedeLeerlo:
    def test_abre_la_situacion_de_otra_persona(self, app, db, admin, docente_con_sda):
        from app.services import situacion_service

        _dueño, sda = docente_con_sda
        with app.test_request_context():
            recuperada = situacion_service.obtener(sda.id_situacion, admin)

        assert recuperada.id_situacion == sda.id_situacion

    def test_un_docente_cualquiera_no(self, app, db, docente_con_sda):
        """La contrapartida: el acceso es del rol, no de cualquiera."""
        from app.models import Rol, Usuario
        from app.services import situacion_service

        _dueño, sda = docente_con_sda
        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        otro = Usuario(correo="tercero@ies.es", nombre="Tercero", id_rol=rol.id_rol)
        otro.set_password(CLAVE_DOC)
        db.session.add(otro)
        db.session.commit()

        with app.test_request_context():
            with pytest.raises(situacion_service.SituacionError) as exc:
                situacion_service.obtener(sda.id_situacion, otro)

        assert exc.value.http_status == 403


class TestLaTraza:
    """Pieza 3. La única de las tres que es código y no texto."""

    def test_queda_constancia_de_que_un_admin_abre_contenido_ajeno(
        self, app, db, admin, docente_con_sda, caplog
    ):
        from app.services import situacion_service

        _dueño, sda = docente_con_sda
        with app.test_request_context():
            with caplog.at_level("INFO"):
                situacion_service.obtener(sda.id_situacion, admin)

        assert "admin_accede_a_contenido_ajeno" in caplog.text
        assert str(sda.id_situacion) in caplog.text

    def test_no_se_registra_cuando_abre_lo_suyo(self, app, db, admin, caplog):
        """Si registrara todo, el registro sería ruido y el evento dejaría de
        significar nada. Lo que interesa es el acceso a contenido **ajeno**."""
        from app.models import SituacionAprendizaje
        from app.services import situacion_service

        propia = SituacionAprendizaje(
            titulo="Suya", materia="Matemáticas A", curso="4º ESO",
            id_usuario=admin.id_usuario, contenido={},
        )
        db.session.add(propia)
        db.session.commit()

        with app.test_request_context():
            with caplog.at_level("INFO"):
                situacion_service.obtener(propia.id_situacion, admin)

        assert "admin_accede_a_contenido_ajeno" not in caplog.text

    def test_tambien_al_editarla_y_no_solo_al_abrirla(
        self, app, db, admin, docente_con_sda, caplog
    ):
        """La traza está en `_verificar_propietario`, que es el cuello de
        botella por el que pasa **todo** lo que un administrador hace con
        contenido ajeno. Puesta en `obtener` habría dejado fuera editar,
        exportar y generar audio, que es donde más importa saberlo."""
        from app.services import situacion_service

        _dueño, sda = docente_con_sda
        with app.test_request_context():
            with caplog.at_level("INFO"):
                situacion_service.actualizar(
                    sda.id_situacion, admin, {"titulo": "Retocado por el admin"}
                )

        assert "admin_accede_a_contenido_ajeno" in caplog.text

    def test_el_registro_no_lleva_el_contenido(self, app, db, admin, docente_con_sda, caplog):
        """Registrar el acceso no puede convertirse en copiar el trabajo ajeno
        a los logs, que se rotan, se envían y se leen en más sitios."""
        from app.services import situacion_service

        _dueño, sda = docente_con_sda
        with app.test_request_context():
            with caplog.at_level("INFO"):
                situacion_service.obtener(sda.id_situacion, admin)

        assert "Trabajo de otra persona" not in caplog.text


class TestSeDice:
    """Piezas 1 y 2. Son texto, así que se comprueba que el texto esté.

    No se puede comprobar que una frase sea verdad —para eso hay que leerla—,
    pero sí que no desaparezca. Ayuda ya ha mentido dos veces en este proyecto
    por quedarse desactualizada; esto al menos detecta que se borre.
    """

    def test_el_portal_de_ayuda_lo_explica(self, client):
        pagina = client.get("/ayuda").get_data(as_text=True)
        assert "administradoras de AWEBO pueden abrir cualquier situación" in pagina

    def test_ayuda_dice_ademas_que_queda_registrado(self, client):
        """Decir que pueden entrar sin decir que queda rastro contaría media
        verdad, y la media que peor sienta."""
        pagina = client.get("/ayuda").get_data(as_text=True)
        assert "queda registrado" in pagina

    def test_el_registro_avisa_antes_de_crear_la_cuenta(self, client):
        """Que esté en Ayuda no basta: quien se registra no ha entrado ahí."""
        pagina = client.get("/register").get_data(as_text=True)
        assert "pueden abrir el contenido de cualquier cuenta" in pagina

    def test_el_aviso_va_antes_del_boton(self, client):
        """Un aviso debajo del botón de enviar es un aviso que nadie lee."""
        pagina = client.get("/register").get_data(as_text=True)
        assert pagina.index("aviso-acceso") < pagina.index("register-submit")

    def test_no_se_pide_marcar_una_casilla(self, client):
        """Deliberado: sería consentimiento de pega. Nadie lee lo que hay que
        aceptar para seguir, y convertiría un aviso honesto en un trámite."""
        pagina = client.get("/register").get_data(as_text=True)
        bloque = pagina[pagina.index("aviso-acceso") - 400 : pagina.index("register-submit")]
        assert 'type="checkbox"' not in bloque
