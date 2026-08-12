"""Ofrecer el correo de respaldo al registrarse.

POR QUÉ AQUÍ Y NO SOLO EN EL PERFIL
------------------------------------
El respaldo hace falta en momentos que nunca se ven venir: una baja, un cambio
de centro, alguien reclamando tu contenido. Todos son posteriores al registro, y
quien no lo puso el primer día casi nunca entra al perfil a ponerlo *antes* de
necesitarlo. Ofrecerlo aquí es la única forma de que lo tenga quien lo va a
necesitar.

LA REGLA QUE NO CAMBIA
-----------------------
Aunque se dé al registrarse, **no se guarda sin confirmar**. Se manda el enlace
y ya. Guardarlo a ciegas permitiría apuntar al registrarse la dirección de otra
persona y hacerle llegar los enlaces de una cuenta que no es suya.
"""
from __future__ import annotations

from unittest.mock import patch



NUEVO = "nuevo@ies.es"
PERSONAL = "yo.personal@ejemplo.es"
CLAVE = "ContrasenaNueva1"


def _registrar(client, **extra):
    cuerpo = {"correo": NUEVO, "contrasena": CLAVE, "nombre": "Quien Sea"}
    cuerpo.update(extra)
    return client.post("/auth/register", json=cuerpo)


class TestEsOpcional:
    def test_sin_respaldo_el_registro_va_como_siempre(self, client, db):
        """Lo primero que hay que proteger: que añadir esto no rompa el alta
        normal, que es la mayoritaria."""
        with patch("app.tasks.encolar") as encolar:
            r = _registrar(client)

        assert r.status_code == 201, r.get_json()
        assert r.get_json()["respaldo_pendiente"] is False
        assert not encolar.called

    def test_con_respaldo_se_manda_el_enlace(self, client, db):
        with patch("app.tasks.encolar") as encolar:
            r = _registrar(client, correo_respaldo=PERSONAL)

        assert r.status_code == 201, r.get_json()
        assert encolar.called
        assert encolar.call_args.kwargs["destino"] == PERSONAL

    def test_se_avisa_de_que_queda_pendiente(self, client, db):
        """Sin este dato la pantalla saltaría al perfil en silencio y quien lo
        pidió creería tenerlo puesto. Un respaldo sin confirmar no cuenta para
        nada, así que creerlo puesto es peor que saber que falta."""
        with patch("app.tasks.encolar"):
            cuerpo = _registrar(client, correo_respaldo=PERSONAL).get_json()

        assert cuerpo["respaldo_pendiente"] is True


class TestNoSeGuardaSinConfirmar:
    def test_la_cuenta_nace_sin_respaldo(self, client, db):
        from app.models import Usuario

        with patch("app.tasks.encolar"):
            _registrar(client, correo_respaldo=PERSONAL)

        u = db.session.query(Usuario).filter_by(correo=NUEVO).one()
        assert u.correo_respaldo is None
        assert u.tiene_respaldo is False

    def test_solo_cuenta_tras_abrir_el_enlace(self, client, db):
        from app.models import Usuario

        with patch("app.tasks.encolar") as encolar:
            _registrar(client, correo_respaldo=PERSONAL)
            texto = encolar.call_args.kwargs["texto"]
            token = next(p for p in texto.split() if p.startswith("http")).split("token=", 1)[1]

        assert client.post("/auth/confirmar-respaldo", json={"token": token}).status_code == 200

        u = db.session.query(Usuario).filter_by(correo=NUEVO).one()
        assert u.correo_respaldo == PERSONAL
        assert u.tiene_respaldo is True


class TestLoQueSeRechaza:
    def test_el_mismo_correo_de_la_cuenta_no_vale(self, client, db):
        """Y se rechaza **antes** de crear nada.

        `respaldo.solicitar` lo rechazaría igual, pero con la cuenta ya creada:
        el registro habría salido bien, el respaldo no, y nadie se enteraría
        hasta buscar en el buzón un correo que nunca se envió.
        """
        from app.models import Usuario

        r = _registrar(client, correo_respaldo=NUEVO)

        assert r.status_code == 409
        assert r.get_json()["error"] == "respaldo_igual_al_principal"
        assert db.session.query(Usuario).filter_by(correo=NUEVO).first() is None

    def test_una_direccion_con_forma_invalida_da_400(self, client, db):
        from app.models import Usuario

        r = _registrar(client, correo_respaldo="esto-no-es-un-correo")

        assert r.status_code == 400
        assert db.session.query(Usuario).filter_by(correo=NUEVO).first() is None

    def test_al_reclamar_una_cuenta_ajena_no_se_toca_su_respaldo(self, client, db):
        """El caso torcido, y el que más importa.

        Quien se registra con la dirección de una cuenta dada de baja no tiene
        todavía esa cuenta: la solicitud está pendiente. Si su respaldo se
        aplicara ya, estaría poniendo su propia dirección de recuperación en
        una cuenta que aún es de otra persona — y encima sería el respaldo con
        el que se le pide permiso a esa otra persona.
        """
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        anterior = Usuario(correo=NUEVO, nombre="Anterior", id_rol=rol.id_rol)
        anterior.set_password("ContrasenaVieja1")
        db.session.add(anterior)
        db.session.commit()
        anterior.marcar_eliminado()
        db.session.commit()

        with patch("app.tasks.encolar"):
            r = _registrar(client, correo_respaldo=PERSONAL, reclamar_contenido=True)

        assert r.status_code == 202
        db.session.refresh(anterior)
        assert anterior.correo_respaldo is None
        assert PERSONAL not in str(anterior.reclamacion_pendiente)


class TestSiElCorreoNoSale:
    """El caso que encontró un fallo de verdad.

    La primera versión del código solo capturaba `RespaldoError` alrededor del
    envío. Con la cola caída saltaba un `RuntimeError`, que se llevaba por
    delante la petición entera: la cuenta quedaba **creada**, la respuesta era
    un 500, y al reintentar salía «correo_duplicado». Es decir, justo el
    desastre que el comentario de ese bloque decía estar evitando.
    """

    def test_el_registro_sale_bien_aunque_el_correo_no(self, client, db):
        from app.models import Usuario

        with patch("app.tasks.encolar", side_effect=RuntimeError("cola caída")):
            r = _registrar(client, correo_respaldo=PERSONAL)

        assert r.status_code == 201, r.get_json()
        assert db.session.query(Usuario).filter_by(correo=NUEVO).first() is not None

    def test_no_se_manda_a_mirar_un_buzon_vacio(self, client, db):
        """`respaldo_pendiente` dice lo que **se envió**, no lo que se pidió.

        Si dijera lo segundo, la pantalla mandaría a buscar un enlace que no
        existe, y la persona se quedaría esperando en vez de volver a
        intentarlo desde su perfil.
        """
        with patch("app.tasks.encolar", side_effect=RuntimeError("cola caída")):
            cuerpo = _registrar(client, correo_respaldo=PERSONAL).get_json()

        assert cuerpo["respaldo_pendiente"] is False
