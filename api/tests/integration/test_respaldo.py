"""El correo de respaldo (tarea 13).

QUÉ PROTEGE
-----------
Los correos institucionales se reciclan: `jperez@ies.es` puede ser de otra
persona al curso siguiente. El respaldo es una dirección personal que sobrevive
al cambio de centro, y es contra ella —no contra la dirección reclamada— como
se confirmará una reclamación de contenido.

EL TEST QUE DA SENTIDO AL FICHERO
----------------------------------
`test_cambiarlo_avisa_al_respaldo_anterior_y_no_al_nuevo`. Sin esa regla, quien
se apodere del correo del centro puede restablecer la contraseña, entrar, poner
su propio respaldo y quedarse la cuenta para siempre: la protección entera se
evapora en tres pasos, y encima en silencio.

Se parchea ``app.tasks.encolar`` porque `solicitar` lo importa **dentro** de la
función para romper el ciclo con Celery. Ver la cabecera de
test_restablecimiento.py; en `app/api/situaciones.py` es al revés.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import respaldo
from app.services.tokens import TokenInvalido


CONTRASENA = "ContrasenaResp1"
PERSONAL = "jperez.personal@ejemplo.es"


@pytest.fixture
def docente(db):
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="jperez@ies.es", nombre="Jota", id_rol=rol.id_rol)
    u.set_password(CONTRASENA)
    db.session.add(u)
    db.session.commit()
    return u


def _pedir(app, usuario, correo):
    """Devuelve (destino_del_aviso, token)."""
    with app.test_request_context():
        with patch("app.tasks.encolar") as encolar:
            destino = respaldo.solicitar(usuario, correo)
        texto = encolar.call_args.kwargs["texto"]
    enlace = next(p for p in texto.split() if p.startswith("http"))
    return destino, enlace.split("token=", 1)[1]


class TestPonerElPrimero:
    def test_no_se_guarda_hasta_confirmarlo(self, app, db, docente):
        """Pedirlo no cambia nada: el respaldo vive dentro del token hasta que
        se confirma, así que no hay un estado intermedio a medias."""
        _pedir(app, docente, PERSONAL)

        db.session.refresh(docente)
        assert docente.correo_respaldo is None
        assert docente.tiene_respaldo is False

    def test_al_confirmar_queda_verificado(self, app, db, docente):
        _, token = _pedir(app, docente, PERSONAL)

        with app.test_request_context():
            respaldo.confirmar(token)

        db.session.refresh(docente)
        assert docente.correo_respaldo == PERSONAL
        assert docente.correo_respaldo_verificado_en is not None
        assert docente.tiene_respaldo is True

    def test_el_primero_se_confirma_desde_la_direccion_nueva(self, app, docente):
        """No hay nada anterior que proteger, así que el aviso va al destino."""
        destino, _ = _pedir(app, docente, PERSONAL)
        assert destino == PERSONAL


class TestLaReglaQueLoSostiene:
    """Cambiar el respaldo se confirma desde el respaldo **actual**."""

    @pytest.fixture
    def con_respaldo(self, app, db, docente):
        _, token = _pedir(app, docente, PERSONAL)
        with app.test_request_context():
            respaldo.confirmar(token)
        db.session.refresh(docente)
        return docente

    def test_cambiarlo_avisa_al_respaldo_anterior_y_no_al_nuevo(self, app, con_respaldo):
        """El test que da sentido al fichero.

        Si el aviso fuera a la dirección nueva, quien se apodere del correo del
        centro restablecería la contraseña, entraría, pondría su propio
        respaldo y se quedaría la cuenta. Con esta regla, ese atacante necesita
        además el buzón personal de la víctima, que es justo lo que no tiene.
        """
        destino, _ = _pedir(app, con_respaldo, "delladron@ejemplo.es")

        assert destino == PERSONAL, "el aviso tiene que ir al respaldo de siempre"
        assert destino != "delladron@ejemplo.es"

    def test_el_aviso_del_cambio_avisa_de_que_puede_ser_un_intruso(self, app, con_respaldo):
        """Quien lo reciba sin haberlo pedido necesita saber qué significa: que
        alguien tiene acceso a su cuenta. Este correo es el único aviso."""
        with app.test_request_context():
            with patch("app.tasks.encolar") as encolar:
                respaldo.solicitar(con_respaldo, "otro@ejemplo.es")
            texto = encolar.call_args.kwargs["texto"]

        assert "NO HAS SIDO TÚ" in texto
        assert "contraseña" in texto

    def test_confirmado_el_cambio_el_respaldo_es_el_nuevo(self, app, db, con_respaldo):
        _, token = _pedir(app, con_respaldo, "otro@ejemplo.es")

        with app.test_request_context():
            respaldo.confirmar(token)

        db.session.refresh(con_respaldo)
        assert con_respaldo.correo_respaldo == "otro@ejemplo.es"

    def test_quitarlo_no_pide_enlace_pero_si_contrasena(self, app, db, con_respaldo):
        """Asimetría deliberada. Cambiarlo por otro es lo que permitiría a un
        intruso quedarse la cuenta; quitarlo solo la deja como estaba antes.

        Y exigir el enlace también para quitarlo dejaría a quien pierda su
        correo personal con un respaldo muerto que no puede ni cambiar ni
        borrar.
        """
        with app.test_request_context():
            respaldo.quitar(con_respaldo, CONTRASENA)

        db.session.refresh(con_respaldo)
        assert con_respaldo.correo_respaldo is None
        assert con_respaldo.tiene_respaldo is False

    def test_quitarlo_con_la_contrasena_mal_no_hace_nada(self, app, db, con_respaldo):
        with app.test_request_context():
            with pytest.raises(respaldo.RespaldoError) as exc:
                respaldo.quitar(con_respaldo, "NoEsLaSuya9")

        assert exc.value.code == "contrasena_incorrecta"
        db.session.refresh(con_respaldo)
        assert con_respaldo.tiene_respaldo is True


class TestLoQueNoSeAcepta:
    def test_no_puede_ser_el_correo_de_la_propia_cuenta(self, app, docente):
        """Sería un ancla que se recicla igual que el original: ninguna."""
        with app.test_request_context():
            with patch("app.tasks.encolar") as encolar:
                with pytest.raises(respaldo.RespaldoError) as exc:
                    respaldo.solicitar(docente, docente.correo)

        assert exc.value.code == "igual_al_principal"
        assert not encolar.called

    def test_tampoco_con_otras_mayusculas(self, app, docente):
        """`JPerez@IES.es` es la misma dirección: comparar sin normalizar
        dejaría pasar exactamente el caso que se quiere prohibir."""
        with app.test_request_context():
            with pytest.raises(respaldo.RespaldoError):
                respaldo.solicitar(docente, docente.correo.upper())

    def test_una_direccion_vacia_se_rechaza(self, app, docente):
        with app.test_request_context():
            with pytest.raises(respaldo.RespaldoError):
                respaldo.solicitar(docente, "   ")


class TestElEnlace:
    def test_no_sirve_dos_veces(self, app, db, docente):
        """La huella del hash de la contraseña no cambia al confirmar un
        respaldo, así que este token **sí** se puede reutilizar mientras no
        caduque. Se comprueba para dejarlo escrito: confirmar dos veces la
        misma dirección es idempotente y no hace daño.
        """
        _, token = _pedir(app, docente, PERSONAL)

        with app.test_request_context():
            respaldo.confirmar(token)
            respaldo.confirmar(token)

        db.session.refresh(docente)
        assert docente.correo_respaldo == PERSONAL

    def test_cambiar_la_contrasena_lo_invalida(self, app, db, docente):
        """Lo que sí lo mata. Si alguien roba un enlace pendiente y la víctima
        cambia la contraseña, el enlace deja de valer."""
        _, token = _pedir(app, docente, PERSONAL)

        docente.set_password("OtraDistinta9")
        db.session.commit()

        with app.test_request_context():
            with pytest.raises(TokenInvalido):
                respaldo.confirmar(token)

    def test_un_token_de_otro_proposito_no_vale(self, app, docente):
        """Los propósitos están separados criptográficamente: un enlace de
        restablecimiento no puede cambiar un correo de respaldo."""
        from app.services.tokens import generar_restablecimiento

        with app.test_request_context():
            ajeno = generar_restablecimiento(docente)
            with pytest.raises(TokenInvalido):
                respaldo.confirmar(ajeno)

    def test_la_direccion_viaja_firmada_en_el_token(self, app, db, docente):
        """No se guarda en la base de datos esperando confirmación, así que no
        hay ningún estado «pendiente» que alguien tenga que recordar tratar."""
        from app.services.tokens import leer_respaldo

        _, token = _pedir(app, docente, PERSONAL)

        with app.test_request_context():
            id_usuario, correo = leer_respaldo(token)

        assert id_usuario == docente.id_usuario
        assert correo == PERSONAL
        db.session.refresh(docente)
        assert docente.correo_respaldo is None


class TestUnRespaldoSinVerificarNoCuenta:
    def test_escribirlo_a_mano_no_lo_hace_valido(self, app, db, docente):
        """Cierra el agujero de poner la dirección de otra persona: mientras no
        esté verificado, `tiene_respaldo` es falso y no sirve para nada."""
        docente.correo_respaldo = "victima@ejemplo.es"
        db.session.commit()

        assert docente.tiene_respaldo is False

    def test_con_verificacion_si_cuenta(self, app, db, docente):
        from datetime import datetime, timezone

        docente.correo_respaldo = PERSONAL
        docente.correo_respaldo_verificado_en = datetime.now(timezone.utc)
        db.session.commit()

        assert docente.tiene_respaldo is True
