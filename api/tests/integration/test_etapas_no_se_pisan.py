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
