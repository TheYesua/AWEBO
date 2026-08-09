"""Tests del panel de administración y del borrado en dos modos.

Tres cosas distintas que conviene no mezclar:

* **Autorización.** Que un docente no pueda entrar. Es lo que hace que el resto
  importe: sin esto, el panel es una fuga de datos con formulario.
* **Privacidad.** Que lo que devuelve el panel no incluya el contenido de las
  situaciones. El principio decidido es «gestión sin lectura», y un principio
  que no se comprueba se erosiona con el primer campo que se añade por
  comodidad.
* **Borrado.** Que la lápida conserve el contenido, que el borrado total no, y
  que una cuenta con lápida no pueda entrar ni siquiera con la contraseña
  correcta.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Rol, SituacionAprendizaje, Usuario


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _crear(db, correo: str, *, rol: str = Rol.DOCENTE, contrasena="Segura1234") -> Usuario:
    fila = db.session.scalar(select(Rol).where(Rol.nombre == rol))
    usuario = Usuario(id_rol=fila.id_rol, correo=correo, nombre="Persona de prueba")
    usuario.set_password(contrasena)
    db.session.add(usuario)
    db.session.commit()
    return usuario


def _con_situaciones(db, usuario: Usuario, cuantas: int = 2) -> None:
    for i in range(cuantas):
        db.session.add(
            SituacionAprendizaje(
                id_usuario=usuario.id_usuario,
                titulo=f"SA {i}",
                curso="3º ESO",
                materia="Matemáticas",
                estado=SituacionAprendizaje.BORRADOR,
            )
        )
    db.session.commit()


def _entrar(client, correo: str, contrasena: str = "Segura1234"):
    return client.post("/auth/login", json={"correo": correo, "contrasena": contrasena})


@pytest.fixture()
def admin(db, client):
    """Sesión iniciada como administrador."""
    usuario = _crear(db, "jefa@test.com", rol=Rol.ADMINISTRADOR)
    _entrar(client, "jefa@test.com")
    return usuario


# ---------------------------------------------------------------------------
# Autorización
# ---------------------------------------------------------------------------


class TestAutorizacion:
    RUTAS_API = (
        ("get", "/admin/api/estadisticas"),
        ("get", "/admin/api/usuarios"),
        ("get", "/admin/api/situaciones"),
        ("post", "/admin/api/usuarios"),
        ("delete", "/admin/api/usuarios/1"),
        ("delete", "/admin/api/situaciones/1"),
    )

    @pytest.mark.parametrize("metodo,ruta", RUTAS_API)
    def test_sin_sesion_401(self, client, db, metodo, ruta):
        assert getattr(client, metodo)(ruta).status_code == 401

    @pytest.mark.parametrize("metodo,ruta", RUTAS_API)
    def test_un_docente_no_pasa(self, client, db, metodo, ruta):
        _crear(db, "doc@test.com")
        _entrar(client, "doc@test.com")
        res = getattr(client, metodo)(ruta)
        assert res.status_code == 403
        assert res.get_json()["error"] == "permiso_denegado"

    def test_la_pagina_sin_sesion_lleva_al_login(self, client, db):
        """Y no devuelve JSON: una página que responde {"error": ...} deja a la
        persona mirando un cuerpo suelto en el navegador."""
        res = client.get("/admin/")
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

    def test_la_pagina_con_docente_da_403_y_no_redirige(self, client, db):
        """Mandar al login a quien ya tiene sesión monta un bucle."""
        _crear(db, "doc@test.com")
        _entrar(client, "doc@test.com")
        assert client.get("/admin/").status_code == 403

    def test_el_administrador_entra(self, client, admin):
        assert client.get("/admin/").status_code == 200
        assert client.get("/admin/api/estadisticas").status_code == 200

    def test_los_permisos_vienen_del_rol_no_del_nombre(self, client, db, admin):
        """El decorador mira ``rol.permisos``, no ``rol.nombre``.

        Se comprueba quitando un permiso concreto al rol: si la autorización
        se hiciera por nombre de rol, el administrador seguiría pasando y este
        test no distinguiría una implementación de la otra.
        """
        rol = db.session.scalar(select(Rol).where(Rol.nombre == Rol.ADMINISTRADOR))
        originales = list(rol.permisos)
        rol.permisos = [p for p in originales if p != "situacion:eliminar_cualquiera"]
        db.session.commit()
        try:
            assert client.delete("/admin/api/situaciones/1").status_code == 403
            # Los demás endpoints, que no piden ese permiso, siguen abiertos.
            assert client.get("/admin/api/estadisticas").status_code == 200
        finally:
            rol.permisos = originales
            db.session.commit()


# ---------------------------------------------------------------------------
# Privacidad
# ---------------------------------------------------------------------------


class TestGestionSinLectura:
    #: Campos que el panel no debe devolver jamás. Los tres últimos son texto
    #: libre de la docente sobre su aula y su alumnado.
    PROHIBIDOS = ("contenido", "descripcion", "perfil_aula", "materiales_contexto")

    def test_el_listado_no_expone_contenido(self, client, db, admin):
        docente = _crear(db, "doc@test.com")
        sa = SituacionAprendizaje(
            id_usuario=docente.id_usuario,
            titulo="La Antártida",
            curso="3º ESO",
            materia="Biología y Geología",
            estado=SituacionAprendizaje.GENERADA,
            contenido={"objetivos": ["algo muy privado"]},
            perfil_aula="Alumno con TDAH en segunda fila",
        )
        db.session.add(sa)
        db.session.commit()

        datos = client.get("/admin/api/situaciones").get_json()
        assert datos["total"] == 1
        fila = datos["situaciones"][0]

        for campo in self.PROHIBIDOS:
            assert campo not in fila, f"el panel expone {campo!r}"
        # Y que el texto no se cuele por otra vía, con otro nombre.
        assert "TDAH" not in str(fila)
        assert "muy privado" not in str(fila)

        # Lo que sí necesita para gestionar.
        assert fila["titulo"] == "La Antártida"
        assert fila["correo_usuario"] == "doc@test.com"

    def test_no_hay_endpoint_para_abrir_una_sa(self, client, db, admin):
        """El panel puede borrar por id, no leer por id.

        Si algún día se añade ``GET /admin/api/situaciones/<id>``, este test
        falla y obliga a decidirlo a conciencia en vez de que aparezca de
        rebote al copiar el patrón de otro endpoint.
        """
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 1)
        sa_id = db.session.scalar(select(SituacionAprendizaje.id_situacion))
        assert client.get(f"/admin/api/situaciones/{sa_id}").status_code == 405

    def test_el_listado_de_cuentas_no_lleva_el_hash(self, client, db, admin):
        _crear(db, "doc@test.com")
        datos = client.get("/admin/api/usuarios").get_json()
        assert all("contrasena_hash" not in u for u in datos["usuarios"])
        assert "total" in datos


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------


class TestEstadisticas:
    def test_los_estados_sin_ninguna_sa_salen_a_cero(self, client, db, admin):
        """Y no ausentes: un hueco en la interfaz parece un fallo de carga."""
        datos = client.get("/admin/api/estadisticas").get_json()
        por_estado = datos["situaciones"]["por_estado"]
        assert set(por_estado) == {
            "borrador", "generando", "generada", "error_generacion", "finalizada",
        }
        assert all(v == 0 for v in por_estado.values())

    def test_cuenta_por_estado_y_el_total_cuadra(self, client, db, admin):
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 3)
        datos = client.get("/admin/api/estadisticas").get_json()["situaciones"]
        assert datos["por_estado"]["borrador"] == 3
        assert datos["total"] == 3 == sum(datos["por_estado"].values())

    def test_una_cuenta_sin_situaciones_aparece_igual(self, client, db, admin):
        """Es justamente a quien interesa ver para saber qué cuentas no se usan.

        Depende de que la consulta use LEFT JOIN. Con un JOIN normal, quien no
        tiene ninguna SA desaparece del listado sin que nada avise.
        """
        _crear(db, "recien@test.com")
        correos = [u["correo"] for u in client.get("/admin/api/usuarios").get_json()["usuarios"]]
        assert "recien@test.com" in correos


# ---------------------------------------------------------------------------
# Borrado en dos modos
# ---------------------------------------------------------------------------


class TestBorrado:
    def test_el_modo_es_obligatorio(self, client, db, admin):
        """Sin defecto tácito: equivocarse aquí borra o conserva sin querer."""
        docente = _crear(db, "doc@test.com")
        res = client.delete(f"/admin/api/usuarios/{docente.id_usuario}", json={})
        assert res.status_code == 400
        assert res.get_json()["error"] == "modo_no_indicado"

    def test_la_lapida_conserva_el_contenido(self, client, db, admin):
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 2)

        res = client.delete(
            f"/admin/api/usuarios/{docente.id_usuario}",
            json={"conservar_contenido": True},
        )
        assert res.status_code == 200
        assert res.get_json()["modo"] == "lapida"

        db.session.expire_all()
        assert db.session.get(Usuario, docente.id_usuario).esta_eliminado
        assert db.session.scalar(select(SituacionAprendizaje).limit(1)) is not None

    def test_el_borrado_total_se_lleva_el_contenido(self, client, db, admin):
        """Lo hace el CASCADE que ya existía; no se borra nada a mano."""
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 2)

        res = client.delete(
            f"/admin/api/usuarios/{docente.id_usuario}",
            json={"conservar_contenido": False},
        )
        assert res.get_json()["modo"] == "total"

        db.session.expire_all()
        assert db.session.get(Usuario, docente.id_usuario) is None
        assert db.session.scalar(select(SituacionAprendizaje).limit(1)) is None

    def test_un_administrador_no_puede_eliminarse_a_si_mismo(self, client, db, admin):
        """Sin esta guarda se puede dejar la plataforma sin administración con
        dos clics, y sin manera de deshacerlo desde la web."""
        res = client.delete(
            f"/admin/api/usuarios/{admin.id_usuario}",
            json={"conservar_contenido": False},
        )
        assert res.status_code == 409
        assert res.get_json()["error"] == "no_puedes_eliminarte"

    def test_un_administrador_no_puede_degradarse(self, client, db, admin):
        res = client.patch(
            f"/admin/api/usuarios/{admin.id_usuario}", json={"rol": "docente"}
        )
        assert res.status_code == 409
        assert res.get_json()["error"] == "no_puedes_degradarte"

    def test_editar_solo_toca_lo_que_viene(self, client, db, admin):
        """Ausente es «no lo toques»; sin esa distinción, un formulario que
        manda solo el nombre vaciaría el resto del perfil."""
        docente = _crear(db, "doc@test.com")
        docente.centro_educativo = "IES Ejemplo"
        docente.especialidad = "Matemáticas"
        db.session.commit()

        client.patch(f"/admin/api/usuarios/{docente.id_usuario}", json={"nombre": "Nuevo"})

        db.session.expire_all()
        actualizado = db.session.get(Usuario, docente.id_usuario)
        assert actualizado.nombre == "Nuevo"
        assert actualizado.centro_educativo == "IES Ejemplo"
        assert actualizado.especialidad == "Matemáticas"


# ---------------------------------------------------------------------------
# Efectos de la lápida sobre el acceso
# ---------------------------------------------------------------------------


class TestAccesoConLapida:
    def test_no_puede_entrar_ni_con_la_contrasena_correcta(self, client, db):
        usuario = _crear(db, "baja@test.com")
        usuario.marcar_eliminado()
        db.session.commit()

        res = _entrar(client, "baja@test.com")
        assert res.status_code == 401
        assert res.get_json()["error"] == "cuenta_eliminada"

    def test_la_sesion_abierta_se_corta(self, app, client, db):
        """Dar de baja a alguien tiene que echarlo, no esperar a que caduque
        su cookie. Lo hace ``load_user``, que devuelve None si hay lápida.

        El ``app_context()`` no es adorno. Flask-Login cachea el usuario en
        ``g._login_user`` (``flask_login/utils.py::_get_user``), y ``g`` vive
        en el contexto de **aplicación**. ``conftest`` deja uno abierto toda la
        sesión, y una petición del cliente de test lo reutiliza en vez de crear
        otro: sin este bloque, la segunda llamada a ``/me`` devuelve el usuario
        cacheado en la primera y el test pasa sin comprobar nada.

        Es el mismo ``g`` compartido que ya obligó a arreglar los tests de
        i18n, donde el que cacheaba era Flask-Babel. En producción no ocurre:
        cada petición empuja su propio contexto de aplicación.
        """
        usuario = _crear(db, "baja@test.com")
        _entrar(client, "baja@test.com")
        assert client.get("/me").status_code == 200

        usuario.marcar_eliminado()
        db.session.commit()

        with app.app_context():
            assert client.get("/me").status_code == 401

    def test_no_se_le_puede_restablecer_la_contrasena(self, client, db):
        """La lápida bloquea también el camino del restablecimiento.

        Reescrito el 09/08/2026 con el flujo nuevo. Antes bastaba con enviar el
        correo y la contraseña nueva, y el 404 delataba que esa cuenta existía
        pero estaba de baja; ahora la respuesta es un 202 idéntico al de una
        dirección que no existe, y lo que se comprueba es que **no se manda
        ningún correo**.
        """
        from unittest.mock import patch

        usuario = _crear(db, "baja@test.com")
        usuario.marcar_eliminado()
        db.session.commit()

        with patch("app.tasks.encolar") as encolar:
            res = client.post(
                "/auth/solicitar-restablecimiento", json={"correo": "baja@test.com"}
            )

        assert res.status_code == 202
        assert not encolar.called


# ---------------------------------------------------------------------------
# Reclamación al volver a registrarse
# ---------------------------------------------------------------------------


class TestReclamacion:
    DATOS = {
        "correo": "baja@test.com",
        "contrasena": "NuevaClave1",
        "nombre": "Quien llega",
    }

    @pytest.fixture()
    def dado_de_baja(self, db):
        usuario = _crear(db, "baja@test.com")
        _con_situaciones(db, usuario, 3)
        usuario.marcar_eliminado()
        db.session.commit()
        return usuario

    @pytest.fixture()
    def con_solicitud(self, client, dado_de_baja):
        """Cuenta con lápida y una reclamación ya solicitada.

        Se pide por el endpoint real y no escribiendo el JSONB a mano: así el
        test comprueba también que el registro guarda lo que dice guardar.
        """
        client.post("/auth/register", json={**self.DATOS, "reclamar_contenido": True})
        return dado_de_baja

    def test_el_primer_intento_avisa_y_no_crea_nada(self, client, dado_de_baja):
        """Nunca silenciosa. Los correos institucionales se reciclan: una
        dirección puede reasignarse a otra persona cuando la primera se
        traslada, y una reclamación automática le entregaría trabajo ajeno."""
        res = client.post("/auth/register", json=self.DATOS)
        assert res.status_code == 409
        cuerpo = res.get_json()
        assert cuerpo["error"] == "contenido_reclamable"
        # Se dice de cuánto se trata: confirmar a ciegas no es confirmar.
        assert cuerpo["situaciones"] == 3
        assert cuerpo["dado_de_baja_el"] is not None

    def test_confirmar_solo_deja_la_solicitud_a_la_espera(
        self, client, db, dado_de_baja
    ):
        """Confirmar **no** entrega nada.

        La casilla de quien se registra frena la reclamación accidental, no la
        deliberada: quien hereda una dirección de centro la marcaría igual, de
        buena fe. Quien decide es el administrador.
        """
        res = client.post(
            "/auth/register", json={**self.DATOS, "reclamar_contenido": True}
        )
        # 202, no 409: la solicitud se ha registrado. Que el efecto dependa de
        # otra persona no la convierte en un fallo.
        assert res.status_code == 202
        assert res.get_json()["error"] == "reclamacion_pendiente"

        db.session.expire_all()
        usuario = db.session.get(Usuario, dado_de_baja.id_usuario)
        # Sigue con lápida, con su nombre y su contraseña de antes.
        assert usuario.esta_eliminado
        assert usuario.nombre == "Persona de prueba"
        assert usuario.reclamacion_pendiente["nombre"] == "Quien llega"

    def test_no_deja_sesion_iniciada(self, client, db, dado_de_baja):
        """Un registro normal autentica al terminar. Este no puede: la cuenta
        no es suya todavía."""
        client.post("/auth/register", json={**self.DATOS, "reclamar_contenido": True})
        assert client.get("/me").status_code == 401

    def test_la_solicitud_no_guarda_la_contrasena_en_claro(self, db, con_solicitud):
        db.session.expire_all()
        solicitud = db.session.get(Usuario, con_solicitud.id_usuario).reclamacion_pendiente
        assert "NuevaClave1" not in str(solicitud)
        assert solicitud["contrasena_hash"].startswith("$2")

    def test_el_panel_no_expone_el_hash_de_la_solicitud(
        self, client, db, con_solicitud, admin
    ):
        cuentas = client.get("/admin/api/usuarios").get_json()["usuarios"]
        pendiente = next(u for u in cuentas if u["correo"] == "baja@test.com")
        assert pendiente["reclamacion_pendiente"]["nombre"] == "Quien llega"
        assert "contrasena_hash" not in pendiente["reclamacion_pendiente"]

    def test_aprobar_devuelve_la_cuenta_y_su_contenido(
        self, client, db, con_solicitud, admin
    ):
        res = client.post(
            f"/admin/api/usuarios/{con_solicitud.id_usuario}/reclamacion",
            json={"aprobar": True},
        )
        assert res.status_code == 200
        assert res.get_json()["resultado"] == "aprobada"

        db.session.expire_all()
        usuario = db.session.get(Usuario, con_solicitud.id_usuario)
        assert not usuario.esta_eliminado
        assert usuario.reclamacion_pendiente is None
        assert usuario.nombre == "Quien llega"
        assert len(usuario.situaciones) == 3

        client.post("/auth/logout")
        assert _entrar(client, "baja@test.com", "NuevaClave1").status_code == 200

    def test_rechazar_deja_el_contenido_donde_estaba(
        self, client, db, con_solicitud, admin
    ):
        res = client.post(
            f"/admin/api/usuarios/{con_solicitud.id_usuario}/reclamacion",
            json={"aprobar": False},
        )
        assert res.get_json()["resultado"] == "rechazada"

        db.session.expire_all()
        usuario = db.session.get(Usuario, con_solicitud.id_usuario)
        assert usuario.esta_eliminado
        assert usuario.reclamacion_pendiente is None
        assert usuario.nombre == "Persona de prueba"
        assert len(usuario.situaciones) == 3

    def test_la_decision_es_obligatoria(self, client, db, con_solicitud, admin):
        res = client.post(
            f"/admin/api/usuarios/{con_solicitud.id_usuario}/reclamacion", json={}
        )
        assert res.status_code == 400
        assert res.get_json()["error"] == "decision_no_indicada"

    def test_sin_solicitud_no_hay_nada_que_resolver(self, client, db, admin):
        docente = _crear(db, "normal@test.com")
        res = client.post(
            f"/admin/api/usuarios/{docente.id_usuario}/reclamacion",
            json={"aprobar": True},
        )
        assert res.status_code == 409
        assert res.get_json()["error"] == "sin_reclamacion"

    def test_un_docente_no_puede_resolver_reclamaciones(self, client, db, con_solicitud):
        _crear(db, "doc@test.com")
        _entrar(client, "doc@test.com")
        res = client.post(
            f"/admin/api/usuarios/{con_solicitud.id_usuario}/reclamacion",
            json={"aprobar": True},
        )
        assert res.status_code == 403

    def test_reclamar_no_hereda_el_rol_anterior(self, client, db, admin):
        """Si no, el formulario público de registro sería una escalada de
        privilegios: bastaría con saber el correo de un administrador dado de
        baja para acabar entrando como administrador.

        Se comprueba tras la **aprobación**, que es donde el rol se aplica de
        verdad: mirarlo solo en la solicitud dejaría sin cubrir el paso en el
        que podría colarse.
        """
        antiguo = _crear(db, "exjefe@test.com", rol=Rol.ADMINISTRADOR)
        antiguo.marcar_eliminado()
        db.session.commit()

        client.post(
            "/auth/register",
            json={
                "correo": "exjefe@test.com",
                "contrasena": "Cualquiera1",
                "nombre": "Persona nueva",
                "reclamar_contenido": True,
            },
        )
        res = client.post(
            f"/admin/api/usuarios/{antiguo.id_usuario}/reclamacion",
            json={"aprobar": True},
        )
        assert res.status_code == 200

        db.session.expire_all()
        assert db.session.get(Usuario, antiguo.id_usuario).rol.nombre == Rol.DOCENTE

    def test_un_correo_vivo_sigue_dando_duplicado(self, client, db):
        _crear(db, "activo@test.com")
        res = client.post(
            "/auth/register",
            json={"correo": "activo@test.com", "contrasena": "Otra1234", "nombre": "Otra"},
        )
        assert res.get_json()["error"] == "correo_duplicado"


# ---------------------------------------------------------------------------
# Purgado periódico
# ---------------------------------------------------------------------------


class TestPurgado:
    def test_no_toca_las_lapidas_dentro_del_plazo(self, db):
        from app.tasks.mantenimiento import purgar_cuentas_vencidas

        usuario = _crear(db, "reciente@test.com")
        usuario.eliminado_en = datetime.now(timezone.utc) - timedelta(days=30)
        db.session.commit()

        resultado = purgar_cuentas_vencidas()
        assert resultado["cuentas_purgadas"] == 0
        assert db.session.get(Usuario, usuario.id_usuario) is not None

    def test_purga_las_vencidas_con_su_contenido(self, db):
        from app.tasks.mantenimiento import purgar_cuentas_vencidas

        usuario = _crear(db, "vencida@test.com")
        _con_situaciones(db, usuario, 2)
        usuario.eliminado_en = datetime.now(timezone.utc) - timedelta(
            days=Usuario.DIAS_DE_GRACIA + 1
        )
        db.session.commit()
        id_usuario = usuario.id_usuario

        resultado = purgar_cuentas_vencidas()
        assert resultado["cuentas_purgadas"] == 1
        assert resultado["situaciones_borradas"] == 2

        db.session.expire_all()
        assert db.session.get(Usuario, id_usuario) is None
        assert db.session.scalar(select(SituacionAprendizaje).limit(1)) is None

    def test_no_toca_las_cuentas_vivas(self, db):
        from app.tasks.mantenimiento import purgar_cuentas_vencidas

        usuario = _crear(db, "viva@test.com")
        assert purgar_cuentas_vencidas()["cuentas_purgadas"] == 0
        assert db.session.get(Usuario, usuario.id_usuario) is not None

    def test_justo_en_el_limite_se_purga(self, db):
        """El día 90 exacto entra: la comparación es ``>=``. Un test a 89 y
        otro a 91 dejarían el borde sin comprobar, que es donde viven los
        fallos de un signo.
        """
        from app.tasks.mantenimiento import purgar_cuentas_vencidas

        usuario = _crear(db, "justa@test.com")
        usuario.eliminado_en = datetime.now(timezone.utc) - timedelta(
            days=Usuario.DIAS_DE_GRACIA, seconds=1
        )
        db.session.commit()
        assert purgar_cuentas_vencidas()["cuentas_purgadas"] == 1


# ---------------------------------------------------------------------------
# Arranque: crear el primer administrador
# ---------------------------------------------------------------------------


class TestCliUsuarios:
    """El camino por el que se consigue el primer acceso de administración.

    Importa que funcione: si falla, no hay forma de entrar al panel sin tocar
    la base de datos a mano, que es justo lo que estos comandos evitan.
    """

    def test_listar_sin_ninguno_lo_dice_y_explica_que_hacer(self, app, db):
        salida = app.test_cli_runner().invoke(args=["usuarios", "listar-admins"]).output
        assert "No hay ninguna cuenta de administrador" in salida
        assert "crear-admin" in salida

    def test_crear_admin(self, app, db):
        runner = app.test_cli_runner()
        res = runner.invoke(
            args=[
                "usuarios", "crear-admin",
                "--correo", "jefa@test.com",
                "--nombre", "Jefa",
                "--contrasena", "Segura1234",
            ]
        )
        assert res.exit_code == 0, res.output
        assert "Administrador creado" in res.output

        usuario = db.session.scalar(
            select(Usuario).where(Usuario.correo == "jefa@test.com")
        )
        assert usuario.rol.nombre == Rol.ADMINISTRADOR
        # Pasa por el mismo servicio que el registro web: la contraseña queda
        # hasheada, no en claro.
        assert usuario.check_password("Segura1234")
        assert "Segura1234" not in usuario.contrasena_hash

    def test_la_contrasena_debe_cumplir_la_politica(self, app, db):
        """La misma que el registro web, porque es el mismo servicio.

        Este test falló la primera vez y tenía razón: la política vivía
        duplicada en tres validadores Pydantic y ninguno cubría el CLI, que
        creaba administradores con la contraseña que fuera. Se movió a
        ``auth_service.validar_contrasena``, que ``registrar_usuario`` aplica
        siempre.
        """
        res = app.test_cli_runner().invoke(
            args=[
                "usuarios", "crear-admin",
                "--correo", "floja@test.com",
                "--nombre", "Floja",
                "--contrasena", "sinnumeros",
            ]
        )
        assert res.exit_code != 0

    def test_crear_sobre_un_correo_existente_remite_a_promover(self, app, db):
        _crear(db, "ya@test.com")
        res = app.test_cli_runner().invoke(
            args=[
                "usuarios", "crear-admin",
                "--correo", "ya@test.com",
                "--nombre", "Otra",
                "--contrasena", "Segura1234",
            ]
        )
        assert res.exit_code == 1
        assert "promover" in res.output

    def test_promover_una_cuenta_existente(self, app, db):
        docente = _crear(db, "doc@test.com")
        res = app.test_cli_runner().invoke(
            args=["usuarios", "promover", "doc@test.com"]
        )
        assert res.exit_code == 0
        db.session.expire_all()
        assert db.session.get(Usuario, docente.id_usuario).rol.nombre == Rol.ADMINISTRADOR

    def test_promover_no_levanta_la_lapida(self, app, db):
        """Dar permisos y reactivar una cuenta son dos decisiones distintas.
        Juntarlas haría que promover resucitara cuentas sin que nadie lo pida.
        """
        usuario = _crear(db, "baja@test.com")
        usuario.marcar_eliminado()
        db.session.commit()

        res = app.test_cli_runner().invoke(args=["usuarios", "promover", "baja@test.com"])
        assert res.exit_code == 0
        assert "sigue sin poder iniciar sesión" in res.output

        db.session.expire_all()
        assert db.session.get(Usuario, usuario.id_usuario).esta_eliminado

    def test_promover_un_correo_inexistente_falla(self, app, db):
        res = app.test_cli_runner().invoke(args=["usuarios", "promover", "nadie@test.com"])
        assert res.exit_code == 1


# ---------------------------------------------------------------------------
# Paginación
# ---------------------------------------------------------------------------


class TestPaginacion:
    """Ambas tablas del panel se sirven de diez en diez.

    No es una optimización prematura: los dos listados crecen sin cota —uno con
    cada cuenta, otro con cada SA de cada cuenta— y una consulta sin LIMIT
    sobre una tabla así es una bomba con temporizador largo. Además la página
    se volvería infinita en vertical mucho antes de que la consulta doliera.
    """

    def test_las_cuentas_vienen_de_diez_en_diez(self, client, db, admin):
        for i in range(14):
            _crear(db, f"doc{i:02d}@test.com")

        datos = client.get("/admin/api/usuarios").get_json()
        assert datos["total"] == 15  # 14 docentes + la administradora
        assert len(datos["usuarios"]) == 10

        segunda = client.get("/admin/api/usuarios?desplazamiento=10").get_json()
        assert len(segunda["usuarios"]) == 5
        assert segunda["total"] == 15

    def test_las_paginas_no_repiten_ni_omiten_cuentas(self, client, db, admin):
        """Depende de que el orden sea determinista. Sin `order_by` estable,
        Postgres puede devolver las filas en otro orden entre dos consultas y
        una misma cuenta salir en las dos páginas mientras otra no sale en
        ninguna."""
        for i in range(14):
            _crear(db, f"doc{i:02d}@test.com")

        p1 = client.get("/admin/api/usuarios").get_json()["usuarios"]
        p2 = client.get("/admin/api/usuarios?desplazamiento=10").get_json()["usuarios"]

        correos = [u["correo"] for u in p1 + p2]
        assert len(correos) == len(set(correos)) == 15

    def test_las_reclamaciones_pendientes_salen_primero(self, client, db, admin):
        """Enterrar una solicitud en la página 7 equivale a no mostrarla."""
        for i in range(14):
            _crear(db, f"zz{i:02d}@test.com")  # ordenan después alfabéticamente

        pendiente = _crear(db, "zzz-ultimo@test.com")
        pendiente.reclamacion_pendiente = {"nombre": "Quien reclama", "rol": "docente"}
        pendiente.marcar_eliminado()
        db.session.commit()

        primera = client.get("/admin/api/usuarios").get_json()["usuarios"]
        assert primera[0]["correo"] == "zzz-ultimo@test.com"

    def test_las_situaciones_vienen_de_diez_en_diez(self, client, db, admin):
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 23)

        datos = client.get("/admin/api/situaciones").get_json()
        assert datos["total"] == 23
        assert len(datos["situaciones"]) == 10

        ultima = client.get("/admin/api/situaciones?desplazamiento=20").get_json()
        assert len(ultima["situaciones"]) == 3

    def test_el_limite_tiene_tope(self, client, db, admin):
        """Sin tope, un ?limite=999999 convierte un endpoint paginado en uno
        que no lo está, que es justo lo que se quería evitar."""
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 30)

        datos = client.get("/admin/api/situaciones?limite=999999").get_json()
        assert len(datos["situaciones"]) <= 100

    def test_el_indice_de_cuentas_no_se_pagina(self, client, db, admin):
        """Alimenta el desplegable de filtro. Si se paginara, solo se podría
        filtrar por las diez cuentas ya visibles, que es lo contrario de para
        lo que sirve un filtro."""
        for i in range(14):
            _crear(db, f"doc{i:02d}@test.com")

        datos = client.get("/admin/api/usuarios/indice").get_json()
        assert len(datos["usuarios"]) == 15
        # Solo lo justo para el desplegable: ni nombres ni fechas ni conteos.
        assert set(datos["usuarios"][0]) == {"id_usuario", "correo"}


# ---------------------------------------------------------------------------
# Paginación del listado del docente
# ---------------------------------------------------------------------------


class TestPaginacionDocente:
    """El listado de «Mis situaciones» también se pagina.

    No es solo comodidad visual: un docente con dos cursos y varias unidades
    acumula decenas de SA en un año, y la página crecía sin fin. La respuesta
    pasó de un array a ``{total, situaciones}`` para que la interfaz sepa
    cuántas páginas hay — un paginador que solo mira si la página viene llena
    se equivoca justo cuando el total es múltiplo del tamaño de página.
    """

    def test_devuelve_diez_y_el_total(self, client, db):
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 23)
        _entrar(client, "doc@test.com")

        datos = client.get("/api/situaciones").get_json()
        assert datos["total"] == 23
        assert len(datos["situaciones"]) == 10

    def test_la_ultima_pagina_trae_el_resto(self, client, db):
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 23)
        _entrar(client, "doc@test.com")

        datos = client.get("/api/situaciones?offset=20").get_json()
        assert len(datos["situaciones"]) == 3

    def test_las_paginas_no_repiten_ni_omiten(self, client, db):
        """Las SA creadas en bucle comparten `fecha_modificacion` al segundo,
        así que sin desempatar por identificador el orden no es determinista y
        una misma fila puede salir en dos páginas."""
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 25)
        _entrar(client, "doc@test.com")

        vistos = []
        for offset in (0, 10, 20):
            pagina = client.get(f"/api/situaciones?offset={offset}").get_json()
            vistos += [s["id_situacion"] for s in pagina["situaciones"]]

        assert len(vistos) == len(set(vistos)) == 25

    def test_el_total_respeta_los_filtros(self, client, db):
        """Si el total ignorara el filtro, el paginador ofrecería páginas que
        no existen. `listar` y `contar` comparten las condiciones por eso."""
        docente = _crear(db, "doc@test.com")
        _con_situaciones(db, docente, 12)
        db.session.add(
            SituacionAprendizaje(
                id_usuario=docente.id_usuario,
                titulo="Robótica en el aula",
                curso="3º ESO",
                materia="Matemáticas",
                estado=SituacionAprendizaje.BORRADOR,
            )
        )
        db.session.commit()
        _entrar(client, "doc@test.com")

        datos = client.get("/api/situaciones?q=Rob").get_json()
        assert datos["total"] == 1
        assert len(datos["situaciones"]) == 1

    def test_un_docente_sigue_sin_ver_lo_ajeno(self, client, db):
        """El filtro por propietario vive en `_filtros_listado`, que ahora
        comparten el listado y el conteo. Si se hubiera perdido al refactorizar,
        el total delataría cuántas SA hay de otras personas aunque la página no
        las muestre."""
        otra = _crear(db, "otra@test.com")
        _con_situaciones(db, otra, 15)

        _crear(db, "doc@test.com")
        _entrar(client, "doc@test.com")

        datos = client.get("/api/situaciones").get_json()
        assert datos["total"] == 0
        assert datos["situaciones"] == []


# ---------------------------------------------------------------------------
# Alcance del administrador en la aplicación normal
# ---------------------------------------------------------------------------


class TestAlcanceDelAdministrador:
    """Un administrador ve y abre todas las SdA desde la aplicación normal.

    Se probó lo contrario —cerrarlo del todo— y se descartó: quien administra
    dejaba de poder reproducir un problema que le reportan, y en una plataforma
    administrada por su propia autora eso es fricción sin contrapartida.

    Estos tests fijan la decisión **en los dos sentidos**: que el administrador
    llega, y que un docente cualquiera sigue sin llegar. Lo segundo es lo que
    hace que lo primero no sea un agujero: la excepción es del rol, no de
    cualquiera.
    """

    @pytest.fixture()
    def sa_ajena(self, db):
        docente = _crear(db, "doc@test.com")
        sa = SituacionAprendizaje(
            id_usuario=docente.id_usuario,
            titulo="La Antártida",
            curso="3º ESO",
            materia="Biología y Geología",
            estado=SituacionAprendizaje.GENERADA,
            contenido={"objetivos": ["algo muy privado"]},
        )
        db.session.add(sa)
        db.session.commit()
        return sa

    def test_puede_abrirla(self, client, db, sa_ajena, admin):
        res = client.get(f"/api/situaciones/{sa_ajena.id_situacion}")
        assert res.status_code == 200
        assert "muy privado" in res.data.decode("utf-8")

    def test_aparece_en_su_listado(self, client, db, sa_ajena, admin):
        datos = client.get("/api/situaciones").get_json()
        assert datos["total"] == 1

    def test_el_resumen_del_inicio_las_cuenta(self, client, db, sa_ajena, admin):
        """Listado y resumen comparten `_filtros_listado`. Si divergieran, el
        inicio mostraría un número que no corresponde a lo que se puede abrir —
        que es exactamente lo que se vio al cerrarlo a medias."""
        assert client.get("/api/situaciones/resumen").get_json()["total"] == 1

    def test_otro_docente_sigue_sin_poder(self, client, db, sa_ajena):
        """El control que hace que lo anterior no sea un agujero: la excepción
        es del rol de administrador, no de estar autenticado."""
        _crear(db, "otra@test.com")
        _entrar(client, "otra@test.com")

        res = client.get(f"/api/situaciones/{sa_ajena.id_situacion}")
        assert res.status_code == 403
        assert "muy privado" not in res.data.decode("utf-8")
        assert client.get("/api/situaciones").get_json()["total"] == 0

    def test_el_panel_sigue_sin_exponer_contenido(self, client, db, sa_ajena, admin):
        """Que el administrador pueda llegar por otra vía no es excusa para que
        el panel lo sirva: ahí se gestiona con metadatos, y así la gestión
        rutinaria no pasa por lo que nadie ha escrito."""
        datos = client.get("/admin/api/situaciones").get_json()
        assert datos["total"] == 1
        assert "muy privado" not in str(datos)
