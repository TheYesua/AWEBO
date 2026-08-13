"""Reclamar el contenido de una cuenta dada de baja, con el respaldo decidiendo.

EL ESCENARIO COMPLETO
---------------------
1. Ana usa `jperez@ies.es`, deja su correo personal como respaldo y se da de
   baja conservando el contenido.
2. El instituto reasigna esa dirección a Juan.
3. Juan se registra con ella y ve que hay contenido reclamable.

Hasta ahora eso lo aprobaba un administrador mirando correo, centro y cuántas
SdA hay. Ahora se le pregunta **a Ana**, en su correo personal, que es el único
dato que no se recicla al cambiar de centro.

LO QUE NO RESUELVE, Y HAY QUE DECIRLO
--------------------------------------
Si Ana no dejó respaldo, todo sigue como antes: decide el administrador. El
respaldo es opcional, así que esta protección es opcional también. La interfaz
tiene que decírselo a quien no lo tenga puesto.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services import reclamacion
from app.services.tokens import TokenInvalido


ANTERIOR = "ContrasenaAna1"
INSTITUCIONAL = "jperez@ies.es"
PERSONAL_DE_ANA = "ana.personal@ejemplo.es"


@pytest.fixture
def cuenta_de_ana(db):
    """Con lápida, con contenido y con respaldo verificado."""
    from app.models import Rol, SituacionAprendizaje, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    ana = Usuario(correo=INSTITUCIONAL, nombre="Ana", id_rol=rol.id_rol)
    ana.set_password(ANTERIOR)
    ana.correo_respaldo = PERSONAL_DE_ANA
    ana.correo_respaldo_verificado_en = datetime.now(timezone.utc)
    db.session.add(ana)
    db.session.commit()

    db.session.add(SituacionAprendizaje(
        titulo="El agua en el centro", materia="Matemáticas A", curso="4º ESO",
        id_usuario=ana.id_usuario, contenido={},
    ))
    ana.marcar_eliminado()
    db.session.commit()
    return ana


def _registrarse_reclamando(client):
    """Juan se registra con la dirección heredada y pide el contenido."""
    return client.post("/auth/register", json={
        "correo": INSTITUCIONAL,
        "contrasena": "ContrasenaJuan9",
        "nombre": "Juan", "comunidad_autonoma": "Ceuta",
        "reclamar_contenido": True,
    })


class TestSeLePreguntaAQuienSeFue:
    def test_el_aviso_va_al_respaldo_y_no_a_la_direccion_reclamada(self, client, cuenta_de_ana):
        """El corazón de la tarea.

        Mi primera propuesta era verificar la dirección reclamada, y era mala:
        el enlace habría ido a `jperez@ies.es`, que ahora lee Juan. Habría
        confirmado de buena fe y se habría llevado el trabajo de Ana.
        """
        with patch("app.tasks.encolar") as encolar:
            r = _registrarse_reclamando(client)

        assert r.status_code == 202, r.get_json()
        assert encolar.called
        assert encolar.call_args.kwargs["destino"] == PERSONAL_DE_ANA
        assert encolar.call_args.kwargs["destino"] != INSTITUCIONAL

    def test_no_se_entrega_nada_hasta_que_ana_confirme(self, client, db, cuenta_de_ana):
        with patch("app.tasks.encolar"):
            _registrarse_reclamando(client)

        db.session.refresh(cuenta_de_ana)
        assert cuenta_de_ana.esta_eliminado, "la lápida sigue puesta"
        assert cuenta_de_ana.reclamacion_pendiente is not None
        assert cuenta_de_ana.nombre == "Ana", "los datos de Juan no se han aplicado"

    def test_la_respuesta_no_revela_el_correo_personal_de_ana(self, client, cuenta_de_ana):
        """Quien reclama no tiene por qué enterarse de cuál es la dirección
        personal de otra persona. Se le dice que se ha avisado, no a quién."""
        with patch("app.tasks.encolar"):
            cuerpo = _registrarse_reclamando(client).get_json()

        assert cuerpo.get("avisado_al_respaldo") is True
        assert PERSONAL_DE_ANA not in str(cuerpo)

    def test_el_correo_no_dice_quien_reclama(self, client, cuenta_de_ana):
        """Ana ya no usa AWEBO: no tiene por qué saber con quién comparte
        dirección institucional ahora. Le basta con saber qué se le pide."""
        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            texto = encolar.call_args.kwargs["texto"]

        assert "Juan" not in texto
        assert "situación" in texto, "sí debe decir cuánto contenido hay en juego"


class TestAlConfirmar:
    def _token(self, client, encolar):
        texto = encolar.call_args.kwargs["texto"]
        enlace = next(p for p in texto.split() if p.startswith("http"))
        return enlace.split("token=", 1)[1]

    def test_ana_aprueba_y_juan_recibe_la_cuenta(self, app, client, db, cuenta_de_ana):
        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(client, encolar)

        with app.test_request_context():
            reclamacion.aprobar_por_token(token)

        db.session.refresh(cuenta_de_ana)
        assert not cuenta_de_ana.esta_eliminado
        assert cuenta_de_ana.nombre == "Juan"
        assert cuenta_de_ana.check_password("ContrasenaJuan9")
        assert cuenta_de_ana.reclamacion_pendiente is None

    def test_el_respaldo_de_ana_no_se_queda_en_la_cuenta_de_juan(self, app, client, db, cuenta_de_ana):
        """Lo más fácil de olvidar de todo el flujo.

        Si el respaldo siguiera puesto, Ana conservaría una vía permanente para
        restablecer la contraseña de una cuenta que ya no es suya — y ni ella
        ni Juan tendrían por qué darse cuenta.
        """
        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(client, encolar)

        with app.test_request_context():
            reclamacion.aprobar_por_token(token)

        db.session.refresh(cuenta_de_ana)
        assert cuenta_de_ana.correo_respaldo is None
        assert cuenta_de_ana.tiene_respaldo is False

    def test_un_enlace_de_otro_proposito_no_aprueba_nada(self, app, client, db, cuenta_de_ana):
        from app.services.tokens import generar_restablecimiento

        with patch("app.tasks.encolar"):
            _registrarse_reclamando(client)

        with app.test_request_context():
            ajeno = generar_restablecimiento(cuenta_de_ana)
            with pytest.raises(TokenInvalido):
                reclamacion.aprobar_por_token(ajeno)

        db.session.refresh(cuenta_de_ana)
        assert cuenta_de_ana.esta_eliminado

    def test_aprobar_mata_el_enlace(self, app, client, db, cuenta_de_ana):
        """Sale gratis y conviene dejarlo escrito.

        Al aplicar la reclamación, la contraseña de la cuenta pasa a ser la de
        quien reclamaba, así que la huella del token deja de coincidir y el
        enlace muere solo. Es el mismo mecanismo que hace de un solo uso a los
        de restablecimiento, sin ninguna tabla de tokens gastados.
        """
        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(client, encolar)

        with app.test_request_context():
            reclamacion.aprobar_por_token(token)
            with pytest.raises(TokenInvalido) as exc:
                reclamacion.aprobar_por_token(token)

        assert exc.value.motivo == "ya_usado"

    def test_si_el_administrador_la_rechazo_antes_se_dice_claramente(self, app, client, db, cuenta_de_ana):
        """El caso donde sí aparece «ya se resolvió», y no es raro.

        Rechazar **no** cambia la contraseña —el contenido se queda con su
        lápida—, así que el enlace de Ana sigue verificando pero ya no hay nada
        que autorizar. Fingir un token inválido confundiría a la persona
        legítima, que es justo quien abre ese enlace.

        La primera versión de este test esperaba este error tras *aprobar*, y
        fallaba: allí el enlace muere por la huella antes de llegar a esta
        comprobación. El test enseñó cuál era el escenario de verdad.
        """
        from app.models import Rol, Usuario
        from app.services import admin_service

        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(client, encolar)

        rol = db.session.query(Rol).filter_by(nombre="administrador").first()
        admin = Usuario(correo="admin.rechaza@ejemplo.es", nombre="A", id_rol=rol.id_rol)
        admin.set_password(ANTERIOR)
        db.session.add(admin)
        db.session.commit()

        with app.test_request_context():
            admin_service.resolver_reclamacion(
                cuenta_de_ana.id_usuario, por=admin, aprobar=False
            )
            with pytest.raises(reclamacion.ReclamacionError) as exc:
                reclamacion.aprobar_por_token(token)

        assert exc.value.code == "sin_reclamacion"


class TestSinRespaldoTodoSigueIgual:
    @pytest.fixture
    def sin_respaldo(self, db, cuenta_de_ana):
        cuenta_de_ana.correo_respaldo = None
        cuenta_de_ana.correo_respaldo_verificado_en = None
        db.session.commit()
        return cuenta_de_ana

    def test_no_se_manda_ningun_correo(self, client, sin_respaldo):
        with patch("app.tasks.encolar") as encolar:
            r = _registrarse_reclamando(client)

        assert r.status_code == 202
        assert not encolar.called
        assert r.get_json().get("avisado_al_respaldo") is False

    def test_el_administrador_sigue_pudiendo_aprobarla(self, app, client, db, sin_respaldo):
        """El respaldo es opcional, así que esta vía tiene que seguir viva: es
        el último recurso para quien no lo tenga o haya perdido el acceso."""
        from app.models import Rol, Usuario
        from app.services import admin_service

        with patch("app.tasks.encolar"):
            _registrarse_reclamando(client)

        rol = db.session.query(Rol).filter_by(nombre="administrador").first()
        admin = Usuario(correo="admin.rec@ejemplo.es", nombre="A", id_rol=rol.id_rol)
        admin.set_password(ANTERIOR)
        db.session.add(admin)
        db.session.commit()

        with app.test_request_context():
            admin_service.resolver_reclamacion(
                sin_respaldo.id_usuario, por=admin, aprobar=True
            )

        db.session.refresh(sin_respaldo)
        assert not sin_respaldo.esta_eliminado
        assert sin_respaldo.nombre == "Juan"

    def test_un_respaldo_sin_verificar_no_dispara_el_aviso(self, client, db, sin_respaldo):
        """Escribir la dirección no basta: si contara, cualquiera podría
        apuntar la de otra persona y hacerle llegar esta decisión."""
        sin_respaldo.correo_respaldo = "escrito.a.mano@ejemplo.es"
        db.session.commit()

        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)

        assert not encolar.called


class TestElEndpointYLaPantalla:
    """La capa HTTP: lo que ve quien abre el enlace desde su buzón."""

    def _token(self, encolar):
        texto = encolar.call_args.kwargs["texto"]
        return next(p for p in texto.split() if p.startswith("http")).split("token=", 1)[1]

    def test_la_pantalla_se_abre_sin_sesion(self, client, cuenta_de_ana):
        """Lo importante del endpoint y de la página.

        Quien recibe este enlace **se dio de baja**: no tiene sesión que
        iniciar. Un `login_required` aquí, copiado por costumbre del resto del
        panel, dejaría el enlace inservible justo para su único destinatario.
        """
        r = client.get("/reclamacion?token=loquesea")
        assert r.status_code == 200

    def test_aprobar_sin_sesion_funciona(self, client, db, cuenta_de_ana):
        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(encolar)

        client.delete_cookie("session")
        r = client.post("/auth/aprobar-reclamacion", json={"token": token})

        assert r.status_code == 200, r.get_json()
        assert r.get_json()["situaciones"] == 1
        db.session.refresh(cuenta_de_ana)
        assert not cuenta_de_ana.esta_eliminado

    def test_la_respuesta_no_dice_a_quien_se_le_entrega(self, client, cuenta_de_ana):
        """Simétrico al secreto que se guarda en la otra dirección: quien
        aprueba tampoco necesita saber quién recibe la cuenta."""
        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(encolar)

        cuerpo = client.post("/auth/aprobar-reclamacion", json={"token": token}).get_json()
        assert "Juan" not in str(cuerpo)

    def test_un_token_falso_da_400_y_no_toca_nada(self, client, db, cuenta_de_ana):
        with patch("app.tasks.encolar"):
            _registrarse_reclamando(client)

        r = client.post("/auth/aprobar-reclamacion", json={"token": "x" * 40})

        assert r.status_code == 400
        assert r.get_json()["error"] == "token_invalido"
        db.session.refresh(cuenta_de_ana)
        assert cuenta_de_ana.esta_eliminado

    def test_ya_resuelta_da_409_y_no_400(self, client, db, cuenta_de_ana):
        """La diferencia importa para quien lo lee.

        400 dice «tu enlace no vale»; 409 dice «tu enlace vale, pero esto ya se
        decidió». Quien abre este enlace es la persona legítima: mandarla a
        pedir uno nuevo que nadie va a emitir sería dejarla sin salida.
        """
        from app.models import Rol, Usuario
        from app.services import admin_service

        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(encolar)

        rol = db.session.query(Rol).filter_by(nombre="administrador").first()
        admin = Usuario(correo="admin.409@ejemplo.es", nombre="A", id_rol=rol.id_rol)
        admin.set_password(ANTERIOR)
        db.session.add(admin)
        db.session.commit()
        admin_service.resolver_reclamacion(cuenta_de_ana.id_usuario, por=admin, aprobar=False)

        r = client.post("/auth/aprobar-reclamacion", json={"token": token})

        assert r.status_code == 409
        assert r.get_json()["error"] == "sin_reclamacion"

    def test_el_endpoint_no_acepta_campos_de_mas(self, client, cuenta_de_ana):
        """`extra="forbid"` no es cosmético aquí.

        Si el cuerpo pudiera llevar un id o un correo, quien tuviera el enlace
        podría apuntarlo a otra cuenta. Lo único que aporta esta pantalla es
        un «sí» a algo que ya estaba decidido.
        """
        with patch("app.tasks.encolar") as encolar:
            _registrarse_reclamando(client)
            token = self._token(encolar)

        r = client.post(
            "/auth/aprobar-reclamacion",
            json={"token": token, "id_usuario": 999},
        )
        assert r.status_code == 400
