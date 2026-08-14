"""Las SdA quedan enlazadas con las filas reales del catálogo.

QUÉ SE ESTABA PERDIENDO
------------------------
`conexion_curricular` guarda códigos: `"CE1"`, `"1.1"`, `"A.3"`. Un código no
es una referencia, es una cadena que se le parece. Las cuatro tablas de enlace
existían desde el TFG para convertirlos en referencias de verdad y **nadie
escribía nunca en ellas**: 39 SdA, 0 enlaces, y cuatro consultas por carga que
siempre volvían vacías.

LO QUE MÁS IMPORTA DE ESTE FICHERO
-----------------------------------
No es que los enlaces se escriban —eso es la parte fácil—, sino que se escriban
**los correctos**. Los códigos no son únicos: `"1.1"` existe en todas las
materias. Enlazar por código a secas ataría la SdA al criterio de otra
asignatura, y eso es peor que no enlazar nada, porque parece bien.
"""
from __future__ import annotations

import pytest


MATERIA = "Matemáticas A"
CURSO = "4º ESO"


@pytest.fixture
def catalogo(db):
    """Un catálogo mínimo con la trampa dentro: el mismo código en dos materias."""
    from app.models import Competencia, CriterioEvaluacion, SaberBasico

    filas = [
        Competencia(
            comunidad="ceuta",
            idioma="es",
            codigo="CE1", tipo=Competencia.ESPECIFICA, materia=MATERIA,
                    cursos_aplicables=[CURSO], descriptores=[], descripcion="Resolver"),
        Competencia(
            comunidad="ceuta",
            idioma="es",
            codigo="CE2", tipo=Competencia.ESPECIFICA, materia=MATERIA,
                    cursos_aplicables=[CURSO], descriptores=[], descripcion="Modelizar"),
        # Clave: sin materia. Vale para cualquiera y no debe quedar excluida.
        Competencia(
            comunidad="ceuta",
            idioma="es",
            codigo="CCL", tipo=Competencia.PRINCIPAL, materia=None,
                    cursos_aplicables=[CURSO], descriptores=[], descripcion="Lingüística"),
        # LA TRAMPA: mismo código, otra materia.
        Competencia(
            comunidad="ceuta",
            idioma="es",
            codigo="CE1", tipo=Competencia.ESPECIFICA, materia="Biología y Geología",
                    cursos_aplicables=[CURSO], descriptores=[], descripcion="Otra cosa"),
    ]
    db.session.add_all(filas)
    db.session.flush()

    ce1 = next(f for f in filas if f.codigo == "CE1" and f.materia == MATERIA)
    db.session.add_all([
        CriterioEvaluacion(
            comunidad="ceuta",
            idioma="es",
            codigo="1.1", id_competencia=ce1.id_competencia,
                           materia=MATERIA, cursos_aplicables=[CURSO], descripcion="x"),
        # Mismo código, otro curso: tampoco debe colarse.
        CriterioEvaluacion(
            comunidad="ceuta",
            idioma="es",
            codigo="1.1", id_competencia=ce1.id_competencia,
                           materia=MATERIA, cursos_aplicables=["1º ESO"], descripcion="y"),
        SaberBasico(
            comunidad="ceuta",
            idioma="es",
            codigo="A.3", bloque="Sentido numérico", materia=MATERIA,
                    cursos_aplicables=[CURSO], descripcion="z"),
    ])
    db.session.commit()
    return filas


@pytest.fixture
def sda(db, catalogo):
    from app.models import Rol, SituacionAprendizaje, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="docente.enlaces@ies.es", nombre="D", id_rol=rol.id_rol)
    u.set_password("ContrasenaDoc1")
    db.session.add(u)
    db.session.commit()

    s = SituacionAprendizaje(
        comunidad_autonoma="Ceuta",
        titulo="El agua", materia=MATERIA, curso=CURSO, id_usuario=u.id_usuario,
        contenido={"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}, {"codigo": "CCL"}],
            "criterios": [{"codigo": "1.1"}],
            "saberes": [{"codigo": "A.3"}],
        }},
    )
    db.session.add(s)
    db.session.commit()
    return s


class TestSeEnlazaLoCorrecto:
    def test_se_escriben_los_enlaces(self, db, sda):
        from app.services.enlaces_curriculares import sincronizar

        sincronizar(sda)

        assert {c.codigo for c in sda.competencias} == {"CE1", "CCL"}
        assert [c.codigo for c in sda.criterios] == ["1.1"]
        assert [s.codigo for s in sda.saberes] == ["A.3"]

    def test_no_se_enlaza_el_codigo_de_otra_materia(self, db, sda):
        """La trampa principal.

        `CE1` existe en Matemáticas A y en Biología. Resolver por código a
        secas engancharía las dos, y la SdA aparecería trabajando una
        competencia de una asignatura que no imparte — con toda la apariencia
        de estar bien.
        """
        from app.services.enlaces_curriculares import sincronizar

        sincronizar(sda)

        materias = {c.materia for c in sda.competencias}
        assert "Biología y Geología" not in materias
        assert len([c for c in sda.competencias if c.codigo == "CE1"]) == 1

    def test_no_se_enlaza_el_criterio_de_otro_curso(self, db, sda):
        """La Orden EFP/754 desarrolla criterios por curso, así que el mismo
        código convive con descripciones distintas dentro de una materia."""
        from app.services.enlaces_curriculares import sincronizar

        sincronizar(sda)

        assert all(CURSO in c.cursos_aplicables for c in sda.criterios)

    def test_las_competencias_clave_sin_materia_sí_se_enlazan(self, db, sda):
        """`Competencia.materia` es NULL en las clave. Un filtro `== materia` a
        secas dejaría fuera precisamente las transversales."""
        from app.services.enlaces_curriculares import sincronizar

        sincronizar(sda)

        assert "CCL" in {c.codigo for c in sda.competencias}


class TestLosCodigosInventados:
    def test_no_se_enlazan_y_se_informan(self, db, sda):
        """El efecto secundario que más valor tiene.

        El prompt le prohíbe al modelo inventarse códigos, pero prohibir no es
        comprobar. Al resolverlos contra la base de datos, los inventados se
        caen solos y quedan contados.
        """
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}, {"codigo": "CE99"}],
            "criterios": [{"codigo": "9.9"}],
            "saberes": [],
        }}
        db.session.commit()

        resumen = sincronizar(sda)

        assert [c.codigo for c in sda.competencias] == ["CE1"]
        assert resumen["huerfanos"]["competencias"] == ["CE99"]
        assert resumen["huerfanos"]["criterios"] == ["9.9"]

    def test_una_sda_entera_de_codigos_inventados_no_revienta(self, db, sda):
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "XX"}], "criterios": [], "saberes": [],
        }}
        db.session.commit()

        resumen = sincronizar(sda)
        assert resumen["competencias"] == 0
        assert sda.competencias == []


class TestElPrefijoQueSeInventaElModelo:
    """El catálogo dice «1» y el modelo escribe «CE1». Tiene que casar igual.

    Se intentó arreglar en el prompt, quitándole el `"CE1"` del ejemplo. **El
    fallo cambió de idioma**: antes lo ponía la versión castellana y no la
    catalana, después al revés. Un arreglo que mueve el fallo de sitio en vez
    de quitarlo demuestra que la causa era variabilidad del modelo, no el
    ejemplo.

    Aquí es determinista. Y no da error cuando falla: la competencia se
    descarta en silencio y el documento sale con una sección de menos.
    """

    def test_ce4_casa_con_el_codigo_4_del_catalogo(self, db, sda):
        """El catálogo de este fichero usa «CE1» y «CE2» de verdad, así que
        para probar la normalización hace falta un código **que no colisione**:
        se añade «4» y se cita «CE4». Con «CE1» el test no probaba nada, porque
        casaba exacto —y así fallaba, con razón—."""
        from app.models import Competencia
        from app.services.enlaces_curriculares import sincronizar

        db.session.add(Competencia(
            codigo="4", tipo=Competencia.ESPECIFICA, materia=sda.materia,
            descripcion="Competencia sin prefijo", descriptores=[],
            cursos_aplicables=[sda.curso], comunidad="ceuta", idioma="es",
        ))
        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE4"}], "criterios": [], "saberes": [],
        }}
        db.session.commit()

        resumen = sincronizar(sda)

        assert [c.codigo for c in sda.competencias] == ["4"]
        assert resumen["huerfanos"].get("competencias", []) == [], (
            "se contó como inventado un código que sí existe con otro formato"
        )

    def test_un_codigo_que_de_verdad_no_existe_sigue_siendo_huerfano(self, db, sda):
        """La tolerancia no puede tragárselo todo: si aceptara cualquier cosa,
        dejaría de detectar los códigos realmente inventados, que es para lo
        que existe `sincronizar`."""
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE404"}], "criterios": [], "saberes": [],
        }}
        db.session.commit()

        resumen = sincronizar(sda)

        assert sda.competencias == []
        assert resumen["huerfanos"]["competencias"] == ["CE404"]

    def test_el_codigo_exacto_gana_al_normalizado(self, db, sda):
        """Si el catálogo tiene «CE1» de verdad —como el de estos tests—, ese
        es el que debe enlazarse, no una variante que también exista."""
        from app.models import Competencia
        from app.services.enlaces_curriculares import sincronizar

        db.session.add(Competencia(
            codigo="1", tipo=Competencia.ESPECIFICA, materia=sda.materia,
            descripcion="La que NO toca", descriptores=[],
            cursos_aplicables=[sda.curso], comunidad="ceuta", idioma="es",
        ))
        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}], "criterios": [], "saberes": [],
        }}
        db.session.commit()

        sincronizar(sda)

        codigos = [c.codigo for c in sda.competencias]
        assert codigos == ["CE1"], (
            "enlazó también la variante: una competencia citada, dos filas"
        )


class TestElDocumentoEnseñaElCodigoDelBoletin:
    """Lo que ve el docente sale del JSONB, no de los enlaces.

    Normalizar solo al buscar arregla la aplicación y no a la persona: la SdA
    quedaba bien enlazada y el PDF seguía enseñando «CE1», que no está en
    ningún decreto.
    """

    def test_el_codigo_citado_se_reescribe_con_el_del_catalogo(self, db, sda):
        from app.models import Competencia
        from app.services.enlaces_curriculares import sincronizar

        db.session.add(Competencia(
            codigo="4", tipo=Competencia.ESPECIFICA, materia=sda.materia,
            descripcion="Sin prefijo", descriptores=[],
            cursos_aplicables=[sda.curso], comunidad="ceuta", idioma="es",
        ))
        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE4", "justificacion": "x"}],
            "criterios": [], "saberes": [],
        }}
        db.session.commit()

        resumen = sincronizar(sda)

        guardado = sda.contenido["conexion_curricular"]["competencias"][0]["codigo"]
        assert guardado == "4", "el PDF seguiría enseñando un código que no existe"
        assert resumen["codigos_normalizados"] == ["CE4"]

    def test_un_codigo_huerfano_no_se_toca(self, db, sda):
        """Es la señal de que el modelo se lo inventó. Normalizarlo lo
        escondería, y `enlazar --simular` dejaría de poder contarlos."""
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE404"}], "criterios": [], "saberes": [],
        }}
        db.session.commit()

        sincronizar(sda)

        assert sda.contenido["conexion_curricular"]["competencias"][0]["codigo"] == "CE404"


class TestJSONBRetorcido:
    """El contenido lo escribe un modelo de lenguaje, no un formulario.

    Ha llegado en formas que el esquema no prometía. Reventar aquí dejaría la
    generación entera en error por un adorno del JSON que la pantalla pinta sin
    inmutarse.
    """

    @pytest.mark.parametrize("seccion", [
        None,
        {},
        {"competencias": None},
        {"competencias": "CE1"},
        {"competencias": [{"sin_codigo": 1}]},
        {"competencias": ["CE1"]},          # cadenas sueltas, sin objeto
        {"competencias": [{"codigo": "  "}]},
        {"competencias": [{"codigo": None}]},
        "esto no es un diccionario",
    ])
    def test_no_lanza_nunca(self, db, sda, seccion):
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": seccion}
        db.session.commit()

        resumen = sincronizar(sda)
        assert "error" not in resumen

    def test_una_lista_de_cadenas_sueltas_sí_se_aprovecha(self, db, sda):
        """Tolerar no es ignorar: si el código se puede leer, se usa."""
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": {"competencias": ["CE1"]}}
        db.session.commit()

        sincronizar(sda)
        assert [c.codigo for c in sda.competencias] == ["CE1"]

    def test_los_codigos_repetidos_no_duplican(self, db, sda):
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}, {"codigo": "CE1"}],
        }}
        db.session.commit()

        sincronizar(sda)
        assert len(sda.competencias) == 1


class TestSeRehaceNoSeAcumula:
    def test_regenerar_la_seccion_borra_los_enlaces_anteriores(self, db, sda):
        """Si se acumulara, la cobertura curricular solo podría crecer: una
        sección regenerada con menos criterios seguiría contando los viejos."""
        from app.services.enlaces_curriculares import sincronizar

        sincronizar(sda)
        assert len(sda.competencias) == 2

        sda.contenido = {"conexion_curricular": {"competencias": [{"codigo": "CE2"}]}}
        db.session.commit()
        sincronizar(sda)

        assert [c.codigo for c in sda.competencias] == ["CE2"]

    def test_vaciar_la_seccion_deja_la_sda_sin_enlaces(self, db, sda):
        from app.services.enlaces_curriculares import sincronizar

        sincronizar(sda)
        sda.contenido = {}
        db.session.commit()
        sincronizar(sda)

        assert sda.competencias == []
        assert sda.criterios == []
        assert sda.saberes == []


class TestNingunEscritorSeOlvida:
    """El guardián de verdad, y el motivo de que exista.

    `contenido` se reasigna en cuatro puntos distintos del código, y no hay
    ningún sitio central por donde pasen todos. Un quinto punto añadido dentro
    de seis meses dejaría los enlaces desincronizados **en silencio**: la
    pantalla seguiría pintando bien, porque pinta del JSONB, y solo se notaría
    al mirar recuentos. Que es exactamente como se descubrió el problema
    original.

    Así que se comprueba de forma estructural. Es un test frágil a propósito:
    prefiere molestar a quien mueva este código antes que dejar pasar el caso.
    """

    RUTA_RELATIVA = ("app/tasks/generacion.py", "app/tasks/operaciones.py",
                     "app/services/situacion_service.py")

    def test_toda_reasignacion_de_contenido_sincroniza_cerca(self):
        import re
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        sin_sincronizar = []

        for relativa in self.RUTA_RELATIVA:
            lineas = (raiz / relativa).read_text(encoding="utf-8").splitlines()
            for i, linea in enumerate(lineas):
                if not re.search(r"^\s*sa\.contenido\s*=\s*contenido\s*(#.*)?$", linea):
                    continue
                # 12 líneas de margen: suficiente para un comentario en medio,
                # corto para que «cerca» siga significando algo.
                #
                # Se quitan los comentarios antes de mirar, y eso lo enseñó un
                # sabotaje: al sustituir la llamada real por `pass`, el test
                # seguía verde porque el comentario que hay encima menciona
                # «sincronizar» y hasta nombra a este test. Se estaba validando
                # a sí mismo. Ahora exige la llamada, con paréntesis.
                vecindad = "\n".join(
                    l.split("#", 1)[0] for l in lineas[i : i + 12]
                )
                if "sincronizar(" not in vecindad:
                    sin_sincronizar.append(f"{relativa}:{i + 1}")

        assert sin_sincronizar == [], (
            "estas líneas reasignan `sa.contenido` sin rehacer los enlaces "
            "curriculares justo después. Si el caso no lo necesita, dilo con un "
            f"comentario que mencione `sincronizar`: {sin_sincronizar}"
        )

    def test_el_detector_encuentra_algo(self):
        """Sin esto, renombrar la variable dejaría el test anterior en verde
        para siempre sin comprobar absolutamente nada."""
        import re
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        total = sum(
            len(re.findall(r"^\s*sa\.contenido\s*=\s*contenido\s*(?:#.*)?$",
                           (raiz / r).read_text(encoding="utf-8"), re.M))
            for r in self.RUTA_RELATIVA
        )
        assert total >= 3, f"el detector solo ve {total} reasignaciones; ¿cambió el patrón?"


class TestODS:
    def test_la_situacion_ya_no_carga_ods(self):
        """No hay relación, y es deliberado: ningún prompt pide ODS, así que
        el JSONB nunca los trae. Era una consulta garantizada a vacío en cada
        carga de cada SdA."""
        from app.models import SituacionAprendizaje

        assert not hasattr(SituacionAprendizaje, "ods")

    def test_la_tabla_y_el_catalogo_siguen_existiendo(self):
        """Se quitó la relación, no los datos: el catálogo de la ONU sigue ahí
        para cuando haya una sección que lo pida."""
        from app.models import ODS, situacion_ods

        assert situacion_ods is not None and ODS is not None


class TestElCaminoRealDeLaGeneracion:
    """Lo estructural no basta, y el mismo sabotaje lo demostró.

    `TestNingunEscritorSeOlvida` mira la forma del código; este mira el efecto.
    Hacen falta los dos: el estructural caza el punto de escritura nuevo que
    nadie enganchó, y este caza que el enganche exista pero no funcione.
    """

    def test_generar_la_seccion_deja_los_enlaces_escritos(self, db, sda, catalogo):
        from app.tasks.generacion import _fusionar_seccion

        sda.competencias = []
        db.session.commit()

        _fusionar_seccion(sda, "conexion_curricular", {
            "competencias": [{"codigo": "CE2"}],
            "criterios": [], "saberes": [],
        })
        db.session.commit()

        assert [c.codigo for c in sda.competencias] == ["CE2"]

    def test_generar_otra_seccion_no_toca_los_enlaces(self, db, sda, catalogo):
        """Sincronizar en cada sección sería tirar tres consultas por cada una
        de las seis que se generan, para rehacer siempre lo mismo."""
        from app.services.enlaces_curriculares import sincronizar
        from app.tasks.generacion import _fusionar_seccion

        sincronizar(sda)
        antes = {c.codigo for c in sda.competencias}

        _fusionar_seccion(sda, "descripcion", {"texto": "otra cosa"})
        db.session.commit()

        assert {c.codigo for c in sda.competencias} == antes


class TestSinCurriculoNoEsInventarse:
    """La distinción que faltaba, y que produjo un diagnóstico falso.

    La primera ejecución real sobre los datos de Jesús dio 17 de 39 SdA
    «citando códigos que el modelo se inventó». Ninguna lo hacía. Las tres
    parejas culpables eran `Matemáticas · 4º ESO` (en 4º hay A y B),
    `Tecnología y Digitalización · 4º ESO` (solo se imparte en 2º y 3º) y
    `Lengua Castellana y Literatura`, que en el catálogo se llama `Lengua`.
    Todas anteriores a que el formulario validara la pareja.

    Con la pareja sin currículo, **ningún** código puede casar, hagan lo que
    hagan el modelo y el docente. Meterlo en el mismo saco que una alucinación
    no solo es impreciso: manda a quien lo lee a buscar donde no está el
    problema, y falsea la medida de cuánto inventan los modelos, que es lo que
    hacía valioso este recuento.
    """

    @pytest.fixture
    def sda_sin_curriculo(self, db, sda):
        """Misma SdA, pero anclada a una pareja que no existe en el catálogo."""
        sda.materia = "Materia Que No Existe"
        db.session.commit()
        return sda

    def test_se_marca_como_sin_curriculo(self, db, sda_sin_curriculo):
        from app.services.enlaces_curriculares import sincronizar

        resumen = sincronizar(sda_sin_curriculo)
        assert resumen["sin_curriculo"] is True

    def test_una_sda_con_curriculo_no_se_marca(self, db, sda):
        from app.services.enlaces_curriculares import sincronizar

        resumen = sincronizar(sda)
        assert resumen["sin_curriculo"] is False

    def test_inventarse_codigos_teniendo_curriculo_sigue_marcandose(self, db, sda):
        """La otra mitad: la señal que sí interesa no se pierde por el camino."""
        from app.services.enlaces_curriculares import sincronizar

        sda.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}, {"codigo": "INVENTADO"}],
        }}
        db.session.commit()

        resumen = sincronizar(sda)
        assert resumen["sin_curriculo"] is False
        assert resumen["huerfanos"]["competencias"] == ["INVENTADO"]

    def test_el_curso_tambien_cuenta_no_solo_la_materia(self, db, sda):
        """`Matemáticas` existe, pero no en 4º ESO. Mirar solo la materia
        habría dado por bueno el currículo de una de las tres parejas que
        provocaron el fallo."""
        from app.services.enlaces_curriculares import sincronizar

        sda.curso = "2º ESO"        # el catálogo de prueba solo cubre 4º
        db.session.commit()

        assert sincronizar(sda)["sin_curriculo"] is True

    def test_el_registro_lo_dice_con_otro_evento(self, db, sda_sin_curriculo, caplog):
        """Dos causas distintas, dos eventos distintos. Si compartieran nombre,
        el recuento de alucinaciones seguiría contaminado aunque el resumen
        estuviera bien."""
        from app.services.enlaces_curriculares import sincronizar

        with caplog.at_level("WARNING"):
            sincronizar(sda_sin_curriculo)

        assert "situacion_sin_curriculo" in caplog.text
        assert "codigos_curriculares_inventados" not in caplog.text
