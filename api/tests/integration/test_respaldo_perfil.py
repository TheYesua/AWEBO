"""La capa HTTP del correo de respaldo: ponerlo, cambiarlo, verlo y quitarlo.

`test_respaldo.py` ya cubre el servicio —la regla de a quién se avisa, qué se
rechaza, qué se guarda—. Aquí se prueba lo que el servicio no puede saber:
quién puede llamar, qué se devuelve al navegador y qué **no** se devuelve.

Lo que más se prueba en este fichero es una decisión que parece cosmética y no
lo es: la dirección se sirve enmascarada. El razonamiento está en
`services/respaldo.enmascarar`, y se resume en que el respaldo es lo único que
tener la sesión no da, así que enseñarlo entero le regalaría a quien robe una
sesión el siguiente objetivo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.respaldo import enmascarar


PERSONAL = "ana.perez@ejemplo.es"
OTRO = "otro.buzon@ejemplo.es"
CLAVE = "ContrasenaAna1"


@pytest.fixture
def ana(db):
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="ana@ies.es", nombre="Ana", id_rol=rol.id_rol)
    u.set_password(CLAVE)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def sesion(client, ana):
    client.post("/auth/login", json={"correo": "ana@ies.es", "contrasena": CLAVE})
    return client


def _con_respaldo(db, usuario, correo=PERSONAL):
    usuario.correo_respaldo = correo
    usuario.correo_respaldo_verificado_en = datetime.now(timezone.utc)
    db.session.commit()
    return usuario


class TestEnmascarar:
    """Función pura, así que se prueba directamente y sin base de datos."""

    @pytest.mark.parametrize(
        "entrada, esperado",
        [
            ("ana.perez@ejemplo.es", "a*******z@ejemplo.es"),
            ("ab@ejemplo.es", "a*@ejemplo.es"),
            ("a@ejemplo.es", "a*@ejemplo.es"),
            (None, None),
        ],
    )
    def test_casos(self, entrada, esperado):
        assert enmascarar(entrada) == esperado

    def test_el_dominio_se_ve_entero(self):
        """A propósito: es lo que permite reconocer la dirección de un vistazo
        y lo menos identificativo de ella."""
        assert enmascarar("cualquiera@gmail.com").endswith("@gmail.com")

    def test_no_deja_pasar_la_direccion_original(self):
        assert "ana.perez" not in enmascarar("ana.perez@ejemplo.es")

    def test_una_cadena_sin_arroba_no_se_filtra_entera(self):
        """No debería llegar nunca —hay validación de correo antes—, pero si
        llegara, lo peor sería devolverla tal cual creyendo haberla tapado."""
        assert enmascarar("esto-no-es-un-correo") == "*" * len("esto-no-es-un-correo")


class TestVerlo:
    def test_sin_sesion_no_se_ve(self, client, ana):
        assert client.get("/me/correo-de-respaldo").status_code == 401

    def test_sin_respaldo_dice_que_no_hay(self, sesion):
        cuerpo = sesion.get("/me/correo-de-respaldo").get_json()
        assert cuerpo == {"correo": None, "verificado": False, "verificado_en": None}

    def test_con_respaldo_llega_enmascarado(self, db, sesion, ana):
        _con_respaldo(db, ana)
        cuerpo = sesion.get("/me/correo-de-respaldo").get_json()

        assert cuerpo["verificado"] is True
        assert cuerpo["correo"] != PERSONAL
        assert "ana.perez" not in str(cuerpo)
        assert cuerpo["correo"].endswith("@ejemplo.es")

    def test_escrito_pero_sin_verificar_se_distingue(self, db, sesion, ana):
        """El estado que más engaña.

        Quien tiene una dirección escrita y sin confirmar cree estar protegido
        y no lo está: un respaldo sin verificar no cuenta para nada. Si la
        respuesta no distinguiera los dos casos, la pantalla tampoco podría.
        """
        ana.correo_respaldo = PERSONAL
        ana.correo_respaldo_verificado_en = None
        db.session.commit()

        cuerpo = sesion.get("/me/correo-de-respaldo").get_json()
        assert cuerpo["correo"] is not None
        assert cuerpo["verificado"] is False

    def test_el_respaldo_no_se_cuela_en_el_perfil_general(self, db, sesion, ana):
        """`/me` lo consumen varias pantallas y el mismo esquema se sirve en el
        panel de administración. Meter ahí la dirección la repartiría por todas
        ellas de golpe, que es justo lo que se quiso evitar dándole endpoint
        propio."""
        _con_respaldo(db, ana)
        assert PERSONAL not in str(sesion.get("/me").get_json())


class TestPonerlo:
    def test_sin_sesion_no_se_puede(self, client, ana):
        r = client.post("/me/correo-de-respaldo", json={"correo": PERSONAL})
        assert r.status_code == 401

    def test_el_primero_va_a_la_direccion_nueva(self, sesion, ana):
        with patch("app.tasks.encolar") as encolar:
            r = sesion.post("/me/correo-de-respaldo", json={"correo": PERSONAL})

        assert r.status_code == 202
        assert encolar.call_args.kwargs["destino"] == PERSONAL
        assert r.get_json()["era_cambio"] is False

    def test_el_cambio_va_al_respaldo_ANTERIOR(self, db, sesion, ana):
        """La regla que sostiene todo lo demás.

        Sin ella, quien se apodere del correo del centro restablece la
        contraseña, entra, pone su propio respaldo y se queda la cuenta para
        siempre. Con ella, se queda encerrado fuera de la única vía que
        probaría identidad.
        """
        _con_respaldo(db, ana)

        with patch("app.tasks.encolar") as encolar:
            r = sesion.post("/me/correo-de-respaldo", json={"correo": OTRO})

        assert encolar.call_args.kwargs["destino"] == PERSONAL
        assert encolar.call_args.kwargs["destino"] != OTRO
        assert r.get_json()["era_cambio"] is True

    def test_se_dice_adonde_se_envio_y_enmascarado(self, db, sesion, ana):
        """Sin esto, quien cambia el respaldo esperaría el correo en el buzón
        nuevo y no le llegaría nunca: va al anterior."""
        _con_respaldo(db, ana)

        with patch("app.tasks.encolar"):
            cuerpo = sesion.post("/me/correo-de-respaldo", json={"correo": OTRO}).get_json()

        assert cuerpo["enviado_a"] == enmascarar(PERSONAL)
        assert cuerpo["enviado_a"] != PERSONAL

    def test_no_se_guarda_nada_hasta_confirmar(self, db, sesion, ana):
        with patch("app.tasks.encolar"):
            sesion.post("/me/correo-de-respaldo", json={"correo": PERSONAL})

        db.session.refresh(ana)
        assert ana.correo_respaldo is None

    def test_el_correo_principal_se_rechaza_con_motivo(self, sesion, ana):
        with patch("app.tasks.encolar") as encolar:
            r = sesion.post("/me/correo-de-respaldo", json={"correo": "ana@ies.es"})

        assert r.status_code == 409
        assert r.get_json()["error"] == "igual_al_principal"
        assert not encolar.called

    def test_una_direccion_con_forma_invalida_da_400(self, sesion, ana):
        r = sesion.post("/me/correo-de-respaldo", json={"correo": "no-es-un-correo"})
        assert r.status_code == 400


class TestConfirmarlo:
    def _token(self, encolar):
        texto = encolar.call_args.kwargs["texto"]
        return next(p for p in texto.split() if p.startswith("http")).split("token=", 1)[1]

    def test_la_pantalla_se_abre_sin_sesion(self, client):
        assert client.get("/correo-de-respaldo?token=x").status_code == 200

    def test_confirmar_sin_sesion_funciona(self, client, db, sesion, ana):
        """No es una comodidad: al **cambiar** el respaldo el enlace llega al
        buzón anterior, que puede estar abierto en otro navegador o incluso
        pertenecer a otra persona. Un `login_required` aquí lo rompería."""
        with patch("app.tasks.encolar") as encolar:
            sesion.post("/me/correo-de-respaldo", json={"correo": PERSONAL})
            token = self._token(encolar)

        sesion.delete_cookie("session")
        r = sesion.post("/auth/confirmar-respaldo", json={"token": token})

        assert r.status_code == 200, r.get_json()
        db.session.refresh(ana)
        assert ana.correo_respaldo == PERSONAL
        assert ana.tiene_respaldo is True

    def test_la_respuesta_tambien_va_enmascarada(self, sesion, ana):
        with patch("app.tasks.encolar") as encolar:
            sesion.post("/me/correo-de-respaldo", json={"correo": PERSONAL})
            token = self._token(encolar)

        cuerpo = sesion.post("/auth/confirmar-respaldo", json={"token": token}).get_json()
        assert cuerpo["correo"] == enmascarar(PERSONAL)

    def test_la_direccion_no_se_acepta_desde_el_cuerpo(self, sesion, ana):
        """`extra="forbid"` con un motivo concreto.

        Si la dirección pudiera mandarse aparte del token, quien interceptara
        un enlace podría apuntarlo a un buzón suyo — exactamente lo que la
        regla del respaldo anterior existe para impedir.
        """
        with patch("app.tasks.encolar") as encolar:
            sesion.post("/me/correo-de-respaldo", json={"correo": PERSONAL})
            token = self._token(encolar)

        r = sesion.post(
            "/auth/confirmar-respaldo", json={"token": token, "correo": "mio@malo.es"}
        )
        assert r.status_code == 400

    def test_un_token_de_otro_proposito_no_vale(self, app, sesion, ana):
        from app.services.tokens import generar_restablecimiento

        with app.test_request_context():
            ajeno = generar_restablecimiento(ana)

        r = sesion.post("/auth/confirmar-respaldo", json={"token": ajeno})
        assert r.status_code == 400
        assert r.get_json()["error"] == "token_invalido"


class TestQuitarlo:
    def test_basta_la_contrasena(self, db, sesion, ana):
        _con_respaldo(db, ana)

        with patch("app.tasks.encolar") as encolar:
            r = sesion.post("/me/correo-de-respaldo/quitar", json={"contrasena": CLAVE})

        assert r.status_code == 200
        db.session.refresh(ana)
        assert ana.correo_respaldo is None
        assert not encolar.called, "quitarlo no manda ningún enlace, al revés que cambiarlo"

    def test_con_la_contrasena_mal_no_se_quita(self, db, sesion, ana):
        _con_respaldo(db, ana)

        r = sesion.post("/me/correo-de-respaldo/quitar", json={"contrasena": "otra"})

        assert r.status_code == 409
        db.session.refresh(ana)
        assert ana.correo_respaldo == PERSONAL

    def test_sin_sesion_no_se_puede(self, client, db, ana):
        _con_respaldo(db, ana)
        r = client.post("/me/correo-de-respaldo/quitar", json={"contrasena": CLAVE})
        assert r.status_code == 401

    def test_se_puede_quitar_uno_sin_verificar(self, db, sesion, ana):
        """El caso que justifica la asimetría entera.

        Si quitarlo exigiera también el enlace, quien perdiera el acceso a su
        correo personal no podría cambiarlo **ni quitarlo**, y se quedaría con
        un respaldo muerto para siempre.
        """
        ana.correo_respaldo = PERSONAL
        ana.correo_respaldo_verificado_en = None
        db.session.commit()

        r = sesion.post("/me/correo-de-respaldo/quitar", json={"contrasena": CLAVE})

        assert r.status_code == 200
        db.session.refresh(ana)
        assert ana.correo_respaldo is None
