"""La etapa de una SdA sale del catálogo, no de quien la crea.

POR QUÉ NO SE ACEPTA DEL CLIENTE
---------------------------------
Es el mismo trato que `comunidad_autonoma`, que se deriva de la provincia y se
ignora si viene en la petición. Aceptarla permitiría guardar una SdA que dice
ser de la ESO con el curso «2º Bachillerato»: dos campos plausibles por
separado, incoherentes juntos, y sin forma de detectarlo después.

POR QUÉ NO SE DEDUCE DE LA CADENA DEL CURSO
--------------------------------------------
Porque «1º Bachillerato» lleva la etapa dentro **por costumbre, no por
contrato**. Basta con que una comunidad escriba «1.º» con punto, o que entre
un ciclo de FP, para que la deducción empiece a mentir sin fallar. El catálogo
tiene la etapa en una columna desde `d1a7b4e62c95`: preguntarle es leer un
dato en vez de interpretarlo.

LO QUE ESTOS TESTS VIGILAN DE VERDAD
-------------------------------------
Que los **tres** caminos que pueden cambiar el par materia/curso dejen la etapa
coherente: crear, actualizar y `reasignar_curriculo`. Si solo uno lo hiciera,
el fallo dependería de por dónde se hubiera editado la SdA, que es la clase de
diferencia que nadie reproduce cuando la reporta.
"""
from __future__ import annotations

import pytest

# `db` llega siempre como fixture, nunca importado: importarlo aquí crearía un
# nombre de módulo que las funciones sombrean, y en la que se olvidara el
# parámetro se usaría la sesión de fuera de la transacción del test.
from app.models import Competencia, CriterioEvaluacion, SaberBasico
from app.services import situacion_service as svc


def _tramo(db, *, etapa, cursos, materia="Matematika"):
    """Un currículo mínimo pero **completo** de una materia en una etapa.

    Las tres tablas, y el criterio colgando de su competencia: `id_competencia`
    es NOT NULL, así que hay un `flush` en medio para que la competencia tenga
    identificador antes de referenciarla. Insertarlas de golpe con `add_all`
    fallaba —lo hizo— porque el criterio salía con la clave ajena a nulo.
    """
    comun = dict(comunidad="pais-vasco", etapa=etapa, materia=materia,
                 idioma="eu", cursos_aplicables=cursos)

    ce = Competencia(codigo="1", descripcion="Konpetentzia",
                     tipo=Competencia.ESPECIFICA, **comun)
    db.session.add(ce)
    db.session.flush()          # para tener `ce.id_competencia`

    db.session.add_all([
        CriterioEvaluacion(codigo="1.1", descripcion="Irizpidea",
                           id_competencia=ce.id_competencia, **comun),
        SaberBasico(codigo="A.1", descripcion="Jakintza", bloque="A", **comun),
    ])
    return ce


@pytest.fixture()
def usuario(db):
    """Docente de Bizkaia: la provincia decide la comunidad, y la comunidad
    el catálogo contra el que se resuelve la etapa."""
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="etapa@ies.eus", nombre="Etapa", id_rol=rol.id_rol,
                provincia="bizkaia", comunidad_autonoma="pais-vasco")
    u.set_password("ContrasenaBaja1")
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def catalogo_vasco(db):
    """«Matematika» en las dos etapas, que es el caso real del País Vasco.

    El mismo nombre de materia con currículos distintos es justo lo que hace
    que la etapa no se pueda deducir de la materia tampoco.
    """
    _tramo(db, etapa="ESO", cursos=["1º ESO", "2º ESO"])
    _tramo(db, etapa="Bachillerato", cursos=["1º Bachillerato"])
    db.session.commit()


def _datos(curso="1º ESO", materia="Matematika"):
    return {"titulo": "Proba bat", "curso": curso, "materia": materia,
            "provincia": "bizkaia"}


class TestAlCrear:

    def test_la_etapa_sale_del_catalogo(self, db, usuario, catalogo_vasco):
        sa = svc.crear(usuario, _datos(curso="1º Bachillerato"))

        assert sa.etapa == "Bachillerato"

    def test_la_misma_materia_en_otro_curso_da_otra_etapa(
        self, db, usuario, catalogo_vasco
    ):
        """Lo que prueba que se lee el catálogo y no el nombre de la materia:
        «Matematika» es la misma cadena en los dos casos."""
        assert svc.crear(usuario, _datos(curso="1º ESO")).etapa == "ESO"

    def test_la_que_mande_el_cliente_se_ignora(
        self, db, usuario, catalogo_vasco
    ):
        """Mandar «ESO» con un curso de Bachillerato no puede colar."""
        sa = svc.crear(usuario, {**_datos(curso="1º Bachillerato"),
                                 "etapa": "ESO"})

        assert sa.etapa == "Bachillerato"

    def test_sin_curriculo_no_falla_y_se_queda_en_eso(self, db, usuario):
        """Crear un borrador nunca ha exigido currículo —lo que lo exige es
        *generar*—, así que esto no puede romperse por una materia que el
        catálogo no conozca."""
        sa = svc.crear(usuario, _datos(materia="Lo Que Sea"))

        assert sa.etapa == "ESO"


class TestConstruirElModeloAMano:
    """Sin pasar por el servicio, que es lo que hacen ochenta ficheros de test.

    EL FALLO QUE ESTO FIJA
    -----------------------
    La columna nació NOT NULL y **sin default**, razonando que «una SdA sin
    etapa debe fallar». Falló: doscientos tests reventaron en el INSERT, y no
    porque estuvieran mal, sino porque ninguno tenía por qué conocer un campo
    añadido esa misma tarde.

    Una columna obligatoria que no sabe rellenarse sola no protege el dato:
    obliga a repetirlo en cada sitio que inserta, que es exactamente donde se
    cuelan las incoherencias que la columna venía a evitar.
    """

    def test_se_puede_insertar_sin_indicar_la_etapa(self, db, usuario):
        from app.models import SituacionAprendizaje

        sa = SituacionAprendizaje(titulo="A mano", curso="3º ESO",
                                  materia="Matematika",
                                  id_usuario=usuario.id_usuario, contenido={})
        db.session.add(sa)
        db.session.commit()

        assert sa.etapa == "ESO"

    def test_y_la_deduce_del_curso(self, db, usuario):
        """La misma deducción que hace el backfill de la migración."""
        from app.models import SituacionAprendizaje

        sa = SituacionAprendizaje(titulo="A mano", curso="1º Bachillerato",
                                  materia="Matematika",
                                  id_usuario=usuario.id_usuario, contenido={})
        db.session.add(sa)
        db.session.commit()

        assert sa.etapa == "Bachillerato"

    def test_lo_explicito_manda_sobre_el_default(self, db, usuario):
        """Porque el servicio la asigna antes del flush, y su valor —leído del
        catálogo— tiene que ganarle a la deducción."""
        from app.models import SituacionAprendizaje

        sa = SituacionAprendizaje(titulo="A mano", curso="3º ESO",
                                  materia="Matematika", etapa="Bachillerato",
                                  id_usuario=usuario.id_usuario, contenido={})
        db.session.add(sa)
        db.session.commit()

        assert sa.etapa == "Bachillerato"


class TestAlEditar:

    def test_cambiar_de_curso_recalcula_la_etapa(
        self, db, usuario, catalogo_vasco
    ):
        """Sin esto, mover una SdA de «1º ESO» a «1º Bachillerato» la dejaría
        archivada como de la ESO y el filtro la enseñaría donde no toca."""
        sa = svc.crear(usuario, _datos(curso="1º ESO"))
        assert sa.etapa == "ESO"

        svc.actualizar(sa.id_situacion, usuario, {"curso": "1º Bachillerato"})

        assert sa.etapa == "Bachillerato"

    def test_reasignar_curriculo_tambien(self, db, usuario, catalogo_vasco):
        """El otro camino que cambia materia y curso. Se llama desde la
        consola, sin sesión, y es fácil olvidarlo porque no pasa por el API."""
        sa = svc.crear(usuario, _datos(curso="1º ESO"))

        svc.reasignar_curriculo(sa, materia="Matematika",
                                curso="1º Bachillerato", motivo="prueba")

        assert sa.etapa == "Bachillerato"

    def test_tocar_otra_cosa_no_la_toca(self, db, usuario, catalogo_vasco):
        """Recalcular en cada guardado sería gratis pero engañoso: dejaría de
        verse cuándo cambia de verdad."""
        sa = svc.crear(usuario, _datos(curso="1º Bachillerato"))

        svc.actualizar(sa.id_situacion, usuario, {"titulo": "Beste izenburu"})

        assert sa.etapa == "Bachillerato"


class TestAlDuplicar:

    def test_la_copia_hereda_la_etapa(self, db, usuario, catalogo_vasco):
        """Se copia en vez de recalcularse: si el currículo cambió desde que se
        creó el original, recalcular haría que copia y original dijeran etapas
        distintas sin que nadie las haya movido."""
        sa = svc.crear(usuario, _datos(curso="1º Bachillerato"))

        copia = svc.duplicar(sa.id_situacion, usuario)

        assert copia.etapa == "Bachillerato"


class TestElFiltro:

    def test_lista_solo_las_de_esa_etapa(self, db, usuario, catalogo_vasco):
        svc.crear(usuario, _datos(curso="1º ESO"))
        svc.crear(usuario, _datos(curso="1º Bachillerato"))

        solo_bach = svc.listar(usuario, etapa="Bachillerato")

        assert [s.etapa for s in solo_bach] == ["Bachillerato"]

    def test_el_total_cuenta_lo_mismo_que_se_ve(
        self, db, usuario, catalogo_vasco
    ):
        """`listar` y `contar` comparten `_filtros_listado` para no divergir.
        Si una aplicara la etapa y la otra no, el paginador prometería páginas
        vacías y nadie lo notaría hasta contarlas."""
        svc.crear(usuario, _datos(curso="1º ESO"))
        svc.crear(usuario, _datos(curso="1º Bachillerato"))

        assert svc.contar(usuario, etapa="Bachillerato") == 1
        assert len(svc.listar(usuario, etapa="Bachillerato")) == 1
