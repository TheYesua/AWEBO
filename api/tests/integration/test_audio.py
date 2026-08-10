"""El audio de una situación: almacenamiento, endpoints y limpieza.

POR QUÉ NO HAY TABLA DE AUDIOS
-------------------------------
El nombre del fichero se calcula a partir del texto que narra, así que **el
nombre es el estado**: si existe, está listo y corresponde a ese texto. No hay
ningún campo que pueda decir «hay audio» mientras el disco dice que no.

Se hizo así por lo aprendido con las cuatro tablas de enlace que este proyecto
arrastra desde el TFG: existen, tienen relaciones declaradas y **nadie escribe
nunca en ellas**. Cuatro consultas vacías por cada SdA que se abre.

LO QUE MÁS FÁCIL SE OLVIDA
---------------------------
El audio vive en un volumen, no en Postgres, así que **ningún `cascade` se lo
lleva**. Hay cuatro caminos por los que una SdA desaparece —su dueño la borra,
un administrador la borra, su dueño se da de baja en modo total, o la purga se
lleva una cuenta vencida— y los cuatro tienen que limpiar el volumen. Aquí se
comprueban los cuatro: olvidar uno deja ficheros invisibles creciendo.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


CONTRASENA = "ContrasenaAudio1"
TEXTO = "Sesión 1: presentación del reto sobre el consumo de agua."


@pytest.fixture
def docente(db):
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="audio@ejemplo.es", nombre="Audio", id_rol=rol.id_rol)
    u.set_password(CONTRASENA)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def situacion(db, docente):
    from app.models import SituacionAprendizaje

    sa = SituacionAprendizaje(
        titulo="Con audio", materia="Matemáticas A", curso="4º ESO",
        id_usuario=docente.id_usuario, contenido={}, idioma="es",
    )
    db.session.add(sa)
    db.session.commit()
    return sa


@pytest.fixture
def volumen(app, tmp_path):
    """Un volumen de audio de usar y tirar."""
    app.config["VOZ_AUDIO_DIR"] = str(tmp_path)
    return tmp_path


def _entrar(client, correo=  "audio@ejemplo.es"):
    r = client.post("/auth/login", json={"correo": correo, "contrasena": CONTRASENA})
    assert r.status_code == 200, r.get_json()


def _dejar_audio(app, situacion, texto=TEXTO, seccion="sesiones", idioma="es"):
    """Escribe un audio como si lo hubiera generado la tarea."""
    from app.services import audio as almacen

    with app.test_request_context():
        return almacen.guardar(situacion.id_situacion, seccion, texto, idioma, b"ID3fake")


class TestElNombreEsElEstado:
    def test_el_mismo_texto_da_el_mismo_nombre(self, app, volumen):
        from app.services import audio as almacen

        with app.test_request_context():
            a = almacen.ruta(1, "sesiones", TEXTO, "es")
            b = almacen.ruta(1, "sesiones", TEXTO, "es")
        assert a == b

    def test_cambiar_el_texto_cambia_el_nombre(self, app, volumen):
        """Es lo que hace que al editar una sección no se sirva la narración
        antigua, que suena perfecta y cuenta otra cosa."""
        from app.services import audio as almacen

        with app.test_request_context():
            a = almacen.ruta(1, "sesiones", TEXTO, "es")
            b = almacen.ruta(1, "sesiones", TEXTO + " Y una frase más.", "es")
        assert a != b

    def test_el_idioma_entra_en_el_nombre(self, app, volumen):
        """El mismo texto leído en gallego y en castellano son dos audios. Si
        compartieran nombre, el segundo se serviría con la voz del primero."""
        from app.services import audio as almacen

        with app.test_request_context():
            assert almacen.ruta(1, "s", TEXTO, "es") != almacen.ruta(1, "s", TEXTO, "gl")

    def test_una_seccion_con_barras_no_escribe_fuera(self, app, volumen):
        """El nombre de la sección acaba en una ruta de fichero."""
        from app.services import audio as almacen

        with app.test_request_context():
            for malicioso in ("../../etc/passwd", "a/b", "..", "SECCION"):
                with pytest.raises(ValueError):
                    almacen.ruta(1, malicioso, TEXTO, "es")

    def test_al_guardar_se_tira_la_version_anterior(self, app, volumen, situacion):
        """Una SdA editada diez veces no puede dejar diez audios muertos."""
        from app.services import audio as almacen

        with app.test_request_context():
            almacen.guardar(situacion.id_situacion, "sesiones", "texto viejo", "es", b"A")
            almacen.guardar(situacion.id_situacion, "sesiones", "texto nuevo", "es", b"B")

        carpeta = volumen / str(situacion.id_situacion)
        assert len(list(carpeta.glob("sesiones-*.mp3"))) == 1

    def test_no_queda_ningun_fichero_parcial(self, app, volumen, situacion):
        """Se escribe a un temporal y se renombra: si el proceso muriera a
        medias, un MP3 truncado con el nombre bueno sería indistinguible de uno
        completo y se serviría igual."""
        _dejar_audio(app, situacion)
        carpeta = volumen / str(situacion.id_situacion)
        assert not list(carpeta.glob("*.parcial"))


class TestLosEndpoints:
    def test_sin_sesion_no_se_puede_pedir(self, client, situacion, volumen):
        r = client.post(f"/api/situaciones/{situacion.id_situacion}/audio",
                        json={"seccion": "sesiones", "texto": TEXTO})
        assert r.status_code == 401

    def test_pedirlo_encola_y_responde_202(self, app, client, situacion, volumen):
        """Se parchea `app.api.situaciones.encolar`, no `app.tasks.encolar`.

        Es el reverso de lo que pasa en el restablecimiento. Allí `encolar` se
        importa **dentro** de la función —para romper un ciclo con Celery—, así
        que no es atributo del módulo y hay que parchear el de origen. Aquí el
        import es de nivel superior, de modo que el nombre quedó ligado en
        `app.api.situaciones` al cargarse: parchear el origen no cambia nada y
        el test pasaría sin comprobar nada, que fue justo lo que pasó al
        escribirlo.
        """
        _entrar(client)
        with patch("app.api.situaciones.encolar") as encolar:
            r = client.post(f"/api/situaciones/{situacion.id_situacion}/audio",
                            json={"seccion": "sesiones", "texto": TEXTO})
        assert r.status_code == 202, r.get_json()
        assert r.get_json()["estado"] == "generando"
        assert encolar.called

    def test_si_ya_existe_no_se_vuelve_a_generar(self, app, client, situacion, volumen):
        """La comprobación sale gratis: el nombre se calcula del texto, no hay
        que preguntarle a ninguna tabla si está hecho."""
        _entrar(client)
        _dejar_audio(app, situacion)

        with patch("app.api.situaciones.encolar") as encolar:
            r = client.post(f"/api/situaciones/{situacion.id_situacion}/audio",
                            json={"seccion": "sesiones", "texto": TEXTO})

        assert r.status_code == 200
        assert r.get_json()["estado"] == "listo"
        assert not encolar.called, "no debe volver a sintetizar lo que ya está"

    def test_el_audio_de_otra_persona_no_se_sirve(self, app, db, client, situacion, volumen):
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        otra = Usuario(correo="otra@ejemplo.es", nombre="Otra", id_rol=rol.id_rol)
        otra.set_password(CONTRASENA)
        db.session.add(otra)
        db.session.commit()
        _dejar_audio(app, situacion)

        _entrar(client, "otra@ejemplo.es")
        r = client.get(f"/api/situaciones/{situacion.id_situacion}/audio",
                       query_string={"seccion": "sesiones", "texto": TEXTO})
        assert r.status_code in (403, 404)

    def test_todavia_sin_generar_devuelve_404(self, client, situacion, volumen):
        _entrar(client)
        r = client.get(f"/api/situaciones/{situacion.id_situacion}/audio",
                       query_string={"seccion": "sesiones", "texto": TEXTO})
        assert r.status_code == 404
        assert r.get_json()["estado"] == "no_disponible"

    def test_generado_se_sirve_como_mp3(self, app, client, situacion, volumen):
        _entrar(client)
        _dejar_audio(app, situacion)

        r = client.get(f"/api/situaciones/{situacion.id_situacion}/audio",
                       query_string={"seccion": "sesiones", "texto": TEXTO})

        assert r.status_code == 200
        assert r.mimetype == "audio/mpeg"
        assert r.data == b"ID3fake"

    def test_pedir_otro_texto_no_devuelve_el_audio_viejo(self, app, client, situacion, volumen):
        """El fallo que evita meter el texto en la petición: tras editar una
        sección, «dame el audio de esa sección» habría devuelto la narración
        anterior — bien grabada y diciendo otra cosa."""
        _entrar(client)
        _dejar_audio(app, situacion)

        r = client.get(f"/api/situaciones/{situacion.id_situacion}/audio",
                       query_string={"seccion": "sesiones", "texto": TEXTO + " editado"})
        assert r.status_code == 404


class TestElAudioSeLimpiaSiempre:
    """Los cuatro caminos por los que una SdA desaparece."""

    def test_al_borrarla_su_dueño(self, app, client, db, situacion, volumen):
        from app.services import situacion_service as svc

        _dejar_audio(app, situacion)
        carpeta = volumen / str(situacion.id_situacion)
        assert carpeta.is_dir()

        with app.test_request_context():
            svc.eliminar(situacion.id_situacion, situacion.usuario)

        assert not carpeta.exists(), "el audio ha quedado huérfano en el volumen"

    def test_al_borrarla_un_administrador(self, app, db, situacion, volumen):
        from app.models import Rol, Usuario
        from app.services import admin_service

        rol = db.session.query(Rol).filter_by(nombre="administrador").first()
        admin = Usuario(correo="admin.audio@ejemplo.es", nombre="A", id_rol=rol.id_rol)
        admin.set_password(CONTRASENA)
        db.session.add(admin)
        db.session.commit()

        _dejar_audio(app, situacion)
        carpeta = volumen / str(situacion.id_situacion)

        with app.test_request_context():
            admin_service.eliminar_situacion(situacion.id_situacion, por=admin)

        assert not carpeta.exists()

    def test_al_darse_de_baja_en_modo_total(self, app, db, situacion, volumen):
        from unittest.mock import patch as parchear

        from app.services import baja

        _dejar_audio(app, situacion)
        carpeta = volumen / str(situacion.id_situacion)

        with app.test_request_context():
            with parchear("app.tasks.encolar") as encolar:
                baja.solicitar(situacion.usuario, CONTRASENA, conservar_contenido=False)
            token = [p for p in encolar.call_args.kwargs["texto"].split()
                     if p.startswith("http")][0].split("token=")[1]
            baja.confirmar(token)

        assert not carpeta.exists()

    def test_al_purgar_una_cuenta_vencida(self, app, db, situacion, volumen):
        """El camino más fácil de olvidar: no lo dispara ninguna persona."""
        from datetime import datetime, timedelta, timezone

        from app.models import Usuario
        from app.tasks import mantenimiento

        usuario = situacion.usuario
        usuario.marcar_eliminado()
        usuario.eliminado_en = datetime.now(timezone.utc) - timedelta(
            days=Usuario.DIAS_DE_GRACIA + 1
        )
        db.session.commit()

        _dejar_audio(app, situacion)
        carpeta = volumen / str(situacion.id_situacion)

        with app.test_request_context():
            mantenimiento.purgar_cuentas_vencidas()

        assert not carpeta.exists()
