"""Cargar Bachillerato no puede pisar el currículo de la ESO.

EL FALLO QUE ESTO EVITA, ANTES DE QUE OCURRA
---------------------------------------------
El upsert de competencias casaba por `(comunidad, codigo, materia)`, y esas
tres cosas coinciden entre etapas: «Matemáticas» existe en la ESO y en
Bachillerato, en la misma comunidad, y sus competencias específicas se numeran
`1`, `2`, `3`… en las dos.

Cargar Bachillerato habría **sobrescrito** las de la ESO una por una, sin error
y sin aviso: el seed las habría contado como «actualizadas», que es exactamente
lo que dice cuando todo va bien. Se habría descubierto abriendo una SdA de la
ESO y viendo criterios de Bachillerato.

Este es de los pocos tests del proyecto escritos **antes** del fallo y no
después. Se escribe porque la colisión se vio leyendo la clave del upsert al
planificar 9b, no porque nadie la sufriera.

POR QUÉ NO BASTABA `cursos_aplicables`
---------------------------------------
Los criterios y los saberes sí lo llevan en su clave, así que para ellos «1º
ESO» y «1º Bachillerato» ya eran distintos. Las competencias no, **y es a
propósito**: son comunes a toda la etapa, y el seed fusiona sus cursos en vez
de crear una fila por curso. Meter los cursos en la clave habría roto esa
fusión, que es correcta dentro de una etapa.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.models import Competencia, CriterioEvaluacion, SaberBasico
from app.seeds.seed_curriculo import seed_curriculo


def _json(etapa: str, cursos: list[str], descripcion: str) -> dict:
    """Dos ficheros idénticos salvo la etapa: mismo código, misma materia.

    Es el caso que colisionaba, reducido a lo imprescindible.
    """
    return {
        "materia_oficial": "Matemáticas",
        "materia": "Matemáticas",
        "etapa": etapa,
        "ciclo": "Único",
        "itinerario": None,
        "cursos_aplicables": cursos,
        "comunidad": "ceuta",
        "idioma": "es",
        "competencias_especificas": [
            {"codigo": "1", "descripcion": descripcion, "descriptores": []}
        ],
        "criterios_evaluacion": [
            {"codigo": "1.1", "competencia": "1", "descripcion": f"Criterio {etapa}"}
        ],
        "saberes_basicos": [
            {"codigo": "A", "bloque": "A. Bloque", "titulo": "Bloque",
             "items": [f"Saber {etapa}"]}
        ],
    }


@pytest.fixture()
def cargadas(app, db, tmp_path):
    """Carga la ESO y después Bachillerato, en ese orden."""
    (tmp_path / "mates_eso.json").write_text(
        json.dumps(_json("ESO", ["1º ESO", "2º ESO"], "Competencia de la ESO")),
        encoding="utf-8")
    seed_curriculo(tmp_path)

    (tmp_path / "mates_eso.json").unlink()
    (tmp_path / "mates_bach.json").write_text(
        json.dumps(_json("Bachillerato", ["1º Bachillerato"],
                         "Competencia de Bachillerato")),
        encoding="utf-8")
    seed_curriculo(tmp_path)
    return tmp_path


class TestLaESOSobreviveACargarBachillerato:

    def test_hay_dos_competencias_y_no_una(self, app, db, cargadas):
        """Con la clave vieja habría **una sola fila**, la de Bachillerato,
        porque la segunda carga actualizaba la primera."""
        filas = db.session.scalars(
            select(Competencia).where(Competencia.codigo == "1",
                                      Competencia.materia == "Matemáticas")
        ).all()
        assert {f.etapa for f in filas} == {"ESO", "Bachillerato"}, (
            f"deberían ser dos etapas y son {[f.etapa for f in filas]}"
        )

    def test_la_descripcion_de_la_eso_no_se_ha_tocado(self, app, db, cargadas):
        """Lo que se habría perdido: el texto del decreto de la ESO."""
        eso = db.session.scalar(
            select(Competencia).where(Competencia.codigo == "1",
                                      Competencia.etapa == "ESO")
        )
        assert eso.descripcion == "Competencia de la ESO"

    def test_los_cursos_no_se_han_fusionado_entre_etapas(self, app, db, cargadas):
        """`_union_cursos` fusiona los cursos de una misma competencia, y eso
        es correcto **dentro** de una etapa. Entre etapas produciría una
        Matemáticas que se imparte de 1.º de ESO a 1.º de Bachillerato."""
        eso = db.session.scalar(
            select(Competencia).where(Competencia.etapa == "ESO"))
        assert eso.cursos_aplicables == ["1º ESO", "2º ESO"]

    @pytest.mark.parametrize("modelo", [CriterioEvaluacion, SaberBasico])
    def test_criterios_y_saberes_tampoco_se_pisan(self, app, db, cargadas, modelo):
        """Estos ya estaban a salvo por `cursos_aplicables`, pero ahora llevan
        la etapa explícita y conviene que se quede así: deducirla de la cadena
        del curso es el tipo de dato derivado que acaba divergiendo."""
        filas = db.session.scalars(select(modelo)).all()
        assert {f.etapa for f in filas} == {"ESO", "Bachillerato"}


class TestElBorradoDeSobrantesRespetaLaEtapa:
    """LO QUE ESTE FICHERO NO CUBRÍA, Y COSTÓ EL CURRÍCULO DE LA ESO.

    Los tests de arriba comprueban que cargar Bachillerato no **sobrescriba**
    la ESO. El 02/09/2026 se recargó Bachillerato del País Vasco con
    `--borrar-sobrantes` y la ESO del País Vasco **desapareció**: 723 criterios
    y 1480 saberes borrados, sobreviviendo solo los 28 que alguna SdA citaba.

    El borrado acotaba por comunidad y no por etapa, así que todo lo vasco que
    no viniera en la carpeta de Bachillerato era sobrante. Y la ESO no venía,
    claro: se estaba cargando Bachillerato.

    Sobrescribir y borrar son dos operaciones distintas. Al meter la etapa en
    el esquema se revisó la primera y no la segunda, y estos tests —escritos
    aquel mismo día, y por una vez antes del fallo— dieron una sensación de
    cobertura que no era real. La lección no es «faltaba un test»: es que
    proteger una clave de escritura no protege la de borrado, y hay que
    buscarlas todas cuando se añade una dimensión al modelo.
    """

    @pytest.fixture()
    def con_las_dos_etapas(self, app, db, tmp_path):
        """La ESO cargada y, aparte, la carpeta de Bachillerato sola."""
        eso = tmp_path / "eso"
        eso.mkdir()
        (eso / "mates.json").write_text(
            json.dumps(_json("ESO", ["1º ESO", "2º ESO"], "Competencia ESO")),
            encoding="utf-8")
        seed_curriculo(eso)

        bach = tmp_path / "bach"
        bach.mkdir()
        (bach / "mates.json").write_text(
            json.dumps(_json("Bachillerato", ["1º Bachillerato"],
                             "Competencia Bachillerato")),
            encoding="utf-8")
        return bach

    def test_recargar_bachillerato_no_borra_la_eso(self, app, db,
                                                   con_las_dos_etapas):
        """El fallo, exactamente como ocurrió."""
        seed_curriculo(con_las_dos_etapas, borrar_sobrantes=True)

        criterios = db.session.scalars(
            select(CriterioEvaluacion).where(
                CriterioEvaluacion.etapa == "ESO")
        ).all()
        assert criterios, "la ESO se ha borrado al recargar Bachillerato"

    @pytest.mark.parametrize("modelo", [Competencia, CriterioEvaluacion,
                                        SaberBasico])
    def test_ninguna_de_las_tres_tablas_pierde_la_eso(self, app, db,
                                                      con_las_dos_etapas,
                                                      modelo):
        """Las tres se borran en el mismo bucle, así que las tres fallaban.
        Se comprueban por separado para que el día que alguien toque una sola
        no haya que deducirlo del recuento."""
        seed_curriculo(con_las_dos_etapas, borrar_sobrantes=True)

        filas = db.session.scalars(select(modelo)).all()
        assert {f.etapa for f in filas} == {"ESO", "Bachillerato"}, (
            f"{modelo.__name__}: quedan {[f.etapa for f in filas]}"
        )

    def test_dentro_de_la_etapa_sigue_borrando(self, app, db,
                                               con_las_dos_etapas):
        """El arreglo no puede desactivar el flag: lo que sobra **dentro** del
        par (comunidad, etapa) que se carga tiene que seguir yéndose. Es lo que
        el flag existe para hacer."""
        seed_curriculo(con_las_dos_etapas, borrar_sobrantes=True)

        # Segunda pasada de Bachillerato con la materia renombrada: la anterior
        # queda obsoleta y debe desaparecer.
        datos = _json("Bachillerato", ["1º Bachillerato"], "Otra competencia")
        datos["materia"] = datos["materia_oficial"] = "Matemáticas II"
        (con_las_dos_etapas / "mates.json").write_text(
            json.dumps(datos), encoding="utf-8")
        seed_curriculo(con_las_dos_etapas, borrar_sobrantes=True)

        materias = {
            c.materia for c in db.session.scalars(
                select(Competencia).where(Competencia.etapa == "Bachillerato")
            ).all()
        }
        assert materias == {"Matemáticas II"}, materias


class TestElOrdenDeLosCursos:

    def test_bachillerato_va_despues_de_la_eso(self):
        """La versión anterior solo conocía «Nº ESO» y mandaba lo demás al
        final con un 99: los dos cursos de Bachillerato habrían quedado
        empatados y en orden arbitrario, sin fallar."""
        from app.seeds.seed_curriculo import _union_cursos
        assert _union_cursos(
            ["2º Bachillerato", "1º ESO"], ["1º Bachillerato", "3º ESO"]
        ) == ["1º ESO", "3º ESO", "1º Bachillerato", "2º Bachillerato"]

    def test_lo_desconocido_va_al_final_pero_en_orden_estable(self):
        """Un orden que dependa del recorrido de un `set` produce diferencias
        entre cargas que parecen cambios de datos y no lo son."""
        from app.seeds.seed_curriculo import _union_cursos
        assert _union_cursos(["Zzz", "1º ESO"], ["Aaa"]) == \
            ["1º ESO", "Aaa", "Zzz"]
