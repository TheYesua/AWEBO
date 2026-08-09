"""Tests del envío de correo.

El más importante es el primero: que el proveedor por defecto no mande nada.
Todo lo demás son comodidades; eso es lo que evita que un entorno de
desarrollo con credenciales heredadas escriba a una dirección real.
"""
from __future__ import annotations

import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.correo import CorreoError, Mensaje, obtener_proveedor
from app.correo.consola import ProveedorConsola
from app.correo.smtp import ProveedorSmtp


@pytest.fixture
def mensaje():
    return Mensaje(
        destino="docente@ejemplo.es",
        asunto="Restablecer tu contraseña",
        texto="Abre este enlace: https://ejemplo.es/x/abc",
        html="<p>Abre <a href='https://ejemplo.es/x/abc'>este enlace</a></p>",
    )


class TestElDefectoNoEnvia:
    def test_sin_configurar_nada_el_proveedor_es_el_de_consola(self, app):
        """Si el defecto fuera SMTP, bastaría con arrancar el entorno con unas
        credenciales heredadas para mandar correo de verdad a direcciones de
        prueba. Al revés no pasa nada."""
        with app.test_request_context():
            app.config.pop("CORREO_PROVEEDOR", None)
            assert isinstance(obtener_proveedor(), ProveedorConsola)

    def test_el_de_consola_no_abre_ninguna_conexion(self, app, mensaje):
        """No basta con que no lance error: hay que ver que no toca la red."""
        with app.test_request_context():
            with patch("smtplib.SMTP") as smtp, patch("smtplib.SMTP_SSL") as ssl_:
                ProveedorConsola().enviar(mensaje)
            smtp.assert_not_called()
            ssl_.assert_not_called()

    def test_el_de_consola_deja_el_mensaje_en_el_registro(self, app, mensaje, caplog):
        """En desarrollo es la única forma de completar un restablecimiento.

        Si el texto no sale en el log, el flujo queda inaccesible sin servidor
        de correo, que es justo lo que este proveedor viene a resolver.
        """
        import logging

        with app.test_request_context():
            with caplog.at_level(logging.WARNING, logger="correo.consola"):
                ProveedorConsola().enviar(mensaje)

        registrado = caplog.text
        assert mensaje.destino in registrado
        assert mensaje.asunto in registrado
        assert "https://ejemplo.es/x/abc" in registrado


class TestFactoria:
    def test_se_puede_pedir_smtp_explicitamente(self, app):
        with app.test_request_context():
            app.config["CORREO_PROVEEDOR"] = "smtp"
            assert isinstance(obtener_proveedor(), ProveedorSmtp)

    def test_un_nombre_desconocido_cae_a_consola_y_avisa(self, app, caplog):
        """Una errata en una variable de entorno no debe tumbar el arranque
        por algo que solo afecta al correo. Pero tampoco pasar inadvertida."""
        import logging

        with app.test_request_context():
            app.config["CORREO_PROVEEDOR"] = "mailgun-typo"
            with caplog.at_level(logging.WARNING, logger="correo.factoria"):
                proveedor = obtener_proveedor()

        assert isinstance(proveedor, ProveedorConsola)
        assert "mailgun-typo" in caplog.text


class TestSmtp:
    def test_sin_servidor_configurado_falla_claro(self, app, mensaje):
        with app.test_request_context():
            app.config["SMTP_HOST"] = ""
            with pytest.raises(CorreoError, match="SMTP_HOST"):
                ProveedorSmtp().enviar(mensaje)

    def test_el_puerto_465_usa_TLS_directo_y_el_587_STARTTLS(self, app, mensaje):
        """Confundirlos da un error de protocolo que no dice nada.

        El 465 habla TLS desde el primer byte; el 587 empieza en claro y sube
        con STARTTLS. Se elige por el puerto, así que conviene comprobar que la
        elección es la que se cree.
        """
        with app.test_request_context():
            # `SMTP_SIN_TLS` explícito aunque `TestConfig` ya lo fije: este
            # test trata precisamente de cuándo se negocia el cifrado, y
            # dejarlo implícito es lo que hizo que fallara solo dentro del
            # contenedor, donde la variable vale 1 para el buzón de pruebas.
            app.config.update(SMTP_HOST="correo.ejemplo.es", SMTP_USER="",
                              SMTP_PASSWORD="", SMTP_SIN_TLS=False)

            app.config["SMTP_PORT"] = 465
            with patch("smtplib.SMTP_SSL") as directo, patch("smtplib.SMTP") as normal:
                directo.return_value.__enter__.return_value = MagicMock()
                ProveedorSmtp().enviar(mensaje)
            directo.assert_called_once()
            normal.assert_not_called()

            app.config["SMTP_PORT"] = 587
            with patch("smtplib.SMTP") as normal, patch("smtplib.SMTP_SSL") as directo:
                cliente = MagicMock()
                normal.return_value.__enter__.return_value = cliente
                ProveedorSmtp().enviar(mensaje)
            normal.assert_called_once()
            directo.assert_not_called()
            cliente.starttls.assert_called_once()

    def test_siempre_se_pasa_un_tiempo_de_espera(self, app, mensaje):
        """Sin él, smtplib espera lo que diga el sistema operativo —minutos— y
        deja bloqueado el worker de Celery que hace el envío, sin que nadie lo
        note."""
        with app.test_request_context():
            app.config.update(SMTP_HOST="correo.ejemplo.es", SMTP_PORT=587,
                              SMTP_USER="", SMTP_PASSWORD="", SMTP_TIMEOUT=7)
            with patch("smtplib.SMTP") as normal:
                normal.return_value.__enter__.return_value = MagicMock()
                ProveedorSmtp().enviar(mensaje)

            assert normal.call_args.kwargs.get("timeout") == 7

    def test_un_fallo_de_red_se_traduce_a_CorreoError(self, app, mensaje):
        """Quien llama no debe tener que conocer las excepciones de smtplib."""
        with app.test_request_context():
            app.config.update(SMTP_HOST="correo.ejemplo.es", SMTP_PORT=587)
            with patch("smtplib.SMTP", side_effect=OSError("sin ruta al host")):
                with pytest.raises(CorreoError):
                    ProveedorSmtp().enviar(mensaje)

    def test_el_error_registrado_no_lleva_la_direccion(self, app, mensaje, caplog):
        """Estos registros acaban en sitios donde no debería haber correos de
        usuarios, y el mensaje de una excepción de smtplib suele incluir el
        destinatario."""
        import logging

        with app.test_request_context():
            app.config.update(SMTP_HOST="correo.ejemplo.es", SMTP_PORT=587)
            with caplog.at_level(logging.ERROR, logger="correo.smtp"):
                with patch("smtplib.SMTP",
                           side_effect=OSError(f"no such user {mensaje.destino}")):
                    with pytest.raises(CorreoError):
                        ProveedorSmtp().enviar(mensaje)

        assert mensaje.destino not in caplog.text

    def test_sin_tls_y_con_usuario_se_niega_a_enviar(self, app, mensaje):
        """La peor combinación posible, y la más fácil de alcanzar por error.

        El LOGIN de SMTP manda usuario y contraseña en base64, que no es
        cifrado sino codificación: cualquiera en el camino las lee. Se llega
        aquí dejándose puesta la variable del buzón local al configurar un
        proveedor de verdad, así que el código corta antes de conectar.
        """
        with app.test_request_context():
            app.config.update(SMTP_HOST="correo.ejemplo.es", SMTP_PORT=587,
                              SMTP_USER="alguien", SMTP_PASSWORD="secreta",
                              SMTP_SIN_TLS=True)
            with patch("smtplib.SMTP") as normal:
                with pytest.raises(CorreoError, match="claro"):
                    ProveedorSmtp().enviar(mensaje)
            # Y no llega a abrir la conexión: no basta con lanzar el error
            # después de haber mandado ya las credenciales.
            normal.assert_not_called()

    def test_el_mensaje_va_en_texto_y_en_html(self, app, mensaje):
        """Hay clientes que bloquean el HTML por defecto. Un enlace de
        restablecimiento que no se puede pulsar deja la cuenta inaccesible."""
        with app.test_request_context():
            app.config.update(SMTP_HOST="correo.ejemplo.es", SMTP_PORT=587,
                              SMTP_USER="", SMTP_PASSWORD="")
            with patch("smtplib.SMTP") as normal:
                cliente = MagicMock()
                normal.return_value.__enter__.return_value = cliente
                ProveedorSmtp().enviar(mensaje)

            enviado = cliente.send_message.call_args.args[0]
            tipos = {parte.get_content_type() for parte in enviado.walk()}
            assert "text/plain" in tipos
            assert "text/html" in tipos


class ServidorFalso(threading.Thread):
    """Un servidor SMTP de verdad, mínimo y que NO ofrece STARTTLS.

    POR QUÉ UN SERVIDOR Y NO OTRO SIMULACRO
    ---------------------------------------
    Todo lo de arriba parchea ``smtplib``, así que comprueba lo que el código
    *decide*, nunca lo que pasa al hablar con algo al otro lado. El fallo que
    motivó esta clase no se ve desde un simulacro: ``cliente.starttls()`` se
    llamaba siempre, y contra un servidor que no anuncia la extensión
    ``smtplib`` lanza ``SMTPNotSupportedError`` sin llegar a mandar el comando.
    El buzón de pruebas local es exactamente ese caso —Mailpit no ofrece
    STARTTLS salvo que se le den certificados—, de modo que el envío fallaba
    entero y la bandeja se quedaba vacía.

    Habla lo justo del protocolo para que ``send_message`` termine, y guarda lo
    recibido en ``recibido`` para poder mirarlo.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.puerto = self.sock.getsockname()[1]
        self.recibido: str | None = None
        self.comandos: list[str] = []

    def run(self) -> None:
        cliente, _ = self.sock.accept()
        with cliente, cliente.makefile("rwb") as f:
            f.write(b"220 prueba.local ESMTP\r\n")
            f.flush()
            en_datos = False
            cuerpo: list[str] = []
            while True:
                linea = f.readline()
                if not linea:
                    break
                texto = linea.decode("utf-8", "replace").rstrip("\r\n")

                if en_datos:
                    if texto == ".":
                        en_datos = False
                        self.recibido = "\n".join(cuerpo)
                        f.write(b"250 2.0.0 Ok\r\n")
                        f.flush()
                    else:
                        cuerpo.append(texto)
                    continue

                self.comandos.append(texto)
                orden = texto.split(" ", 1)[0].upper()
                if orden == "EHLO":
                    # Sin STARTTLS en la lista: eso es lo que se está probando.
                    f.write(b"250-prueba.local\r\n250 8BITMIME\r\n")
                elif orden in {"HELO", "MAIL", "RCPT", "NOOP", "RSET"}:
                    f.write(b"250 2.0.0 Ok\r\n")
                elif orden == "DATA":
                    en_datos = True
                    f.write(b"354 Adelante\r\n")
                elif orden == "QUIT":
                    f.write(b"221 2.0.0 Adios\r\n")
                    f.flush()
                    break
                else:
                    f.write(b"502 5.5.1 No implementado\r\n")
                f.flush()

    def __enter__(self) -> "ServidorFalso":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.sock.close()
        self.join(timeout=5)


class TestContraUnServidorDeVerdad:
    """El camino de SMTP ejercitado sin parchear nada."""

    def test_contra_un_servidor_sin_starttls_el_envio_falla(self, app, mensaje):
        """Este es el fallo, visto tal cual lo vería el buzón local.

        Con la configuración normal el código exige STARTTLS. Contra un
        servidor que no lo anuncia no hay negociación posible y no sale nada.
        Que falle está bien: lo que no puede es fallar *en silencio*.
        """
        with ServidorFalso() as servidor:
            with app.test_request_context():
                app.config.update(SMTP_HOST="127.0.0.1", SMTP_PORT=servidor.puerto,
                                  SMTP_USER="", SMTP_PASSWORD="", SMTP_TIMEOUT=5,
                                  SMTP_SIN_TLS=False)
                with pytest.raises(CorreoError):
                    ProveedorSmtp().enviar(mensaje)

        assert servidor.recibido is None, "no debería haber entregado el mensaje"

    def test_con_SMTP_SIN_TLS_el_mensaje_llega_entero(self, app, mensaje):
        """El mismo servidor, la misma configuración salvo la renuncia
        explícita al cifrado, y el correo llega con sus dos partes y su enlace.

        Es el único test del proyecto que ve un mensaje salir por un socket.
        """
        with ServidorFalso() as servidor:
            with app.test_request_context():
                app.config.update(SMTP_HOST="127.0.0.1", SMTP_PORT=servidor.puerto,
                                  SMTP_USER="", SMTP_PASSWORD="", SMTP_TIMEOUT=5,
                                  SMTP_SIN_TLS=True,
                                  CORREO_REMITENTE="awebo@ejemplo.es")
                ProveedorSmtp().enviar(mensaje)

        assert servidor.recibido is not None, "el servidor no recibió nada"

        # Se parsea en vez de buscar cadenas sueltas. El asunto lleva una eñe y
        # viaja codificado —`=?utf-8?q?contrase=C3=B1a?=`—, así que buscarlo tal
        # cual falla aunque haya llegado bien. Parseando se comprueba lo que de
        # verdad importa: que un cliente de correo pueda reconstruirlo.
        from email import message_from_string
        from email.header import decode_header, make_header

        correo = message_from_string(servidor.recibido)
        assert str(make_header(decode_header(correo["Subject"]))) == mensaje.asunto
        assert correo["To"] == mensaje.destino

        partes = {p.get_content_type(): p.get_payload(decode=True).decode("utf-8")
                  for p in correo.walk() if not p.is_multipart()}
        assert set(partes) == {"text/plain", "text/html"}
        # El enlace es lo único que el usuario necesita: si se perdiera por el
        # camino, el correo llegaría y el restablecimiento seguiría siendo
        # imposible. En las dos partes, porque hay clientes que bloquean el HTML.
        assert all("https://ejemplo.es/x/abc" in cuerpo for cuerpo in partes.values())

        # `.upper()` porque smtplib manda los verbos en minúscula
        # —`rcpt TO:<...>`—, cosa que el protocolo permite y que no se ve hasta
        # que se mira lo que llega por el socket de verdad.
        assert any(c.upper().startswith("RCPT TO") and mensaje.destino in c
                   for c in servidor.comandos), servidor.comandos
