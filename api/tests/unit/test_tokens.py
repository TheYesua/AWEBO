"""Tests de los tokens firmados que llegan por correo.

Lo que se comprueba aquí es lo que hoy **no existe** en la aplicación: que para
cambiar una contraseña haga falta algo más que saber un correo. Hasta ahora
``POST /auth/reset-password`` la cambiaba sabiendo solo la dirección, sin
sesión, sin token y sin confirmar nada.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.tokens import (
    CADUCIDAD_RESTABLECER,
    TokenInvalido,
    generar_restablecimiento,
    leer_restablecimiento,
)


@pytest.fixture
def usuario(db):
    """Un usuario cualquiera con contraseña conocida."""
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(
        correo="prueba.tokens@ejemplo.es",
        nombre="Prueba",
        id_rol=rol.id_rol,
    )
    u.set_password("Contrasena1")
    db.session.add(u)
    db.session.commit()
    return u


class TestTokenDeRestablecimiento:
    def test_un_token_recien_emitido_identifica_a_su_usuario(self, app, usuario):
        with app.test_request_context():
            token = generar_restablecimiento(usuario)
            assert leer_restablecimiento(token) == usuario.id_usuario

    def test_al_cambiar_la_contrasena_el_token_muere(self, app, db, usuario):
        """La propiedad que sostiene todo el diseño.

        El token lleva dentro una huella del hash de la contraseña. Al
        cambiarla, el hash cambia, la huella deja de coincidir y el token queda
        inservible **en el mismo instante en que se usa**. Es de un solo uso
        sin guardar nada en la base de datos: ni tabla de tokens, ni limpieza
        de caducados, ni una consulta más por intento.
        """
        with app.test_request_context():
            token = generar_restablecimiento(usuario)
            assert leer_restablecimiento(token) == usuario.id_usuario

            usuario.set_password("OtraDistinta9")
            db.session.commit()

            with pytest.raises(TokenInvalido) as exc:
                leer_restablecimiento(token)
            assert exc.value.motivo == "ya_usado"

    def test_pedir_dos_enlaces_y_usar_uno_invalida_el_otro(self, app, db, usuario):
        """Consecuencia gratuita de lo anterior, y deseable.

        Si alguien pulsa dos veces «he olvidado la contraseña», el enlace viejo
        deja de valer en cuanto se usa el nuevo.
        """
        with app.test_request_context():
            primero = generar_restablecimiento(usuario)
            segundo = generar_restablecimiento(usuario)

            usuario.set_password("TerceraClave3")
            db.session.commit()

            for token in (primero, segundo):
                with pytest.raises(TokenInvalido):
                    leer_restablecimiento(token)

    def test_un_token_manipulado_se_rechaza(self, app, usuario):
        with app.test_request_context():
            token = generar_restablecimiento(usuario)
            with pytest.raises(TokenInvalido):
                leer_restablecimiento(token[:-3] + "AAA")

    def test_un_token_inventado_se_rechaza(self, app):
        with app.test_request_context():
            with pytest.raises(TokenInvalido):
                leer_restablecimiento("esto.no.es.un.token")

    def test_rotar_la_clave_del_servidor_invalida_los_enlaces_pendientes(
        self, app, usuario
    ):
        """Es el comportamiento que se quiere, no un efecto secundario.

        Ante una sospecha de compromiso, cambiar `SECRET_KEY` corta de golpe
        todos los enlaces que anden por ahí.
        """
        with app.test_request_context():
            token = generar_restablecimiento(usuario)
            original = app.config["SECRET_KEY"]
            app.config["SECRET_KEY"] = "otra-clave-distinta"
            try:
                with pytest.raises(TokenInvalido):
                    leer_restablecimiento(token)
            finally:
                app.config["SECRET_KEY"] = original

    def test_caduca_pasado_el_plazo(self, app, usuario):
        """El reloj se simula, y hay un motivo para no dormir de verdad.

        `itsdangerous` guarda la marca de tiempo con **granularidad de un
        segundo**. Un test que durmiera 1,1 s contra un tope de 1 s pasaría o
        fallaría según el momento exacto del reloj en que arrancó: el token
        tendría «1 segundo» de edad, que no es mayor que el tope. Haría falta
        dormir más de dos segundos para que fuera fiable, y aun así sería un
        test lento y frágil. Se comprobó empíricamente antes de escribirlo.
        """
        with app.test_request_context():
            token = generar_restablecimiento(usuario)

            futuro = __import__("time").time() + CADUCIDAD_RESTABLECER + 60
            with patch("itsdangerous.timed.time.time", return_value=futuro):
                with pytest.raises(TokenInvalido) as exc:
                    leer_restablecimiento(token)
            assert exc.value.motivo == "caducado"

    def test_justo_antes_de_caducar_todavia_vale(self, app, usuario):
        """El complemento del anterior: sin esto, un token que caducara
        inmediatamente pasaría el test de caducidad y nadie lo notaría."""
        with app.test_request_context():
            token = generar_restablecimiento(usuario)

            casi = __import__("time").time() + CADUCIDAD_RESTABLECER - 60
            with patch("itsdangerous.timed.time.time", return_value=casi):
                assert leer_restablecimiento(token) == usuario.id_usuario

    def test_una_cuenta_dada_de_baja_no_puede_restablecer(self, app, db, usuario):
        """La lápida se respeta también por esta puerta.

        `resetear_contrasena` ya trataba las cuentas con lápida como
        inexistentes. El camino nuevo tiene que hacer lo mismo, o sería una
        forma de revivir una cuenta esquivando la reclamación.
        """
        with app.test_request_context():
            token = generar_restablecimiento(usuario)
            usuario.marcar_eliminado()
            db.session.commit()

            with pytest.raises(TokenInvalido) as exc:
                leer_restablecimiento(token)
            assert exc.value.motivo == "usuario_inexistente"

    def test_el_token_no_lleva_el_correo_ni_el_hash_en_claro(self, app, usuario):
        """Un enlace de correo acaba en registros de servidores intermedios.

        No debe poder leerse de él ni la dirección ni material derivado de la
        contraseña de forma reutilizable. La carga va firmada pero **no
        cifrada**: cualquiera puede decodificarla.
        """
        with app.test_request_context():
            token = generar_restablecimiento(usuario)

            import base64

            cuerpo = token.split(".")[0]
            relleno = "=" * (-len(cuerpo) % 4)
            visible = base64.urlsafe_b64decode(cuerpo + relleno).decode(
                "utf-8", errors="replace"
            )

            assert usuario.correo not in visible
            assert usuario.contrasena_hash not in visible
