"""El comando `flask curriculo enlazar`, ejecutado de verdad.

POR QUÉ EXISTE ESTE FICHERO
----------------------------
Porque el comando salió roto a la primera ejecución real, con un
`NameError: name 'select' is not defined`, y **nada lo detectó**.

La comprobación que se había hecho era `python -c "import app.cli"`, que
devolvió «importa» y pareció suficiente. No lo es: importar un módulo ejecuta
su cuerpo, no el de sus funciones. Un nombre que solo se usa dentro de una
función no falta hasta que alguien la llama, así que un import olvidado en un
comando de CLI sobrevive intacto a cualquier comprobación de importación.

Es la regla 9 de `docs/CLAUDE.md` en su versión más literal: no dar una
instrucción sin haber recorrido el camino entero. Se dio el comando por bueno
y se puso en unas instrucciones de despliegue sin haberlo ejecutado nunca.

LO QUE SE PRUEBA
----------------
Que el comando **corre**. El comportamiento de la sincronización ya lo cubre
`test_enlaces_curriculares.py`; aquí lo que importa es lo que aquellos tests no
pueden ver, porque llaman a la función directamente y se saltan la capa de
click: los imports del comando, sus opciones y lo que imprime.
"""
from __future__ import annotations

import pytest


MATERIA = "Matemáticas A"
CURSO = "4º ESO"


@pytest.fixture
def sda_con_codigos(db):
    from app.models import Competencia, Rol, SituacionAprendizaje, Usuario

    db.session.add(Competencia(
        codigo="CE1", tipo=Competencia.ESPECIFICA, materia=MATERIA,
        cursos_aplicables=[CURSO], descriptores=[], descripcion="Resolver",
    ))
    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="cli@ies.es", nombre="CLI", id_rol=rol.id_rol)
    u.set_password("ContrasenaCli1")
    db.session.add(u)
    db.session.commit()

    s = SituacionAprendizaje(
        titulo="Del CLI", materia=MATERIA, curso=CURSO, id_usuario=u.id_usuario,
        contenido={"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}, {"codigo": "INVENTADO"}],
        }},
    )
    db.session.add(s)
    db.session.commit()
    return s


class TestElComandoCorre:
    """El test que habría ahorrado el fallo. Es el más tonto y el que faltaba."""

    def test_no_revienta(self, app, db, sda_con_codigos):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert resultado.exit_code == 0, resultado.output
        assert resultado.exception is None, resultado.exception

    def test_sin_situaciones_lo_dice_y_no_falla(self, app, db):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar"])

        assert resultado.exit_code == 0
        assert "No hay situaciones" in resultado.output


class TestSimularNoEscribe:
    """La opción existe para poder mirar antes de tocar. Si escribiera igual,
    sería peor que no tenerla: daría una confianza que no corresponde."""

    def test_con_simular_los_enlaces_no_se_guardan(self, app, db, sda_con_codigos):
        app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        db.session.expire_all()
        assert sda_con_codigos.competencias == []

    def test_sin_simular_si(self, app, db, sda_con_codigos):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar"])

        assert resultado.exit_code == 0, resultado.output
        db.session.expire_all()
        assert [c.codigo for c in sda_con_codigos.competencias] == ["CE1"]

    def test_se_avisa_de_que_fue_simulado(self, app, db, sda_con_codigos):
        """Sin esta marca en la salida, las dos ejecuciones se ven idénticas y
        es fácil creer que ya se ha aplicado cuando no."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "simulado" in resultado.output


class TestInformaDeLosInventados:
    def test_los_lista_con_su_situacion(self, app, db, sda_con_codigos):
        """Es la razón principal de correr esto con `--simular` antes: ver
        cuántos códigos se está inventando el modelo."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "INVENTADO" in resultado.output
        assert str(sda_con_codigos.id_situacion) in resultado.output

    def test_no_los_llama_error(self, app, db, sda_con_codigos):
        """Un código inventado no es un fallo del comando: es un hallazgo. Si
        terminara en error, la salida legítima parecería una ejecución rota."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert resultado.exit_code == 0


class TestNoConfundeLasDosCausas:
    """El comando dijo «17 situaciones citan códigos que el modelo se inventó»
    y ninguna lo hacía. Este es el test que faltaba."""

    @pytest.fixture
    def sda_sin_curriculo(self, db, sda_con_codigos):
        sda_con_codigos.materia = "Materia Que No Existe"
        db.session.commit()
        return sda_con_codigos

    def test_sin_curriculo_no_se_llama_inventado(self, app, db, sda_sin_curriculo):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "No son códigos inventados" in resultado.output
        assert "el modelo se inventó" not in resultado.output

    def test_se_agrupa_por_pareja_y_no_por_situacion(self, app, db, sda_sin_curriculo):
        """Con 17 SdA repartidas en tres parejas, listarlas una a una esconde
        justo lo que hay que ver: que el problema son tres materias, no
        diecisiete situaciones."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "Materia Que No Existe · 4º ESO" in resultado.output

    def test_inventarse_codigos_de_verdad_sí_se_llama_así(self, app, db, sda_con_codigos):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "el modelo se inventó" in resultado.output
        assert "INVENTADO" in resultado.output

    def test_cuando_todo_casa_se_dice(self, app, db, sda_con_codigos):
        """Sin este mensaje, una ejecución limpia y una a medias se distinguen
        solo por la ausencia de texto, que es difícil de ver."""
        sda_con_codigos.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}],
        }}
        db.session.commit()

        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])
        assert "Todos los códigos casan" in resultado.output


# ---------------------------------------------------------------------------
# `flask curriculo reasignar`
# ---------------------------------------------------------------------------


@pytest.fixture
def catalogo_real(db):
    """Las materias de 4º ESO que importan para la reasignación.

    Se cargan las de destino —`Lengua`, `Tecnología`, `Matemáticas A` y `B`— y
    **no** las de origen, que es justo lo que las hace huérfanas.
    """
    from app.models import Competencia

    for materia in ("Lengua", "Tecnología", "Matemáticas A", "Matemáticas B"):
        db.session.add(Competencia(
            codigo="CE1", tipo=Competencia.ESPECIFICA, materia=materia,
            cursos_aplicables=["4º ESO"], descriptores=[], descripcion="x",
        ))
    db.session.commit()


def _sda(db, materia, curso="4º ESO", titulo="Vieja del TFG"):
    from app.models import Rol, SituacionAprendizaje, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    correo = f"{materia.lower().replace(' ', '')}@ies.es"
    u = db.session.query(Usuario).filter_by(correo=correo).first()
    if u is None:
        u = Usuario(correo=correo, nombre="D", id_rol=rol.id_rol)
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()

    s = SituacionAprendizaje(
        titulo=titulo, materia=materia, curso=curso, id_usuario=u.id_usuario,
        contenido={"conexion_curricular": {"competencias": [{"codigo": "CE1"}]}},
    )
    db.session.add(s)
    db.session.commit()
    return s


class TestReasignacionesMecanicas:
    """Las dos parejas que tienen destino único y comprobable."""

    def test_lengua_castellana_pasa_a_lengua(self, app, db, catalogo_real):
        sda = _sda(db, "Lengua Castellana y Literatura")

        r = app.test_cli_runner().invoke(args=["curriculo", "reasignar"])

        assert r.exit_code == 0, r.output
        db.session.refresh(sda)
        assert sda.materia == "Lengua"
        assert sda.curso == "4º ESO", "el curso era correcto y no debe tocarse"

    def test_tecnologia_y_digitalizacion_de_4o_pasa_a_tecnologia(self, app, db, catalogo_real):
        """En 4º la materia se llama «Tecnología». Se corrige el nombre, que es
        lo que estaba mal, y se conserva el curso, que es lo que el docente
        eligió."""
        sda = _sda(db, "Tecnología y Digitalización")

        app.test_cli_runner().invoke(args=["curriculo", "reasignar"])

        db.session.refresh(sda)
        assert (sda.materia, sda.curso) == ("Tecnología", "4º ESO")

    def test_una_pareja_valida_no_se_toca(self, app, db, catalogo_real):
        sda = _sda(db, "Lengua", titulo="Esta ya está bien")

        app.test_cli_runner().invoke(args=["curriculo", "reasignar"])

        db.session.refresh(sda)
        assert (sda.materia, sda.curso) == ("Lengua", "4º ESO")


class TestMatematicasSePregunta:
    """La decisión que el comando **no** toma por su cuenta.

    A y B no son niveles de la misma asignatura: son itinerarios con currículos
    distintos. Elegir por defecto sería decidir por el docente qué asignatura
    imparte.
    """

    def test_sin_decir_nada_se_pregunta(self, app, db, catalogo_real):
        _sda(db, "Matemáticas")

        r = app.test_cli_runner().invoke(args=["curriculo", "reasignar"], input="A\n")

        assert "¿A, B o s" in r.output
        assert "bachillerato científico" in r.output, "hay que dar el criterio, no solo la letra"

    def test_lo_contestado_es_lo_que_se_aplica(self, app, db, catalogo_real):
        sda = _sda(db, "Matemáticas")

        app.test_cli_runner().invoke(args=["curriculo", "reasignar"], input="B\n")

        db.session.refresh(sda)
        assert sda.materia == "Matemáticas B"

    def test_se_puede_saltar_una(self, app, db, catalogo_real):
        """Quien no sepa cuál toca debe poder dejarla como está en vez de
        elegir a boleo para salir del paso."""
        sda = _sda(db, "Matemáticas")

        r = app.test_cli_runner().invoke(args=["curriculo", "reasignar"], input="s\n")

        db.session.refresh(sda)
        assert sda.materia == "Matemáticas"
        assert "sin regla de reasignación" in r.output

    def test_la_opcion_evita_contestar_una_por_una(self, app, db, catalogo_real):
        sda = _sda(db, "Matemáticas")

        r = app.test_cli_runner().invoke(
            args=["curriculo", "reasignar", "--matematicas", "A"]
        )

        assert "¿A, B o s" not in r.output
        db.session.refresh(sda)
        assert sda.materia == "Matemáticas A"


class TestSeGuardaElEstadoAnterior:
    def test_queda_una_version_con_la_materia_vieja(self, app, db, catalogo_real):
        """Son documentos de trabajo de alguien, no filas de prueba. Si la
        reasignación resulta equivocada, tiene que haber a dónde volver."""
        from app.models import Version

        sda = _sda(db, "Lengua Castellana y Literatura")
        app.test_cli_runner().invoke(args=["curriculo", "reasignar"])

        versiones = db.session.query(Version).filter_by(id_situacion=sda.id_situacion).all()
        assert len(versiones) == 1
        assert versiones[0].contenido["materia"] == "Lengua Castellana y Literatura"

    def test_el_motivo_queda_escrito(self, app, db, catalogo_real):
        from app.models import Version

        sda = _sda(db, "Lengua Castellana y Literatura")
        app.test_cli_runner().invoke(args=["curriculo", "reasignar"])

        v = db.session.query(Version).filter_by(id_situacion=sda.id_situacion).one()
        assert "no existe en el catálogo" in v.descripcion_cambio


class TestSimularYRegenerar:
    def test_simular_no_escribe(self, app, db, catalogo_real):
        sda = _sda(db, "Lengua Castellana y Literatura")

        r = app.test_cli_runner().invoke(args=["curriculo", "reasignar", "--simular"])

        db.session.expire_all()
        assert sda.materia == "Lengua Castellana y Literatura"
        assert "simulado" in r.output

    def test_sin_regenerar_avisa_de_que_queda_a_medias(self, app, db, catalogo_real):
        """Reasignar sin regenerar deja el contenido citando el currículo
        anterior. Callarlo haría creer que el problema está resuelto."""
        _sda(db, "Lengua Castellana y Literatura")

        r = app.test_cli_runner().invoke(args=["curriculo", "reasignar"])

        assert "no se ha regenerado nada" in r.output.lower()

    def test_con_regenerar_se_encola(self, app, db, catalogo_real):
        from unittest.mock import patch

        sda = _sda(db, "Lengua Castellana y Literatura")

        with patch("app.tasks.encolar") as encolar:
            r = app.test_cli_runner().invoke(args=["curriculo", "reasignar", "--regenerar"])

        assert r.exit_code == 0, r.output
        assert encolar.called
        assert sda.id_situacion in encolar.call_args.args

    def test_no_se_regenera_lo_que_no_se_reasigno(self, app, db, catalogo_real):
        """Regenerar cuesta dinero. Solo lo que ha cambiado."""
        from unittest.mock import patch

        _sda(db, "Lengua", titulo="Esta ya estaba bien")

        with patch("app.tasks.encolar") as encolar:
            app.test_cli_runner().invoke(args=["curriculo", "reasignar", "--regenerar"])

        assert not encolar.called


# ---------------------------------------------------------------------------
# `flask curriculo estado`
# ---------------------------------------------------------------------------


class TestEstado:
    """El vigía para esperar a que termine un lote de regeneraciones.

    Existe porque seguirlo en el log del worker obliga a leer líneas sueltas y
    llevar la cuenta a mano. Esto lo cuenta contra la base de datos, que es
    donde está el estado de verdad.
    """

    def test_dice_cuantas_quedan_generandose(self, app, db, catalogo_real):
        from app.models import SituacionAprendizaje

        sda = _sda(db, "Lengua")
        sda.estado = SituacionAprendizaje.GENERANDO
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])

        assert r.exit_code == 0
        assert "Quedan 1 generándose" in r.output

    def test_sin_ninguna_en_curso_lo_dice(self, app, db, catalogo_real):
        from app.models import SituacionAprendizaje

        sda = _sda(db, "Lengua")
        sda.estado = SituacionAprendizaje.GENERADA
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])

        assert "Ninguna en curso y ninguna en error" in r.output

    def test_las_que_fallaron_se_cuentan_aparte(self, app, db, catalogo_real):
        """Lo que hace útil al vigía.

        Una generación en error se queda en `error_generacion` y **no vuelve
        sola**. Mirando solo «cuántas quedan generando», el bucle terminaría
        dando por bueno un lote a medias.
        """
        from app.models import SituacionAprendizaje

        sda = _sda(db, "Lengua")
        sda.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])

        assert "RESUMEN generando=0 error=1" in r.output

    def test_se_dice_CUALES_fallaron_no_solo_cuantas(self, app, db, catalogo_real):
        """Este test pasaba sin comprobar nada, y lo delató un sabotaje.

        La primera versión hacía `assert str(sda.id_situacion) in r.output`.
        Con una sola SdA de id 1, ese «1» aparece también en «1 situaciones en
        total», así que la aserción se cumplía aunque la línea con los ids no
        se imprimiera. Ahora se mira **esa línea**, y con varias SdA para que
        el id no pueda colarse por casualidad.

        Importa que se digan: son las que hay que relanzar a mano, y buscarlas
        después obliga a repetir la consulta.
        """
        from app.models import SituacionAprendizaje

        buenas = [_sda(db, "Lengua", titulo=f"Buena {i}") for i in range(4)]
        for s in buenas:
            s.estado = SituacionAprendizaje.GENERADA
        rota = _sda(db, "Tecnología", titulo="La que falló")
        rota.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])

        linea = next(l for l in r.output.splitlines() if "En error:" in l)
        assert str(rota.id_situacion) in linea
        assert str(buenas[0].id_situacion) not in linea


class TestElCodigoDeSalida:
    """Para poder esperar desde un script sin analizar el texto."""

    def test_mientras_generan_termina_en_1(self, app, db, catalogo_real):
        from app.models import SituacionAprendizaje

        sda = _sda(db, "Lengua")
        sda.estado = SituacionAprendizaje.GENERANDO
        db.session.commit()

        r = app.test_cli_runner().invoke(
            args=["curriculo", "estado", "--codigo-de-salida"]
        )
        assert r.exit_code == 1

    def test_al_terminar_todas_da_0(self, app, db, catalogo_real):
        from app.models import SituacionAprendizaje

        sda = _sda(db, "Lengua")
        sda.estado = SituacionAprendizaje.GENERADA
        db.session.commit()

        r = app.test_cli_runner().invoke(
            args=["curriculo", "estado", "--codigo-de-salida"]
        )
        assert r.exit_code == 0

    def test_un_error_no_deja_el_bucle_colgado(self, app, db, catalogo_real):
        """Sin nada en curso, un error sí es definitivo y el bucle debe salir.

        El docstring de este test decía «una SdA en error no vuelve sola», que
        es **falso a medias** y lo desmintió una ejecución real: SdA en error
        pasaron a `generada` sin que nadie tocara nada, porque la tarea marca
        el estado y *luego* relanza para que `autoretry_for` la reintente.

        Lo que sigue siendo cierto es lo que este test comprueba: cuando ya no
        queda ninguna en curso, los reintentos se agotaron y el bucle tiene que
        terminar. Si esperase a que no hubiera errores, no acabaría nunca.
        """
        from app.models import SituacionAprendizaje

        sda = _sda(db, "Lengua")
        sda.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()

        r = app.test_cli_runner().invoke(
            args=["curriculo", "estado", "--codigo-de-salida"]
        )
        assert r.exit_code == 0
        assert "RESUMEN generando=0 error=1" in r.output

    def test_sin_la_opcion_siempre_da_0(self, app, db, catalogo_real):
        """Mirar el estado no es un fallo. Sin la opción, el comando es
        informativo y no debe romper un script que lo llame de paso."""
        from app.models import SituacionAprendizaje

        sda = _sda(db, "Lengua")
        sda.estado = SituacionAprendizaje.GENERANDO
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# `flask curriculo regenerar`
# ---------------------------------------------------------------------------


class TestRegenerarLasQueFallaron:
    """Una generación fallida no vuelve sola: se queda en `error_generacion`.

    Sin este comando, recuperar un lote de 19 obliga a entrar en cada SdA por
    la interfaz y pulsar regenerar una por una.
    """

    def _en_error(self, db, cuantas=3):
        from app.models import SituacionAprendizaje

        sdas = [_sda(db, "Lengua", titulo=f"Rota {i}") for i in range(cuantas)]
        for s in sdas:
            s.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()
        return sdas

    def test_relanza_solo_las_que_estan_en_error(self, app, db, catalogo_real):
        from unittest.mock import patch

        from app.models import SituacionAprendizaje

        rotas = self._en_error(db, 2)
        buena = _sda(db, "Lengua", titulo="Esta salió bien")
        buena.estado = SituacionAprendizaje.GENERADA
        db.session.commit()

        with patch(
            "app.tasks.generacion.generar_situacion_completa.apply_async"
        ) as encolar:
            r = app.test_cli_runner().invoke(args=["curriculo", "regenerar"])

        assert r.exit_code == 0, r.output
        encolados = [c.kwargs["args"][0] for c in encolar.call_args_list]
        assert sorted(encolados) == sorted(s.id_situacion for s in rotas)
        assert buena.id_situacion not in encolados

    def test_sin_ninguna_en_error_lo_dice(self, app, db, catalogo_real):
        r = app.test_cli_runner().invoke(args=["curriculo", "regenerar"])
        assert "Ninguna situación en error" in r.output

    def test_simular_no_encola(self, app, db, catalogo_real):
        from unittest.mock import patch

        self._en_error(db, 2)

        with patch(
            "app.tasks.generacion.generar_situacion_completa.apply_async"
        ) as encolar:
            r = app.test_cli_runner().invoke(args=["curriculo", "regenerar", "--simular"])

        assert not encolar.called
        assert "no se ha encolado nada" in r.output


class TestElEspaciado:
    """No es un adorno.

    Encolar veinte generaciones de golpe manda veinte peticiones casi
    simultáneas al proveedor. Si el lote anterior falló por un límite de
    peticiones por minuto, repetir la ráfaga reproduce el fallo y no se aprende
    nada.
    """

    def test_las_separa_en_el_tiempo(self, app, db, catalogo_real):
        from unittest.mock import patch

        from app.models import SituacionAprendizaje

        for i in range(3):
            s = _sda(db, "Lengua", titulo=f"Rota {i}")
            s.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()

        with patch(
            "app.tasks.generacion.generar_situacion_completa.apply_async"
        ) as encolar:
            app.test_cli_runner().invoke(
                args=["curriculo", "regenerar", "--espaciado", "30"]
            )

        esperas = [c.kwargs["countdown"] for c in encolar.call_args_list]
        assert esperas == [0, 30, 60]

    def test_sin_espaciado_salen_todas_a_la_vez(self, app, db, catalogo_real):
        from unittest.mock import patch

        from app.models import SituacionAprendizaje

        for i in range(2):
            s = _sda(db, "Lengua", titulo=f"Rota {i}")
            s.estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()

        with patch(
            "app.tasks.generacion.generar_situacion_completa.apply_async"
        ) as encolar:
            r = app.test_cli_runner().invoke(args=["curriculo", "regenerar"])

        assert all(c.kwargs["countdown"] == 0 for c in encolar.call_args_list)
        assert "--espaciado 30" in r.output, "hay que sugerirlo, no solo permitirlo"


# ---------------------------------------------------------------------------
# `flask ia diagnostico`
# ---------------------------------------------------------------------------


class TestDiagnosticoDeProveedor:
    """Con qué proveedor se generaría cada SdA, y por qué.

    EL SÍNTOMA QUE LO MOTIVÓ
    -------------------------
    Jesús cambió su perfil a GPT y las regeneraciones seguían fallando por
    cuota de Gemini. No había forma de averiguar por qué: nada en la
    aplicación dice qué proveedor va a usar una SdA concreta.

    Hay dos vías por las que una preferencia puede no aplicarse, y las dos son
    silenciosas:

    * El proveedor sale del **propietario de la SdA**, no de quien pulsa
      regenerar. Cambiar tu perfil no toca las SdA de otra persona.
    * `catalogo.validar` cae a «el del sistema» si el proveedor elegido no está
      disponible en ese proceso — y `api` y `worker` son contenedores distintos.
    """

    def _sda_de(self, db, correo, proveedor=None, modelo=None):
        from app.models import Rol, SituacionAprendizaje, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo=correo, nombre="D", id_rol=rol.id_rol)
        u.set_password("ContrasenaDoc1")
        u.proveedor_ia = proveedor
        u.modelo_ia = modelo
        db.session.add(u)
        db.session.commit()

        s = SituacionAprendizaje(
            titulo="X", materia="Lengua", curso="4º ESO", id_usuario=u.id_usuario,
            contenido={}, estado=SituacionAprendizaje.ERROR_GENERACION,
        )
        db.session.add(s)
        db.session.commit()
        return s

    def test_dice_de_quien_es_cada_situacion(self, app, db):
        """La clave del asunto: el dueño puede no ser quien está mirando."""
        sda = self._sda_de(db, "otra.persona@ies.es")

        r = app.test_cli_runner().invoke(args=["ia", "diagnostico"])

        assert r.exit_code == 0, r.output
        assert "otra.persona@ies.es" in r.output
        assert str(sda.id_situacion) in r.output

    def test_marca_las_preferencias_que_se_ignoran(self, app, db):
        """Una preferencia guardada que este proceso no puede cumplir es
        exactamente el caso que confunde: el perfil dice una cosa y la
        generación hace otra, sin que nada avise."""
        self._sda_de(db, "con.gpt@ies.es", proveedor="openai", modelo="gpt-5.6")

        r = app.test_cli_runner().invoke(args=["ia", "diagnostico"])

        assert "←" in r.output
        assert "IGNORA" in r.output

    def test_no_marca_a_quien_no_eligio_nada(self, app, db):
        """Usar el del sistema porque no has elegido no es una anomalía, y
        marcarlo llenaría la tabla de flechas que no significan nada."""
        self._sda_de(db, "sin.preferencia@ies.es")

        r = app.test_cli_runner().invoke(args=["ia", "diagnostico"])

        assert "←" not in r.output

    def test_enseña_lo_disponible_en_este_proceso(self, app, db):
        """«En este proceso» es el matiz importante: `api` y `worker` son
        contenedores distintos y podrían no ver las mismas variables."""
        r = app.test_cli_runner().invoke(args=["ia", "diagnostico", "--situaciones", "ninguna"])

        assert "ESTE proceso" in r.output
        assert "Del sistema:" in r.output

    def test_por_defecto_solo_mira_las_que_estan_en_error(self, app, db):
        from app.models import SituacionAprendizaje

        rota = self._sda_de(db, "rota@ies.es")
        buena = self._sda_de(db, "buena@ies.es")
        buena.estado = SituacionAprendizaje.GENERADA
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["ia", "diagnostico"])

        assert "rota@ies.es" in r.output
        assert "buena@ies.es" not in r.output

    def test_con_todas_se_ven_todas(self, app, db):
        from app.models import SituacionAprendizaje

        self._sda_de(db, "rota2@ies.es")
        buena = self._sda_de(db, "buena2@ies.es")
        buena.estado = SituacionAprendizaje.GENERADA
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["ia", "diagnostico", "--situaciones", "todas"])

        assert "buena2@ies.es" in r.output


# ---------------------------------------------------------------------------
# `flask usuarios proveedor`
# ---------------------------------------------------------------------------


class TestCambiarElProveedorDeUnaCuenta:
    """Se cambia desde la consola porque las SdA heredadas del TFG son de
    cuentas de prueba cuya contraseña puede que nadie recuerde, y el proveedor
    sale del **propietario** de la SdA, no de quien pulsa regenerar."""

    @pytest.fixture
    def cuenta(self, db):
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="estudio@ejemplo.com", nombre="Estudio", id_rol=rol.id_rol)
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        return u

    def test_sin_proveedor_solo_informa(self, app, db, cuenta):
        """Un comando que informa cuando no se le pide nada es más difícil de
        usar por error que uno que borre la preferencia al invocarlo sin
        argumentos."""
        r = app.test_cli_runner().invoke(args=["usuarios", "proveedor", cuenta.correo])

        assert r.exit_code == 0, r.output
        assert "usa el del sistema" in r.output
        db.session.refresh(cuenta)
        assert cuenta.proveedor_ia is None

    def test_una_cuenta_inexistente_falla_claro(self, app, db):
        r = app.test_cli_runner().invoke(args=["usuarios", "proveedor", "nadie@ies.es"])

        assert r.exit_code == 1
        assert "No hay ninguna cuenta" in r.output

    def test_un_proveedor_no_disponible_no_se_guarda_en_silencio(self, app, db, cuenta):
        """El fallo que costó una tarde: una preferencia guardada que luego se
        ignora. Aquí se avisa y no se guarda nada."""
        r = app.test_cli_runner().invoke(
            args=["usuarios", "proveedor", cuenta.correo, "--proveedor", "inventado"]
        )

        assert r.exit_code == 1
        assert "no está disponible" in r.output
        db.session.refresh(cuenta)
        assert cuenta.proveedor_ia is None

    def test_se_puede_volver_al_del_sistema(self, app, db, cuenta):
        cuenta.proveedor_ia = "fake"
        cuenta.modelo_ia = "fake"
        db.session.commit()

        r = app.test_cli_runner().invoke(
            args=["usuarios", "proveedor", cuenta.correo, "--proveedor", ""]
        )

        assert r.exit_code == 0, r.output
        db.session.refresh(cuenta)
        assert cuenta.proveedor_ia is None


class TestErrorGeneracionEsProvisional:
    """`error_generacion` significa dos cosas, y confundirlas cuesta trabajo.

    La tarea marca la SdA como `error_generacion` y **después** relanza, para
    que `autoretry_for` la reintente (hasta dos veces, con espera creciente).
    Así que mientras queden generaciones en curso, ese número es provisional.

    Lo descubrieron los datos, no el código: en una ejecución real varias SdA
    figuraron en error y acabaron en `generada` sin intervención. El comando
    afirmaba lo contrario.
    """

    def _sdas(self, db, en_curso=0, en_error=0):
        from app.models import SituacionAprendizaje

        for i in range(en_curso):
            _sda(db, "Lengua", titulo=f"Curso {i}").estado = SituacionAprendizaje.GENERANDO
        for i in range(en_error):
            _sda(db, "Lengua", titulo=f"Error {i}").estado = SituacionAprendizaje.ERROR_GENERACION
        db.session.commit()

    def test_con_algo_en_curso_los_errores_se_dicen_provisionales(self, app, db, catalogo_real):
        self._sdas(db, en_curso=1, en_error=2)

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])

        assert "PROVISIONAL" in r.output
        assert "se reintenta sola" in r.output

    def test_sin_nada_en_curso_los_errores_son_definitivos(self, app, db, catalogo_real):
        self._sdas(db, en_error=2)

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])

        assert "definitivo" in r.output
        assert "PROVISIONAL" not in r.output

    def test_regenerar_se_planta_si_hay_algo_en_curso(self, app, db, catalogo_real):
        """Relanzar sobre una SdA que espera su reintento pondría dos
        generaciones a la vez sobre la misma, pisándose sección a sección."""
        from unittest.mock import patch

        self._sdas(db, en_curso=1, en_error=1)

        with patch(
            "app.tasks.generacion.generar_situacion_completa.apply_async"
        ) as encolar:
            r = app.test_cli_runner().invoke(args=["curriculo", "regenerar"])

        assert r.exit_code == 1
        assert not encolar.called
        assert "esperando su reintento" in r.output

    def test_sin_nada_en_curso_sí_relanza(self, app, db, catalogo_real):
        from unittest.mock import patch

        self._sdas(db, en_error=1)

        with patch(
            "app.tasks.generacion.generar_situacion_completa.apply_async"
        ) as encolar:
            r = app.test_cli_runner().invoke(args=["curriculo", "regenerar"])

        assert r.exit_code == 0, r.output
        assert encolar.called


class TestLaLineaCanonica:
    """Existe para que los scripts no dependan de la prosa.

    `esperar.ps1` buscaba la frase «terminaron en error». Al reescribir ese
    mensaje —para decir que un error es provisional mientras haya generaciones
    en curso— el script dejó de detectarlos, y nada avisó: no hay test que
    ejecute un `.ps1`. La línea canónica desacopla las dos cosas.
    """

    def test_esta_siempre_aunque_no_haya_nada(self, app, db):
        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])
        assert "RESUMEN generando=0 error=0 total=0" in r.output

    def test_cuenta_bien_las_dos_cosas(self, app, db, catalogo_real):
        from app.models import SituacionAprendizaje

        _sda(db, "Lengua", titulo="a").estado = SituacionAprendizaje.GENERANDO
        _sda(db, "Lengua", titulo="b").estado = SituacionAprendizaje.ERROR_GENERACION
        _sda(db, "Lengua", titulo="c").estado = SituacionAprendizaje.GENERADA
        db.session.commit()

        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])
        assert "RESUMEN generando=1 error=1 total=3" in r.output

    def test_va_al_final_para_que_un_tail_1_la_encuentre(self, app, db):
        r = app.test_cli_runner().invoke(args=["curriculo", "estado"])
        assert r.output.strip().splitlines()[-1].startswith("RESUMEN ")
