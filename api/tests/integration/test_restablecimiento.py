"""El flujo de restablecimiento de contraseña, de punta a punta.

El test que da sentido al fichero es el primero: hasta el 09/08/2026,
``POST /auth/reset-password`` cambiaba la contraseña de cualquier cuenta
sabiendo solo su dirección. Sin sesión, sin token y sin confirmar nada.

SE PARCHEA ``app.tasks.encolar``, NO EL DEL MÓDULO DE SERVICIO
---------------------------------------------------------------
``restablecimiento.solicitar`` importa ``encolar`` **dentro** de la función
—para evitar un ciclo con Celery—, así que no es un atributo de ese módulo y
``patch("app.services.restablecimiento.encolar")`` falla con ``AttributeError``.

La primera versión de estos tests lo esquivó con ``create=True``, que crea el
atributo si no existe. Eso los hacía pasar **sin parchear nada**: el envío se
producía de verdad y el mock quedaba a un lado, de modo que
``assert not encolar.called`` era cierto siempre, dijera lo que dijera el
código. Dos tests verdes que no comprobaban nada. ``create=True`` no se usa
aquí por eso.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def docente(db):
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="flujo@ejemplo.es", nombre="Flujo", id_rol=rol.id_rol)
    u.set_password("ContrasenaVieja1")
    db.session.add(u)
    db.session.commit()
    return u


def _enlace_enviado(mock_encolar) -> str:
    """Saca el enlace del correo que se encoló."""
    assert mock_encolar.called, "no se encoló ningún envío"
    texto = mock_encolar.call_args.kwargs["texto"]
    for palabra in texto.split():
        if palabra.startswith("http"):
            return palabra
    raise AssertionError(f"no hay enlace en el correo:\n{texto}")


def _token_de(enlace: str) -> str:
    return enlace.split("token=", 1)[1]


class TestElAgujeroEstaCerrado:
    def test_no_se_puede_cambiar_la_contrasena_solo_con_el_correo(self, client, docente):
        """El comportamiento anterior, comprobado desde fuera.

        Si alguien reintrodujera la ruta vieja —o dejara el token como
        opcional—, esto lo detecta.
        """
        respuesta = client.post(
            "/auth/reset-password",
            json={"correo": docente.correo, "nueva_contrasena": "Intrusa123"},
        )
        # 400 y no 422: el manejador de ValidationError de `app/errors.py`
        # responde 400. El esquema rechaza el cuerpo por dos motivos a la vez
        # —falta `token` y `correo` sobra—, que es exactamente lo que se quiere.
        assert respuesta.status_code == 400, respuesta.get_json()
        detalles = respuesta.get_json()["detalles"]
        assert any(d["loc"] == ["token"] for d in detalles), detalles

        # Y, sobre todo: la contraseña no ha cambiado.
        assert docente.check_password("ContrasenaVieja1")

    def test_un_token_inventado_no_sirve(self, client, docente):
        respuesta = client.post(
            "/auth/reset-password",
            json={"token": "esto-no-es-un-token-valido", "nueva_contrasena": "Intrusa123"},
        )
        assert respuesta.status_code == 400
        assert respuesta.get_json()["error"] == "token_invalido"
        assert docente.check_password("ContrasenaVieja1")


class TestNoSeFiltraQuienTieneCuenta:
    def test_la_respuesta_es_identica_exista_o_no_la_cuenta(self, client, docente):
        """Si distinguiera los dos casos, el formulario serviría para averiguar
        qué direcciones tienen cuenta: el paso previo a probar contraseñas."""
        with patch("app.tasks.encolar"):
            existe = client.post(
                "/auth/solicitar-restablecimiento", json={"correo": docente.correo}
            )
            no_existe = client.post(
                "/auth/solicitar-restablecimiento",
                json={"correo": "nadie.tiene.este@ejemplo.es"},
            )

        assert existe.status_code == no_existe.status_code == 202
        assert existe.get_json() == no_existe.get_json()

    def test_una_cuenta_dada_de_baja_tampoco_se_distingue(self, client, db, docente):
        docente.marcar_eliminado()
        db.session.commit()

        with patch("app.tasks.encolar") as encolar:
            respuesta = client.post(
                "/auth/solicitar-restablecimiento", json={"correo": docente.correo}
            )

        assert respuesta.status_code == 202
        assert not encolar.called, "no debe mandarse correo a una cuenta con lápida"


class TestElFlujoCompleto:
    def test_solicitar_y_restablecer(self, client, db, docente):
        with patch("app.tasks.encolar") as encolar:
            client.post(
                "/auth/solicitar-restablecimiento", json={"correo": docente.correo}
            )
            token = _token_de(_enlace_enviado(encolar))

        respuesta = client.post(
            "/auth/reset-password",
            json={"token": token, "nueva_contrasena": "ContrasenaNueva9"},
        )
        assert respuesta.status_code == 200, respuesta.get_json()

        db.session.refresh(docente)
        assert docente.check_password("ContrasenaNueva9")
        assert not docente.check_password("ContrasenaVieja1")

    def test_el_token_no_vale_dos_veces(self, client, db, docente):
        """Un enlace reenviado o guardado en el historial no debe servir dos
        veces. Se consigue sin tabla de tokens: ver app/services/tokens.py."""
        with patch("app.tasks.encolar") as encolar:
            client.post(
                "/auth/solicitar-restablecimiento", json={"correo": docente.correo}
            )
            token = _token_de(_enlace_enviado(encolar))

        primera = client.post(
            "/auth/reset-password",
            json={"token": token, "nueva_contrasena": "PrimeraNueva1"},
        )
        assert primera.status_code == 200

        segunda = client.post(
            "/auth/reset-password",
            json={"token": token, "nueva_contrasena": "SegundaNueva2"},
        )
        assert segunda.status_code == 400
        assert segunda.get_json()["error"] == "token_invalido"

        db.session.refresh(docente)
        assert docente.check_password("PrimeraNueva1")

    def test_una_contrasena_debil_no_gasta_el_token(self, client, db, docente):
        """Detalle de orden que importa.

        Si se asignara la contraseña antes de validarla, el hash cambiaría y el
        token moriría; escribir una contraseña corta obligaría a pedir otro
        enlace. Por eso se valida primero.
        """
        with patch("app.tasks.encolar") as encolar:
            client.post(
                "/auth/solicitar-restablecimiento", json={"correo": docente.correo}
            )
            token = _token_de(_enlace_enviado(encolar))

        floja = client.post(
            "/auth/reset-password",
            json={"token": token, "nueva_contrasena": "todoletras"},
        )
        assert floja.status_code in (400, 422)

        # El mismo token sigue sirviendo.
        buena = client.post(
            "/auth/reset-password",
            json={"token": token, "nueva_contrasena": "AhoraSiVale7"},
        )
        assert buena.status_code == 200, buena.get_json()


class TestElCorreo:
    def test_lleva_un_enlace_absoluto(self, client, app, docente):
        """Un enlace relativo en un cliente de correo no lleva a ningún sitio."""
        with patch("app.tasks.encolar") as encolar:
            client.post(
                "/auth/solicitar-restablecimiento", json={"correo": docente.correo}
            )
            enlace = _enlace_enviado(encolar)

        assert enlace.startswith(app.config["URL_BASE"].rstrip("/"))
        assert "token=" in enlace

    def test_va_en_texto_y_en_html(self, client, docente):
        with patch("app.tasks.encolar") as encolar:
            client.post(
                "/auth/solicitar-restablecimiento", json={"correo": docente.correo}
            )

        kwargs = encolar.call_args.kwargs
        assert kwargs["texto"].strip()
        assert kwargs["html"].strip()
        assert kwargs["destino"] == docente.correo
