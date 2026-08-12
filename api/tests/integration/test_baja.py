"""La baja de la propia cuenta.

Hasta hoy no existía: la única forma de que una cuenta desapareciera era que la
borrara un administrador. «Pídeselo al administrador» no satisface el derecho
de supresión del RGPD (art. 17).

QUÉ SE COMPRUEBA Y POR QUÉ
---------------------------
Tres propiedades, cada una con su forma de romperse:

* **Hacen falta las dos llaves.** Contraseña *y* acceso al buzón. Una sesión
  abierta en un ordenador compartido —el escenario normal en un centro— no
  puede bastar para borrarlo todo.
* **El modo viaja en el enlace.** Un enlace pedido para conservar el contenido
  no puede acabar borrándolo, ni al revés, aunque quien lo abra pida otra cosa.
* **El último administrador no se va.** Ni pidiéndolo ni confirmándolo, que son
  dos momentos distintos separados por hasta media hora.

Se parchea ``app.tasks.encolar`` y **no** el nombre en el módulo de servicio:
``solicitar`` lo importa dentro de la función para evitar el ciclo con Celery,
así que no es atributo de ese módulo. Sin `create=True`, que fabricaría verde
(ver la cabecera de test_restablecimiento.py).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import baja
from app.services.tokens import TokenInvalido


CONTRASENA = "ContrasenaBaja1"


def _crear(db, correo, rol_nombre="docente", contrasena=CONTRASENA):
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre=rol_nombre).first()
    u = Usuario(correo=correo, nombre=correo.split("@")[0], id_rol=rol.id_rol)
    u.set_password(contrasena)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def docente(db):
    return _crear(db, "baja.docente@ejemplo.es")


def _enlace(mock_encolar) -> str:
    assert mock_encolar.called, "no se encoló ningún envío"
    for palabra in mock_encolar.call_args.kwargs["texto"].split():
        if palabra.startswith("http"):
            return palabra
    raise AssertionError("el correo no lleva enlace")


def _token(mock_encolar) -> str:
    return _enlace(mock_encolar).split("token=", 1)[1]


def _pedir(app, usuario, *, conservar, contrasena=CONTRASENA):
    with app.test_request_context():
        with patch("app.tasks.encolar") as encolar:
            baja.solicitar(usuario, contrasena, conservar_contenido=conservar)
        return _token(encolar)


class TestHacenFaltaLasDosLlaves:
    def test_sin_la_contrasena_correcta_no_se_manda_nada(self, app, docente):
        """Si bastara la sesión, un ordenador compartido sería suficiente."""
        with app.test_request_context():
            with patch("app.tasks.encolar") as encolar:
                with pytest.raises(baja.BajaError) as exc:
                    baja.solicitar(docente, "NoEsLaSuya9", conservar_contenido=True)

        assert exc.value.code == "contrasena_incorrecta"
        assert not encolar.called, "no debe salir correo si la contraseña falla"

    def test_pedirla_no_da_de_baja_a_nadie(self, app, db, docente):
        """El primer paso no cambia nada: hasta el clic en el correo, la cuenta
        sigue como estaba. Si `solicitar` ya marcara la lápida, quien se
        arrepintiera no tendría a dónde volver."""
        _pedir(app, docente, conservar=True)

        db.session.refresh(docente)
        assert not docente.esta_eliminado

    def test_con_el_enlace_se_completa(self, app, db, docente):
        token = _pedir(app, docente, conservar=True)

        with app.test_request_context():
            resumen = baja.confirmar(token)

        db.session.refresh(docente)
        assert docente.esta_eliminado
        assert resumen["modo"] == "lapida"


class TestElModoViajaEnElEnlace:
    def test_conservando_deja_la_cuenta_con_lapida_y_su_contenido(self, app, db, docente):
        token = _pedir(app, docente, conservar=True)

        with app.test_request_context():
            resumen = baja.confirmar(token)

        from app.models import Usuario

        assert db.session.get(Usuario, docente.id_usuario) is not None
        assert docente.esta_eliminado
        assert resumen["dias_de_gracia"] == Usuario.DIAS_DE_GRACIA

    def test_total_borra_la_fila(self, app, db, docente):
        from app.models import Usuario

        id_usuario = docente.id_usuario
        token = _pedir(app, docente, conservar=False)

        with app.test_request_context():
            resumen = baja.confirmar(token)

        assert db.session.get(Usuario, id_usuario) is None
        assert resumen["modo"] == "total"
        assert resumen["dias_de_gracia"] == 0

    def test_los_dos_modos_estan_separados_criptograficamente(self, app, docente):
        """La propiedad que justifica usar dos propósitos y no un parámetro.

        La primera versión de este test confirmaba un enlace de «conservar» y
        comprobaba que salía lápida — lo mismo que ya hacía el test de arriba,
        con un nombre que prometía más. Se vio al sabotear: caía exactamente
        con los mismos cambios que los demás, así que no cubría nada propio.

        Lo que sí es suyo es esto: cada modo firma con una sal distinta, de
        modo que un token emitido para uno **no verifica** como el otro. Si
        alguien igualara los dos propósitos, el modo dejaría de estar protegido
        por la firma y pasaría a depender del orden en que se prueban.
        """
        from app.services import tokens

        with app.test_request_context():
            conservando = tokens.generar_baja(docente, conservar_contenido=True)
            total = tokens.generar_baja(docente, conservar_contenido=False)

            # Cada uno se lee con su modo…
            assert tokens.leer_baja(conservando) == (docente.id_usuario, True)
            assert tokens.leer_baja(total) == (docente.id_usuario, False)

            # …y ninguno verifica contra la sal del otro.
            with pytest.raises(TokenInvalido) as exc:
                tokens.leer(conservando, tokens.PROPOSITO_BAJA_TOTAL,
                            tokens.CADUCIDAD_BAJA)
            assert exc.value.motivo == "firma_invalida"

            with pytest.raises(TokenInvalido):
                tokens.leer(total, tokens.PROPOSITO_BAJA_CONSERVANDO,
                            tokens.CADUCIDAD_BAJA)

    def test_el_correo_dice_cual_de_los_dos_va_a_pasar(self, app, docente):
        """Los dos correos no pueden ser iguales: quien pulsó dos veces con
        modos distintos tiene que poder distinguir cuál está confirmando."""
        with app.test_request_context():
            with patch("app.tasks.encolar") as encolar:
                baja.solicitar(docente, CONTRASENA, conservar_contenido=True)
                conservando = encolar.call_args.kwargs["texto"]
                baja.solicitar(docente, CONTRASENA, conservar_contenido=False)
                total = encolar.call_args.kwargs["texto"]

        assert conservando != total
        assert "definitiva" in total
        assert "definitiva" not in conservando


class TestElEnlaceCaducaYSeGasta:
    def test_no_sirve_dos_veces(self, app, db, docente):
        token = _pedir(app, docente, conservar=True)

        with app.test_request_context():
            baja.confirmar(token)
            with pytest.raises(TokenInvalido):
                baja.confirmar(token)

    def test_un_token_de_restablecimiento_no_da_de_baja(self, app, db, docente):
        """Los propósitos están separados criptográficamente. Sin eso, el
        enlace de «he olvidado mi contraseña» borraría la cuenta."""
        from app.services.tokens import generar_restablecimiento

        with app.test_request_context():
            ajeno = generar_restablecimiento(docente)
            with pytest.raises(TokenInvalido):
                baja.confirmar(ajeno)

        db.session.refresh(docente)
        assert not docente.esta_eliminado

    def test_un_token_caducado_se_dice_caducado(self, app, docente):
        """Y no «firma inválida», que es lo que saldría si al probar el segundo
        propósito se enmascarase el motivo del primero: ese mensaje manda a
        buscar un problema que no existe.

        SE SIMULA EL RELOJ, NO SE DUERME
        ---------------------------------
        La primera versión ponía la caducidad a cero y dormía 1,1 segundos.
        Pasaba en una máquina y fallaba en otra, que es lo peor que puede hacer
        un test. El motivo estaba escrito **en este mismo repositorio** desde la
        tarea 11, en `test_tokens.py`: `itsdangerous` guarda la marca con
        granularidad de un segundo, así que un token puede tener «0 segundos»
        de edad después de dormir uno, según en qué punto del segundo arrancara.
        `0 > 0` es falso y no caduca nada.

        Escribí el test sin mirar cómo estaba resuelto tres ficheros más allá.
        """
        import time

        token = _pedir(app, docente, conservar=True)
        with app.test_request_context():
            from app.services.tokens import CADUCIDAD_BAJA

            futuro = time.time() + CADUCIDAD_BAJA + 60
            with patch("itsdangerous.timed.time.time", return_value=futuro):
                with pytest.raises(TokenInvalido) as exc:
                    baja.confirmar(token)

        assert exc.value.motivo == "caducado"


class TestElUltimoAdministradorNoSeVa:
    def test_no_puede_ni_pedirlo(self, app, db):
        admin = _crear(db, "unico.admin@ejemplo.es", "administrador")

        with app.test_request_context():
            with patch("app.tasks.encolar") as encolar:
                with pytest.raises(baja.BajaError) as exc:
                    baja.solicitar(admin, CONTRASENA, conservar_contenido=True)

        assert exc.value.code == "ultimo_administrador"
        assert not encolar.called

    def test_si_hay_otro_sí_puede(self, app, db):
        primero = _crear(db, "admin.uno@ejemplo.es", "administrador")
        _crear(db, "admin.dos@ejemplo.es", "administrador")

        token = _pedir(app, primero, conservar=True)
        with app.test_request_context():
            baja.confirmar(token)

        db.session.refresh(primero)
        assert primero.esta_eliminado

    def test_tambien_se_comprueba_al_confirmar(self, app, db):
        """El caso que se cuela si solo se mira al pedir.

        Entre el correo y el clic pasa hasta media hora. Si en ese rato el otro
        administrador se da de baja, confirmar dejaría la plataforma sin nadie
        que apruebe reclamaciones ni gestione cuentas, y sin forma de
        arreglarlo desde la web.
        """
        primero = _crear(db, "admin.a@ejemplo.es", "administrador")
        segundo = _crear(db, "admin.b@ejemplo.es", "administrador")

        token = _pedir(app, primero, conservar=True)   # entonces eran dos

        segundo.marcar_eliminado()                      # y ahora queda uno
        db.session.commit()

        with app.test_request_context():
            with pytest.raises(baja.BajaError) as exc:
                baja.confirmar(token)

        assert exc.value.code == "ultimo_administrador"
        db.session.refresh(primero)
        assert not primero.esta_eliminado

    def test_una_cuenta_con_lapida_no_cuenta_como_administrador(self, app, db):
        """Una cuenta dada de baja no puede entrar, así que no cubre el puesto.

        Si se contara, bastaría con que hubiera un administrador antiguo con
        lápida para que el último activo pudiera irse.
        """
        activo = _crear(db, "admin.activo@ejemplo.es", "administrador")
        antiguo = _crear(db, "admin.antiguo@ejemplo.es", "administrador")
        antiguo.marcar_eliminado()
        db.session.commit()

        with app.test_request_context():
            with pytest.raises(baja.BajaError) as exc:
                baja.solicitar(activo, CONTRASENA, conservar_contenido=True)

        assert exc.value.code == "ultimo_administrador"

    def test_un_docente_no_tropieza_con_la_guarda(self, app, db):
        """Aunque no haya ningún administrador, un docente puede irse: la
        guarda es sobre el puesto de administración, no sobre irse."""
        docente = _crear(db, "docente.suelto@ejemplo.es")

        token = _pedir(app, docente, conservar=True)
        with app.test_request_context():
            baja.confirmar(token)

        db.session.refresh(docente)
        assert docente.esta_eliminado


class TestLosEndpoints:
    """La baja vista desde fuera, con sesión de verdad."""

    def _entrar(self, client, correo):
        r = client.post("/auth/login", json={"correo": correo, "contrasena": CONTRASENA})
        assert r.status_code == 200, r.get_json()

    def _pedir_por_api(self, client, *, conservar, contrasena=CONTRASENA):
        with patch("app.tasks.encolar") as encolar:
            r = client.post(
                "/auth/solicitar-baja",
                json={"contrasena": contrasena, "conservar_contenido": conservar},
            )
        return r, encolar

    def test_sin_sesion_no_se_puede_pedir(self, client, docente):
        r = client.post(
            "/auth/solicitar-baja",
            json={"contrasena": CONTRASENA, "conservar_contenido": True},
        )
        assert r.status_code == 401

    def test_el_modo_es_obligatorio(self, client, docente):
        """Sin valor por defecto: los dos modos hacen cosas distintas y uno de
        ellos no se puede deshacer. Un cuerpo que se olvide del campo tiene que
        rebotar, no que se elija por él."""
        self._entrar(client, docente.correo)
        r = client.post("/auth/solicitar-baja", json={"contrasena": CONTRASENA})
        assert r.status_code == 400, r.get_json()
        detalles = r.get_json()["detalles"]
        assert any(d["loc"] == ["conservar_contenido"] for d in detalles), detalles

    def test_la_contrasena_mal_se_explica(self, client, docente):
        """Al revés que en el restablecimiento: aquí hay sesión y se habla de la
        cuenta propia, así que no hay nada que ocultar."""
        self._entrar(client, docente.correo)
        r, encolar = self._pedir_por_api(client, conservar=True, contrasena="NoEsLaSuya9")

        assert r.status_code == 400
        assert r.get_json()["error"] == "contrasena_incorrecta"
        assert not encolar.called

    def test_confirmar_no_necesita_sesion(self, app, db, client, docente):
        """El enlace se abre donde esté el buzón, que suele ser otro navegador.

        Se usa un cliente distinto justamente para eso: si el endpoint exigiera
        sesión, este test daría 401.
        """
        token = _pedir(app, docente, conservar=True)

        otro = app.test_client()          # sin cookie de sesión
        r = otro.post("/auth/confirmar-baja", json={"token": token})

        assert r.status_code == 200, r.get_json()
        assert r.get_json()["modo"] == "lapida"
        db.session.refresh(docente)
        assert docente.esta_eliminado

    def test_un_token_invalido_no_dice_por_que(self, client, docente):
        r = client.post("/auth/confirmar-baja", json={"token": "esto-no-vale-nada"})
        assert r.status_code == 400
        assert r.get_json()["error"] == "token_invalido"

    def test_el_modo_no_se_puede_colar_en_la_peticion(self, client, docente, app):
        """Aceptar el modo aquí permitiría que quien pidió conservar acabara
        borrándolo todo. El esquema lo rechaza como campo desconocido."""
        token = _pedir(app, docente, conservar=True)
        r = client.post(
            "/auth/confirmar-baja",
            json={"token": token, "conservar_contenido": False},
        )
        assert r.status_code == 400, r.get_json()

    def test_la_sesion_queda_cerrada_tras_la_lapida(self, app, db, client, docente):
        """El caso que la lápida hace fácil de olvidar: la fila **sigue ahí**.

        Con borrado total no hay a quién cargar y la sesión muere sola; con
        lápida el usuario existe, y si `load_user` no mirase `eliminado_en`, la
        persona seguiría navegando con todas sus situaciones después de haberse
        dado de baja.
        """
        self._entrar(client, docente.correo)
        assert client.get("/me").status_code == 200

        token = _pedir(app, docente, conservar=True)
        r = client.post("/auth/confirmar-baja", json={"token": token})
        assert r.status_code == 200

        assert client.get("/me").status_code == 401

    def test_la_sesion_queda_cerrada_tras_el_borrado_total(self, app, db, client, docente):
        self._entrar(client, docente.correo)
        token = _pedir(app, docente, conservar=False)

        r = client.post("/auth/confirmar-baja", json={"token": token})
        assert r.status_code == 200

        assert client.get("/me").status_code == 401

    def test_el_ultimo_administrador_recibe_409_al_confirmar(self, app, db, client):
        """409 y no 400: la petición está bien formada y el enlace es válido;
        lo que ha cambiado es el estado del sistema mientras tanto."""
        primero = _crear(db, "api.admin.a@ejemplo.es", "administrador")
        segundo = _crear(db, "api.admin.b@ejemplo.es", "administrador")

        token = _pedir(app, primero, conservar=True)
        segundo.marcar_eliminado()
        db.session.commit()

        r = client.post("/auth/confirmar-baja", json={"token": token})
        assert r.status_code == 409, r.get_json()
        assert r.get_json()["error"] == "ultimo_administrador"

    def test_la_pantalla_del_enlace_existe(self, client):
        assert client.get("/baja").status_code == 200


class TestLaOtraRedDeSeguridad:
    """La guarda de `load_user`, que los tests de arriba no llegan a ver.

    EL ARTEFACTO QUE LO ESCONDE, Y QUE AFECTA A TODA LA BATERÍA
    ------------------------------------------------------------
    Se descubrió al sabotear: quitar la guarda de la lápida de `load_user` no
    rompía ningún test. Instrumentando el cargador se vio por qué — **no se
    llamaba ni una vez**.

    Flask-Login cachea al usuario en `g._login_user`. `g` vive en el contexto
    de aplicación, y el fixture `db` mantiene uno abierto durante todo el test;
    Flask no empuja otro si ya hay uno, así que las peticiones del cliente
    comparten ese contexto. Resultado: en cuanto se inicia sesión,
    `current_user` queda **congelado** para el resto del test, diga lo que diga
    la base de datos. Es la misma trampa que mordió en la tarea 7, ahora en el
    arnés en lugar de en el código.

    Por eso aquí se vacía `g._login_user` a mano: es lo que hace de verdad una
    petición nueva en producción, donde cada una trae su propio contexto.
    `expire_all()` no basta —se probó—: el problema no es el mapa de identidad
    de SQLAlchemy, es que nadie llega a consultarlo.
    """

    @staticmethod
    def _olvidar_el_usuario_cacheado():
        """Simula lo único que distingue una petición nueva de verdad."""
        from flask import g

        g.pop("_login_user", None)

    def test_una_lapida_puesta_por_fuera_cierra_la_sesion_abierta(self, db, client, docente):
        """El camino del administrador, sin pasar por `logout_user`.

        Es la propiedad que la tarea 7 dio por hecha: dar de baja a alguien
        tiene que echarlo, no dejarlo trabajando en una cuenta que el
        administrador cree eliminada.
        """
        client.post(
            "/auth/login",
            json={"correo": docente.correo, "contrasena": CONTRASENA},
        )
        assert client.get("/me").status_code == 200

        docente.marcar_eliminado()
        db.session.commit()
        self._olvidar_el_usuario_cacheado()

        assert client.get("/me").status_code == 401

    def test_una_fila_borrada_por_fuera_cierra_la_sesion_abierta(self, db, client, docente):
        from app.models import Usuario

        client.post(
            "/auth/login",
            json={"correo": docente.correo, "contrasena": CONTRASENA},
        )
        assert client.get("/me").status_code == 200

        db.session.delete(db.session.get(Usuario, docente.id_usuario))
        db.session.commit()
        self._olvidar_el_usuario_cacheado()

        assert client.get("/me").status_code == 401
