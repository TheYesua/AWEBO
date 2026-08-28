"""Cada comunidad tiene su currículo, y ninguna ve el de otra.

EL PROBLEMA QUE ESTO CIERRA
----------------------------
Hasta ahora la base de datos guardaba **un único currículo**, implícitamente el
de Ceuta en castellano. `Competencia`, `CriterioEvaluacion` y `SaberBasico` se
identificaban por `codigo`, `materia` y `cursos_aplicables`, y nada más.

Todo funcionaba por accidente: mientras solo hubiera un decreto cargado, no
había con qué confundirse. En cuanto conviven dos, una SdA de Ceuta empieza a
citar criterios catalanes **sin que nada avise**. Los códigos se parecen —`CE1`,
`1.1`, `A.3` están en todas partes—, las descripciones son plausibles y el
documento sale completo. Solo se descubre al contrastarlo con el decreto propio,
que es exactamente cuando ya se ha usado en clase.

LO QUE MÁS SE PRUEBA AQUÍ
--------------------------
No que el filtro exista, sino que **no haya ninguna puerta trasera**. Son cinco
caminos distintos los que consultan el catálogo —el contexto de generación, los
enlaces, los dos endpoints de consulta, la cobertura y el mensaje de error— y
basta con que uno se olvide para que la separación no valga nada.
"""
from __future__ import annotations

import pytest


CURSO = "4º ESO"
MATERIA = "Lengua"


def _catalogo(db, comunidad: str, idioma: str, descripcion: str) -> None:
    """El MISMO código y la MISMA materia en dos comunidades.

    Es la trampa entera en tres líneas: si algo resuelve por código sin mirar
    la comunidad, se llevará las dos filas y no se notará.
    """
    from app.models import Competencia, CriterioEvaluacion, SaberBasico

    ce = Competencia(
        codigo="CE1", tipo=Competencia.ESPECIFICA, materia=MATERIA,
        comunidad=comunidad, etapa="ESO", idioma=idioma,
        cursos_aplicables=[CURSO], descriptores=[], descripcion=descripcion,
    )
    db.session.add(ce)
    db.session.flush()
    db.session.add_all([
        CriterioEvaluacion(
            codigo="1.1", id_competencia=ce.id_competencia, materia=MATERIA,
            comunidad=comunidad, etapa="ESO", idioma=idioma,
            cursos_aplicables=[CURSO], descripcion=descripcion,
        ),
        SaberBasico(
            codigo="A.1", bloque="Bloque", materia=MATERIA,
            comunidad=comunidad, etapa="ESO", idioma=idioma,
            cursos_aplicables=[CURSO], descripcion=descripcion,
        ),
    ])
    db.session.commit()


#: Una materia que SOLO existe en Cataluña.
#:
#: Sin ella, `/materias` devolvía «Lengua» en las dos comunidades y el test
#: pasaba igual quitando el filtro — lo destapó un sabotaje. Un catálogo de
#: prueba en el que las dos comunidades son idénticas no distingue nada.
MATERIA_SOLO_CATALANA = "Llengua Catalana"


@pytest.fixture
def dos_comunidades(db):
    from app.models import Competencia

    _catalogo(db, "ceuta", "es", "Texto de Ceuta")
    _catalogo(db, "cataluna", "ca", "Text de Catalunya")

    db.session.add(Competencia(
        codigo="CE1", tipo=Competencia.ESPECIFICA, materia=MATERIA_SOLO_CATALANA,
        comunidad="cataluna", etapa="ESO", idioma="ca",
        cursos_aplicables=[CURSO], descriptores=[], descripcion="Només a Catalunya",
    ))
    db.session.commit()


def _sda(db, comunidad_texto, correo="d@ies.es"):
    from app.models import Rol, SituacionAprendizaje, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = db.session.query(Usuario).filter_by(correo=correo).first()
    if u is None:
        u = Usuario(correo=correo, nombre="D", id_rol=rol.id_rol,
                    comunidad_autonoma=comunidad_texto)
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()

    s = SituacionAprendizaje(
        titulo="X", materia=MATERIA, curso=CURSO, id_usuario=u.id_usuario,
        comunidad_autonoma=comunidad_texto, contenido={},
    )
    db.session.add(s)
    db.session.commit()
    return s


class TestElContextoDeGeneracion:
    """El camino por el que el currículo llega al modelo."""

    def test_una_sda_de_ceuta_solo_ve_ceuta(self, app, db, dos_comunidades):
        from app.prompts.contexto import construir_contexto

        sda = _sda(db, "Ceuta")
        with app.test_request_context():
            ctx = construir_contexto(sda)

        # `ContextoGeneracion` guarda diccionarios, no filas: es lo que se
        # serializa al prompt.
        assert len(ctx.competencias) == 1
        assert ctx.competencias[0]["descripcion"] == "Texto de Ceuta"
        assert all(c["descripcion"] == "Texto de Ceuta" for c in ctx.criterios)

    def test_una_sda_catalana_solo_ve_Cataluña(self, app, db, dos_comunidades):
        from app.prompts.contexto import construir_contexto

        sda = _sda(db, "Cataluña", correo="cat@ies.es")
        with app.test_request_context():
            ctx = construir_contexto(sda)

        assert [c["descripcion"] for c in ctx.competencias] == ["Text de Catalunya"]

    def test_sin_comunidad_no_hay_curriculo(self, app, db, dos_comunidades):
        """Deliberado, y es la decisión que más se nota.

        La alternativa —caer a Ceuta— generaría un documento anclado a una
        normativa que no es la de quien lo pide, sin decirlo. Con esto, el
        contexto sale vacío y `_exigir_curriculo` rechaza la generación antes
        de gastarla.
        """
        from app.prompts.contexto import construir_contexto

        sda = _sda(db, None, correo="sin@ies.es")
        with app.test_request_context():
            ctx = construir_contexto(sda)

        assert ctx.competencias == []
        assert ctx.tiene_curriculo() is False

    def test_una_comunidad_irreconocible_tampoco(self, app, db, dos_comunidades):
        from app.prompts.contexto import construir_contexto

        sda = _sda(db, "Wakanda", correo="wak@ies.es")
        with app.test_request_context():
            assert construir_contexto(sda).tiene_curriculo() is False


class TestElTextoLibreSeNormaliza:
    """`comunidad_autonoma` lleva siendo texto libre desde el TFG.

    Un `<input type="text">` con «Ceuta» escrito por defecto. Mientras nadie
    filtraba por él daba igual; ahora decide qué normativa se aplica, y no
    puede depender de cómo teclee cada persona.
    """

    @pytest.mark.parametrize("escrito", [
        "Cataluña", "cataluña", "CATALUÑA", "  Cataluña  ",
        "Catalunya", "cataluna",
    ])
    def test_todas_estas_formas_llegan_al_mismo_curriculo(
        self, app, db, dos_comunidades, escrito
    ):
        from app.prompts.contexto import construir_contexto

        sda = _sda(db, escrito, correo=f"{abs(hash(escrito))}@ies.es")
        with app.test_request_context():
            ctx = construir_contexto(sda)

        assert [c["descripcion"] for c in ctx.competencias] == ["Text de Catalunya"]

    def test_euskadi_es_pais_vasco(self, db):
        from app.curriculo import comunidades

        assert comunidades.normalizar("Euskadi") == "pais-vasco"
        assert comunidades.normalizar("País Vasco") == "pais-vasco"

    def test_lo_que_no_se_reconoce_devuelve_None_y_no_el_defecto(self, db):
        """Devolver `POR_DEFECTO` ante lo desconocido sería el error caro:
        anclar en silencio a una normativa que no es la de quien pide."""
        from app.curriculo import comunidades

        assert comunidades.normalizar("Wakanda") is None
        assert comunidades.normalizar("") is None
        assert comunidades.normalizar(None) is None


class TestLosEnlacesCurriculares:
    """El otro camino que resuelve códigos contra el catálogo."""

    def test_no_se_enlaza_el_criterio_de_otra_comunidad(self, app, db, dos_comunidades):
        from app.services.enlaces_curriculares import sincronizar

        sda = _sda(db, "Ceuta")
        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}],
            "criterios": [{"codigo": "1.1"}],
            "saberes": [{"codigo": "A.1"}],
        }}
        db.session.commit()

        sincronizar(sda)

        assert len(sda.competencias) == 1, "CE1 existe en las dos comunidades"
        assert sda.competencias[0].comunidad == "ceuta"
        assert all(c.comunidad == "ceuta" for c in sda.criterios)
        assert all(s.comunidad == "ceuta" for s in sda.saberes)

    def test_sin_comunidad_reconocida_se_marca_sin_curriculo(self, app, db, dos_comunidades):
        from app.services.enlaces_curriculares import sincronizar

        sda = _sda(db, "Wakanda", correo="w2@ies.es")
        sda.contenido = {"conexion_curricular": {"competencias": [{"codigo": "CE1"}]}}
        db.session.commit()

        resumen = sincronizar(sda)
        assert resumen["sin_curriculo"] is True
        assert sda.competencias == []


class TestLosEndpointsDeConsulta:
    """Los desplegables del formulario.

    Si ofrecieran materias de otra comunidad, el docente elegiría una y la
    generación se rechazaría después por falta de currículo: un callejón sin
    salida servido por la propia interfaz.
    """

    def _entrar(self, client, db, comunidad_texto, correo):
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo=correo, nombre="D", id_rol=rol.id_rol,
                    comunidad_autonoma=comunidad_texto)
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": correo, "contrasena": "ContrasenaDoc1"})
        return u

    def test_las_competencias_son_las_de_su_comunidad(self, client, db, dos_comunidades):
        self._entrar(client, db, "Ceuta", "e1@ies.es")

        cuerpo = client.get("/api/curriculo/competencias").get_json()

        assert len(cuerpo) == 1
        assert cuerpo[0]["descripcion"] == "Texto de Ceuta"

    def test_las_materias_ofrecidas_son_solo_las_suyas(self, client, db, dos_comunidades):
        """El desplegable del formulario.

        Ofrecerle a un docente de Ceuta una materia que solo existe en el
        catálogo catalán le deja elegirla y le falla la generación después: un
        callejón sin salida servido por la propia interfaz.
        """
        self._entrar(client, db, "Ceuta", "e1b@ies.es")

        materias = client.get("/api/curriculo/materias").get_json()

        assert MATERIA in materias
        assert MATERIA_SOLO_CATALANA not in materias

    def test_y_a_quien_le_corresponde_sí_se_la_ofrece(self, client, db, dos_comunidades):
        """La otra mitad: filtrar de más sería tan malo como no filtrar."""
        self._entrar(client, db, "Cataluña", "e1c@ies.es")

        materias = client.get("/api/curriculo/materias").get_json()

        assert MATERIA_SOLO_CATALANA in materias

    def test_otro_docente_ve_las_suyas(self, client, db, dos_comunidades):
        self._entrar(client, db, "Cataluña", "e2@ies.es")

        cuerpo = client.get("/api/curriculo/competencias").get_json()

        descripciones = {c["descripcion"] for c in cuerpo}
        assert "Text de Catalunya" in descripciones
        assert "Texto de Ceuta" not in descripciones

    def test_la_cobertura_tambien(self, client, db, dos_comunidades):
        """Es la que alimenta los dos desplegables acoplados del formulario."""
        self._entrar(client, db, "Ceuta", "e3@ies.es")

        cuerpo = client.get("/api/curriculo/cobertura").get_json()

        assert cuerpo == [{"materia": MATERIA, "cursos": [CURSO]}]

    def test_sin_comunidad_no_se_ofrece_nada(self, client, db, dos_comunidades):
        """Enseñarle un catálogo que no va a poder usar es peor que no
        enseñarle ninguno: le deja elegir y le falla después."""
        self._entrar(client, db, None, "e4@ies.es")

        assert client.get("/api/curriculo/materias").get_json() == []
        assert client.get("/api/curriculo/cobertura").get_json() == []

    def test_sin_parametro_manda_el_perfil(self, client, db, dos_comunidades):
        self._entrar(client, db, "Ceuta", "e5@ies.es")

        cuerpo = client.get("/api/curriculo/competencias").get_json()

        assert [c["descripcion"] for c in cuerpo] == ["Texto de Ceuta"]

    def test_con_provincia_manda_la_provincia(self, client, db, dos_comunidades):
        """DECISIÓN REVISADA el 13/08.

        Antes la comunidad salía **solo** del perfil, y había un test que lo
        fijaba: aceptarla por parámetro «dejaría que el formulario ofreciera
        materias de una comunidad para una SdA que se genera contra otra».

        Ese argumento se cayó cuando el formulario ganó su propio selector de
        provincia. Ahora una SdA puede generarse contra otra comunidad a
        propósito, y negarle al desplegable la provincia elegida produce el
        mismo desajuste, pero al revés: ofrecería las materias del perfil para
        una SdA que se va a generar contra otro currículo.
        """
        self._entrar(client, db, "Ceuta", "e6@ies.es")

        cuerpo = client.get(
            "/api/curriculo/competencias?provincia=barcelona"
        ).get_json()

        descripciones = {c["descripcion"] for c in cuerpo}
        assert "Text de Catalunya" in descripciones
        assert "Texto de Ceuta" not in descripciones

    def test_una_provincia_irreconocible_no_cae_al_perfil(self, client, db, dos_comunidades):
        """Caer al perfil ante una provincia que no existe daría materias de
        Ceuta a quien pidió las de otro sitio, sin decírselo."""
        self._entrar(client, db, "Ceuta", "e7@ies.es")

        cuerpo = client.get("/api/curriculo/competencias?provincia=wakanda").get_json()

        assert cuerpo == []


class TestElMensajeDeError:
    """Los dos fallos se arreglan de formas distintas, así que se distinguen."""

    def _entrar(self, client, db, comunidad_texto, correo):
        from app.models import Rol, SituacionAprendizaje, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo=correo, nombre="D", id_rol=rol.id_rol,
                    comunidad_autonoma=comunidad_texto)
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": correo, "contrasena": "ContrasenaDoc1"})

        s = SituacionAprendizaje(
            titulo="X", materia="Materia Inexistente", curso=CURSO,
            id_usuario=u.id_usuario, comunidad_autonoma=comunidad_texto, contenido={},
        )
        db.session.add(s)
        db.session.commit()
        return s

    def test_comunidad_irreconocible_lo_dice_asi(self, client, db, dos_comunidades):
        sda = self._entrar(client, db, "Wakanda", "m1@ies.es")

        r = client.post(f"/api/situaciones/{sda.id_situacion}/generar")

        assert r.status_code == 422
        assert r.get_json()["error"] == "sin_comunidad"

    def test_materia_sin_curriculo_lo_dice_de_otra_forma(self, client, db, dos_comunidades):
        sda = self._entrar(client, db, "Ceuta", "m2@ies.es")

        r = client.post(f"/api/situaciones/{sda.id_situacion}/generar")

        assert r.status_code == 422
        assert r.get_json()["error"] == "sin_curriculo"
        assert "Ceuta" in r.get_json()["mensaje"], "hay que decir de qué comunidad se habla"

    def test_las_alternativas_son_de_su_comunidad(self, client, db, dos_comunidades):
        """Sugerirle materias que solo existen en otro catálogo sería llevarle
        a otro callejón sin salida."""
        sda = self._entrar(client, db, "Ceuta", "m3@ies.es")

        mensaje = client.post(f"/api/situaciones/{sda.id_situacion}/generar").get_json()["mensaje"]

        assert MATERIA in mensaje


class TestElSeedNoMezcla:
    def test_cargar_dos_comunidades_no_pisa_la_primera(self, app, db, tmp_path):
        """Sin la comunidad en la clave del upsert, el segundo decreto
        **actualizaría** las filas del primero en vez de añadir las suyas: el
        código y la materia coinciden. El currículo de Ceuta acabaría con las
        descripciones catalanas y nadie lo notaría."""
        import json

        from app.models import Competencia
        from app.seeds import seed_curriculo

        fichero = {
            "materia": MATERIA, "cursos_aplicables": [CURSO],
            "competencias_especificas": [
                {"codigo": "CE1", "descripcion": "DESC", "descriptores": []}
            ],
            "criterios_evaluacion": [], "saberes_basicos": [],
        }
        (tmp_path / "lengua.json").write_text(json.dumps(fichero), encoding="utf-8")

        seed_curriculo(tmp_path, comunidad="ceuta", idioma="es")
        seed_curriculo(tmp_path, comunidad="cataluna", idioma="ca")

        filas = db.session.query(Competencia).filter_by(codigo="CE1").all()
        assert {f.comunidad for f in filas} == {"ceuta", "cataluna"}
        assert {f.idioma for f in filas} == {"es", "ca"}

    def test_una_comunidad_inventada_no_carga_nada(self, app, db, tmp_path):
        """Dos mil filas bajo un código inventado obligarían a borrarlas a
        mano, y no hay ningún comando para eso."""
        from app.seeds import seed_curriculo

        with pytest.raises(ValueError, match="no reconocida"):
            seed_curriculo(tmp_path, comunidad="Wakanda")

    def test_el_fichero_manda_sobre_la_opcion(self, app, db, tmp_path):
        """El dato correcto es el del extractor, no el de quien teclea la
        orden: al revés se podría cargar el decreto catalán como si fuera de
        Ceuta por una opción mal puesta."""
        import json

        from app.models import Competencia
        from app.seeds import seed_curriculo

        fichero = {
            "materia": MATERIA, "cursos_aplicables": [CURSO],
            "comunidad": "cataluna", "idioma": "ca",
            "competencias_especificas": [
                {"codigo": "CE9", "descripcion": "D", "descriptores": []}
            ],
            "criterios_evaluacion": [], "saberes_basicos": [],
        }
        (tmp_path / "x.json").write_text(json.dumps(fichero), encoding="utf-8")

        seed_curriculo(tmp_path, comunidad="ceuta", idioma="es")

        fila = db.session.query(Competencia).filter_by(codigo="CE9").one()
        assert (fila.comunidad, fila.idioma) == ("cataluna", "ca")


# ---------------------------------------------------------------------------
# La provincia: lo que el docente elige
# ---------------------------------------------------------------------------


class TestElCatalogoDeProvincias:
    """El currículo va por comunidad; el desplegable, por provincia.

    Andalucía tiene ocho provincias y **un solo decreto**. Guardar el currículo
    por provincia sería duplicarlo ocho veces, con ocho sitios donde puede
    desincronizarse. Así que se pregunta la provincia y se deriva la comunidad:
    la agrupación del desplegable no es decorativa, es la relación real.
    """

    def test_toda_provincia_pertenece_a_una_comunidad_que_existe(self):
        from app.curriculo import comunidades, provincias

        huerfanas = {
            c for _n, c in provincias.PROVINCIAS.values()
            if c not in comunidades.COMUNIDADES
        }
        assert huerfanas == set()

    def test_toda_comunidad_tiene_al_menos_una_provincia(self):
        """Si no, su currículo sería inalcanzable desde el formulario: nadie
        podría elegir un sitio que lo use."""
        from app.curriculo import comunidades, provincias

        con_provincia = {c for _n, c in provincias.PROVINCIAS.values()}
        assert set(comunidades.COMUNIDADES) - con_provincia == set()

    @pytest.mark.parametrize("escrito, esperada", [
        ("Sevilla", "andalucia"),
        ("Lérida", "cataluna"),          # nombre en castellano
        ("Lleida", "cataluna"),
        ("Vizcaya", "pais-vasco"),
        ("Álava", "pais-vasco"),
        ("A Coruña", "galicia"),
        ("Ceuta", "ceuta"),
    ])
    def test_la_comunidad_se_deriva_de_la_provincia(self, escrito, esperada):
        from app.curriculo import provincias

        assert provincias.comunidad_de(escrito) == esperada

    def test_las_ocho_de_andalucia_dan_la_misma_comunidad(self):
        """El motivo de todo el diseño, en un test."""
        from app.curriculo import provincias

        andaluzas = ["almeria", "cadiz", "cordoba", "granada",
                     "huelva", "jaen", "malaga", "sevilla"]
        assert {provincias.comunidad_de(p) for p in andaluzas} == {"andalucia"}

    def test_agrupadas_pone_delante_las_que_tienen_curriculo_previsto(self):
        from app.curriculo import provincias

        etiquetas = [e for e, _ps in provincias.agrupadas()]
        assert etiquetas[:5] == ["Ceuta", "Andalucía", "Cataluña", "Galicia", "País Vasco"]


class TestLasDosColumnasNoDivergen:
    """`provincia` y `comunidad_autonoma` son dos columnas y una decisión.

    La provincia es lo que se elige; la comunidad es lo que se calcula. Si se
    pudieran escribir por separado, tendríamos una SdA que dice ser de Sevilla
    y genera con el currículo de Cataluña, sin forma de saber cuál miente.
    """

    def test_fijar_la_provincia_escribe_la_comunidad(self, db):
        from app.models import Rol, Usuario
        from app.services import geografia

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="g1@ies.es", nombre="G", id_rol=rol.id_rol)
        u.set_password("ContrasenaDoc1")

        geografia.fijar_provincia(u, "Sevilla")

        assert u.provincia == "sevilla"
        assert u.comunidad_autonoma == "Andalucía"

    def test_una_provincia_irreconocible_limpia_las_dos(self, db):
        """Quedarse con la anterior daría un objeto que dice ser de un sitio y
        genera contra el currículo de otro."""
        from app.models import Rol, Usuario
        from app.services import geografia

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="g2@ies.es", nombre="G", id_rol=rol.id_rol)
        u.set_password("ContrasenaDoc1")
        geografia.fijar_provincia(u, "Sevilla")

        geografia.fijar_provincia(u, "Wakanda")

        assert u.provincia is None
        assert u.comunidad_autonoma is None

    def test_el_endpoint_del_perfil_no_acepta_la_comunidad_suelta(self, client, db):
        """Un PUT con las dos incoherentes —Sevilla y «Cataluña»— se guardaría
        tal cual si se aceptaran por separado."""
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="g3@ies.es", nombre="G", id_rol=rol.id_rol)
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": "g3@ies.es", "contrasena": "ContrasenaDoc1"})

        client.put("/me", json={"provincia": "sevilla", "comunidad_autonoma": "Cataluña"})

        db.session.refresh(u)
        assert u.provincia == "sevilla"
        assert u.comunidad_autonoma == "Andalucía"

    def test_la_comunidad_sola_no_se_guarda(self, client, db):
        """El caso donde el `pop` importa de verdad, y que faltaba.

        Con provincia y comunidad a la vez, el orden salva: `fijar_provincia`
        va después y sobrescribe. Pero mandando **solo** la comunidad no hay
        nada que la sobrescriba, y sin el `pop` se guardaría suelta — dejando
        una cuenta cuya comunidad no sale de ninguna provincia.

        Lo destapó un sabotaje que no rompía ningún test.
        """
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="g4@ies.es", nombre="G", id_rol=rol.id_rol,
                    provincia="sevilla", comunidad_autonoma="Andalucía")
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": "g4@ies.es", "contrasena": "ContrasenaDoc1"})

        client.put("/me", json={"comunidad_autonoma": "Cataluña"})

        db.session.refresh(u)
        assert u.comunidad_autonoma == "Andalucía", "no se acepta suelta"
        assert u.provincia == "sevilla"


class TestElFormulario:
    """El bloqueo, y que no dependa del color."""

    def _entrar(self, client, db):
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="form@ies.es", nombre="F", id_rol=rol.id_rol,
                    provincia="ceuta", comunidad_autonoma="Ceuta")
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": "form@ies.es", "contrasena": "ContrasenaDoc1"})

    def test_curso_y_materia_llegan_deshabilitados(self, client, db):
        self._entrar(client, db)

        html = client.get("/situaciones/nueva").get_data(as_text=True)

        curso = html[html.index('id="curso"'):html.index('id="curso"') + 200]
        assert "disabled" in curso

    def test_el_motivo_va_en_un_texto_asociado_y_no_solo_en_el_color(self, client, db):
        """WCAG 1.4.1: el color no puede ser el único medio. Un lector de
        pantalla no ve el gris; lee `aria-describedby`."""
        self._entrar(client, db)

        html = client.get("/situaciones/nueva").get_data(as_text=True)

        assert 'aria-describedby="bloqueo-aviso"' in html
        assert 'id="bloqueo-aviso"' in html
        assert "Elige antes la provincia" in html

    def test_ya_no_hay_campo_de_texto_libre_para_la_comunidad(self, client, db):
        """Era la puerta por la que entraban las erratas que `normalizar()`
        tiene que absorber."""
        self._entrar(client, db)

        html = client.get("/situaciones/nueva").get_data(as_text=True)

        assert 'name="comunidad_autonoma"' not in html
        assert 'id="provincia"' in html

    def test_el_desplegable_viene_agrupado_por_comunidad(self, client, db, dos_comunidades):
        self._entrar(client, db)

        grupos = client.get("/api/curriculo/provincias").get_json()

        andalucia = next(g for g in grupos if g["comunidad"] == "Andalucía")
        assert len(andalucia["provincias"]) == 8
        assert {p["nombre"] for p in andalucia["provincias"]} >= {"Sevilla", "Cádiz"}

    def test_se_marca_cual_no_tiene_curriculo_en_vez_de_esconderla(self, client, db, dos_comunidades):
        """Un docente de Aragón existe aunque AWEBO no tenga su decreto.
        Esconderle su provincia no la hace desaparecer: le deja sin entender
        qué se espera que elija."""
        self._entrar(client, db)

        grupos = client.get("/api/curriculo/provincias").get_json()
        por_nombre = {p["nombre"]: p for g in grupos for p in g["provincias"]}

        assert por_nombre["Zaragoza"]["tiene_curriculo"] is False
        assert por_nombre["Barcelona"]["tiene_curriculo"] is True


class TestLaSdAHeredaLaProvincia:
    def test_al_crearla_sin_decir_nada(self, client, db):
        from app.models import Rol, SituacionAprendizaje, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="h1@ies.es", nombre="H", id_rol=rol.id_rol,
                    provincia="sevilla", comunidad_autonoma="Andalucía")
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()

        from app.services import situacion_service as svc

        sa = svc.crear(u, {"titulo": "X", "curso": CURSO, "materia": MATERIA})

        assert sa.provincia == "sevilla"
        assert sa.comunidad_autonoma == "Andalucía"

    def test_pero_se_puede_cambiar_en_esa_situacion(self, client, db):
        """Quien da clase en dos sitios, o prepara material para otra
        comunidad, no tiene que cambiar su perfil para ello."""
        from app.models import Rol, Usuario
        from app.services import situacion_service as svc

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="h2@ies.es", nombre="H", id_rol=rol.id_rol,
                    provincia="sevilla", comunidad_autonoma="Andalucía")
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()

        sa = svc.crear(u, {"titulo": "X", "curso": CURSO, "materia": MATERIA,
                           "provincia": "barcelona"})

        assert sa.provincia == "barcelona"
        assert sa.comunidad_autonoma == "Cataluña"


class TestLasTresPuertasDelDato:
    """Registro, perfil y formulario de SdA.

    Se hizo primero solo el formulario de SdA, y Jesús lo detectó abriendo el
    perfil: seguía siendo un `<input type="text">`. Con una sola de las tres
    puertas convertida, el texto libre sigue entrando por las otras dos — y la
    del registro es la peor, porque la cuenta nace con la errata y la arrastra.
    """

    def _entrar(self, client, db, correo="puertas@ies.es"):
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo=correo, nombre="P", id_rol=rol.id_rol,
                    provincia="ceuta", comunidad_autonoma="Ceuta")
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": correo, "contrasena": "ContrasenaDoc1"})

    @pytest.mark.parametrize("ruta, con_sesion", [
        ("/register", False),
        ("/perfil", True),
        ("/situaciones/nueva", True),
    ])
    def test_ninguna_pide_la_comunidad_como_texto_libre(self, client, db, ruta, con_sesion):
        if con_sesion:
            self._entrar(client, db, f"p{abs(hash(ruta))}@ies.es")

        html = client.get(ruta).get_data(as_text=True)

        assert 'name="comunidad_autonoma"' not in html, f"{ruta} sigue con texto libre"
        assert 'id="provincia"' in html, f"{ruta} no ofrece la provincia"

    def test_el_registro_trae_el_catalogo_incrustado(self, client, db):
        """Sin sesión no se puede consultar `/api/curriculo/provincias`, que
        exige login. Si el desplegable dependiera de ese fetch, en el registro
        saldría vacío — y nadie podría elegir provincia al darse de alta."""
        html = client.get("/register").get_data(as_text=True)

        # Se buscan nombres SIN tilde: `|tojson` escapa los no-ASCII, así que
        # «Andalucía» aparece como «Andaluc\u00eda». El navegador lo interpreta
        # bien; una aserción sobre el literal acentuado no.
        assert "Sevilla" in html
        assert "Barcelona" in html

    def test_el_perfil_devuelve_la_provincia_guardada(self, client, db):
        """El `<select>` se rellena con lo que diga `/me`. Si el endpoint no la
        expusiera, el desplegable saldría siempre en «Sin especificar» aunque
        la cuenta tuviera provincia."""
        self._entrar(client, db, "perfil-prov@ies.es")

        cuerpo = client.get("/me").get_json()

        assert cuerpo["provincia"] == "ceuta"


class TestLaCuartaPuerta:
    """La SdA ya creada, que se editaba sin poder tocar la provincia.

    Las tres puertas de arriba —registro, perfil, formulario de nueva— cubren
    la *entrada* del dato. Faltaba la cuarta: una SdA existente. Jesús lo vio
    enseguida: «en una situación ya creada previamente, no veo selector de
    provincia». Sin él, una SdA nacida con la provincia equivocada se quedaba
    así para siempre, y la única salida era borrarla y volver a empezar.
    """

    def _docente(self, client, db, correo="cuarta@ies.es", provincia="ceuta"):
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo=correo, nombre="C", id_rol=rol.id_rol,
                    provincia=provincia, comunidad_autonoma="Ceuta")
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": correo, "contrasena": "ContrasenaDoc1"})
        return u

    def _sda(self, db, u, provincia="ceuta", comunidad="Ceuta"):
        from app.models import SituacionAprendizaje

        s = SituacionAprendizaje(
            titulo="X", materia=MATERIA, curso=CURSO, id_usuario=u.id_usuario,
            provincia=provincia, comunidad_autonoma=comunidad, contenido={},
        )
        db.session.add(s)
        db.session.commit()
        return s

    def test_la_pagina_de_detalle_ofrece_el_desplegable(self, client, db):
        u = self._docente(client, db)
        sda = self._sda(db, u)

        r = client.get(f"/situaciones/{sda.id_situacion}")

        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert 'id="provincia"' in html, "la SdA ya creada no deja cambiar la provincia"
        assert 'name="comunidad_autonoma"' not in html

    def test_el_detalle_devuelve_la_provincia_para_preseleccionarla(self, client, db):
        """Sin este campo en la respuesta, el desplegable saldría en blanco y
        el primer guardado mandaría la provincia vacía o la del perfil, como si
        el docente la hubiera cambiado a propósito."""
        u = self._docente(client, db)
        sda = self._sda(db, u)

        r = client.get(f"/api/situaciones/{sda.id_situacion}")

        assert r.status_code == 200, r.get_json()
        assert r.get_json()["provincia"] == "ceuta"

    def test_cambiar_la_provincia_recalcula_la_comunidad(self, client, db):
        """Lo que este test protege NO es que se guarde la provincia: es que la
        comunidad se recalcule con ella. `actualizar` aplicaba los cambios con
        `setattr` en bucle, así que la provincia pasaba a «sevilla» y la
        comunidad se quedaba en «Ceuta». Las dos columnas son plausibles por
        separado; la incoherencia solo aparece al generar, contra el currículo
        equivocado y sin ninguna pista de por qué."""
        u = self._docente(client, db)
        sda = self._sda(db, u)

        r = client.put(f"/api/situaciones/{sda.id_situacion}", json={"provincia": "sevilla"})

        assert r.status_code == 200
        db.session.refresh(sda)
        assert sda.provincia == "sevilla"
        assert sda.comunidad_autonoma == "Andalucía", (
            f"la comunidad no siguió a la provincia: {sda.comunidad_autonoma!r}"
        )

    def test_una_provincia_que_no_existe_se_rechaza_sin_borrar_la_buena(self, client, db):
        """Rechazar, no limpiar. Al crear, quedarse sin provincia es un estado
        inicial normal; al editar significa perder la que ya tenía porque el
        cliente mandó una errata."""
        u = self._docente(client, db)
        sda = self._sda(db, u)

        r = client.put(f"/api/situaciones/{sda.id_situacion}", json={"provincia": "Wakanda"})

        assert r.status_code == 422
        db.session.refresh(sda)
        assert sda.provincia == "ceuta"
        assert sda.comunidad_autonoma == "Ceuta"

    def test_cambiar_solo_la_provincia_cuenta_como_cambio(self, client, db):
        """`actualizar` sale sin hacer nada si el diccionario queda vacío, y la
        provincia se saca de él antes de esa comprobación. Si no se tuviera en
        cuenta, guardar solo el cambio de provincia no haría absolutamente
        nada y la página diría «Cambios guardados correctamente»."""
        u = self._docente(client, db)
        sda = self._sda(db, u)

        r = client.put(f"/api/situaciones/{sda.id_situacion}", json={"provincia": "barcelona"})

        assert r.status_code == 200, r.get_json()
        db.session.refresh(sda)
        assert sda.provincia == "barcelona"

    def test_la_comunidad_suelta_no_se_cuela(self, client, db):
        """El esquema la sigue aceptando para no romper clientes viejos, pero
        se descarta: si se pudiera escribir sola, volveríamos a tener dos
        columnas contando cosas distintas.

        El título va aquí para comprobar que el resto del PUT SÍ se aplica: sin
        él, un 4xx daría el mismo resultado que descartar la comunidad y el
        test pasaría sin haber ejercitado nada. Y tiene que medir al menos dos
        caracteres, que es lo que exige `SituacionUpdateIn`.
        """
        u = self._docente(client, db)
        sda = self._sda(db, u)

        r = client.put(
            f"/api/situaciones/{sda.id_situacion}",
            json={"titulo": "Título nuevo", "comunidad_autonoma": "Cataluña"},
        )

        assert r.status_code == 200, r.get_json()
        db.session.refresh(sda)
        assert sda.titulo == "Título nuevo"
        assert sda.comunidad_autonoma == "Ceuta"


class TestLaQuintaPuerta:
    """El listado, que ofrecía el catálogo de la comunidad del perfil.

    Las cuatro puertas por las que entra la provincia —registro, perfil, SdA
    nueva y SdA ya creada— dejaban fuera una quinta: **los filtros del
    listado**. Ahí `Cobertura.cargar()` se llamaba sin provincia, o sea con la
    del perfil, así que un docente de Ceuta que cambiaba la interfaz a catalán
    seguía viendo «Matemáticas» y no encontraba sus propias SdA catalanas.

    Y curso y materia se rellenaban por separado, sin acotarse entre ellos: el
    filtro volvía a ofrecer «Matemáticas · 4º ESO», que no existe. El mismo
    fallo del 03/08, en el único sitio que se había quedado sin arreglar.
    """

    def _entrar(self, client, db, correo="quinta@ies.es"):
        from app.models import Rol, Usuario

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo=correo, nombre="Q", id_rol=rol.id_rol,
                    provincia="ceuta", comunidad_autonoma="Ceuta")
        u.set_password("ContrasenaDoc1")
        db.session.add(u)
        db.session.commit()
        client.post("/auth/login", json={"correo": correo, "contrasena": "ContrasenaDoc1"})

    def test_el_listado_ofrece_elegir_provincia(self, client, db):
        self._entrar(client, db)

        html = client.get("/situaciones").get_data(as_text=True)

        assert 'id="f-provincia"' in html

    def test_el_catalogo_del_filtro_se_acota_entre_curso_y_materia(self, client, db):
        """`Cobertura.enlazar` es quien restringe los dos desplegables entre sí.
        Sin él, cada uno se rellena por su cuenta y vuelven las combinaciones
        imposibles."""
        self._entrar(client, db, "quinta2@ies.es")

        html = client.get("/situaciones").get_data(as_text=True)

        assert "Cobertura.enlazar(" in html
        assert "Cobertura.enlazarProvincia(" in html

    def test_la_provincia_del_filtro_viaja_al_servidor(self, client, db):
        """INVERTIDO EL 16/08, y conviene contar por qué.

        Este test decía lo contrario: que la provincia **no** debía llevar
        `name`, porque «no filtra situaciones, solo decide qué materias se
        ofrecen; mandarla sería inventar un filtro que el servidor ignora».

        Estaba fijando como correcta una decisión que en la práctica era un
        fallo: elegir «Barcelona» y seguir viendo las SdA de Sevilla es un
        filtro que no filtra. El razonamiento describía el mecanismo —el
        endpoint no aceptaba el parámetro— en vez de preguntarse si debía
        aceptarlo.

        Es un buen recordatorio de que un test verde no dice que algo esté
        bien: dice que hace lo que alguien decidió, y esa decisión puede estar
        equivocada. El fallo sobrevivió un día entero **con su test en verde**.
        """
        self._entrar(client, db, "quinta3@ies.es")

        html = client.get("/situaciones").get_data(as_text=True)
        i = html.index('id="f-provincia"')

        assert 'name="provincia"' in html[i - 200:i + 200]
