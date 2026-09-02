"""Un código de criterio repetido en el decreto no puede perder texto.

EL FALLO
---------
El Decreto 76/2023 publica **dos criterios distintos con el código `8.3`** en
Euskara eta Literatura eta Gaztelania eta Literatura. Son dos textos
diferentes: uno habla de la literatura vasca de lectura guiada y el otro de la
del siglo XIX.

El upsert buscaba por `(comunidad, etapa, codigo, materia, cursos)`, así que el
segundo `8.3` **encontraba la fila del primero y la actualizaba**: entraba su
texto encima del anterior y la base de datos acababa con un criterio donde el
JSON tenía dos. Sin error, sin aviso y sin nada roto: la carga terminaba bien.

CÓMO SE VIO, QUE ES LO QUE MERECE LA PENA CONTAR
-------------------------------------------------
Por un descuadre de seis en un recuento. El seed imprimió `cr_nuevos=1138` y
los JSON tenían 1144 criterios. Cinco de esos seis eran erratas de numeración
que el extractor ya corrige —ver `_corregir_numeracion`—; el sexto es este, y
no se puede corregir porque el decreto no dice cuál de los dos `8.3` está mal.

De no haber imprimido el cargador ese número, la pérdida habría sido invisible.

POR QUÉ NO SE RENUMERA
-----------------------
Porque `8.4` no aparece en el decreto. Un docente que cite «8.4» en su
programación estaría citando un código que nos hemos inventado. Se prefiere un
código duplicado —que es lo que publica el boletín— a uno limpio y falso.
"""
from __future__ import annotations

import json

import pytest

from app.models import CriterioEvaluacion
from app.seeds.seed_curriculo import seed_curriculo


def _json_con_codigo_repetido() -> dict:
    return {
        "materia_oficial": "EUSKARA ETA LITERATURA",
        "materia": "Euskara eta Literatura",
        "etapa": "Bachillerato",
        "ciclo": "Único",
        "itinerario": None,
        "cursos_aplicables": ["1º Bachillerato", "2º Bachillerato"],
        "comunidad": "pais-vasco",
        "idioma": "eu",
        "competencias_especificas": [
            {"codigo": "8", "descripcion": "Obren interpretazioa.",
             "descriptores": []},
        ],
        "criterios_evaluacion": [
            {"codigo": "8.3", "competencia": "8",
             "descripcion": "Ikerketa-proiektuak, euskal literaturari lotuta."},
            {"codigo": "8.3", "competencia": "8",
             "descripcion": "Ikerketa-proiektuak, XIX. mendeko literaturari "
                            "lotuta."},
        ],
        "saberes_basicos": [
            {"codigo": "A", "bloque": "A. Literatura", "titulo": "Literatura",
             "items": ["Obren irakurketa."], "codigos_items": []},
        ],
    }


@pytest.fixture()
def carpeta(tmp_path):
    (tmp_path / "euskara__1_2.json").write_text(
        json.dumps(_json_con_codigo_repetido(), ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


class TestLosDosCriteriosEntran:

    def test_se_crean_dos_filas_y_no_una(self, app, db, carpeta):
        seed_curriculo(carpeta)

        filas = db.session.query(CriterioEvaluacion).filter_by(
            comunidad="pais-vasco", etapa="Bachillerato", codigo="8.3",
            materia="Euskara eta Literatura",
        ).all()

        assert len(filas) == 2, (
            f"{len(filas)} fila(s): el segundo criterio ha pisado al primero"
        )

    def test_los_dos_textos_estan(self, app, db, carpeta):
        """Que haya dos filas no basta: lo que importa es que ninguno de los
        dos textos se haya perdido por el camino."""
        seed_curriculo(carpeta)

        textos = {
            c.descripcion for c in db.session.query(CriterioEvaluacion)
            .filter_by(comunidad="pais-vasco", codigo="8.3").all()
        }

        assert any("euskal literaturari" in t for t in textos), textos
        assert any("XIX. mendeko" in t for t in textos), textos

    def test_recargar_no_multiplica_las_filas(self, app, db, carpeta):
        """El riesgo de la solución: si «lo ya visto» se recordara entre
        cargas, cada pasada crearía dos filas nuevas y la tabla crecería sin
        fin. El registro es **por carga**, así que la segunda pasada actualiza
        las dos que ya están."""
        seed_curriculo(carpeta)
        seed_curriculo(carpeta)

        filas = db.session.query(CriterioEvaluacion).filter_by(
            comunidad="pais-vasco", etapa="Bachillerato", codigo="8.3",
        ).all()

        assert len(filas) == 2, f"{len(filas)} filas tras recargar"
