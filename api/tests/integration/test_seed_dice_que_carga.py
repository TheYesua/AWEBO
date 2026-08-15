"""El seed de currículo tiene que decir en el log lo que carga de verdad.

POR QUÉ EXISTE ESTE FICHERO
----------------------------
Porque cargando Andalucía el 15/08/2026 el log dijo, literalmente:

    Cargando currículo de ceuta en es desde /curriculo/salida_andalucia

Los datos entraron bien —737 criterios y 957 saberes de Andalucía, y la web lo
confirmó—, así que **no era un fallo de carga: era un fallo del log**. El
mensaje se emitía antes de abrir ningún fichero, de modo que solo podía enseñar
el valor por defecto de la opción, mientras que quien manda es la `comunidad`
que trae dentro cada JSON.

Y ese es justo el tipo de defecto que conviene fijar con un test. Un log que
miente no falla nunca: se queda ahí, y el día que alguien cargue de verdad en
la comunidad equivocada, el mensaje dirá lo mismo que decía cuando todo iba
bien. La consecuencia sería sobrescribir el currículo de Ceuta con el de otra
comunidad y descubrirlo al generar una SdA contra la normativa que no toca.

Lo que se prueba es la relación entre las dos cosas: que el mensaje del
principio **no afirma** una comunidad como si fuera un hecho, y que al terminar
se dice cuál se cargó realmente.
"""
from __future__ import annotations

import json
import logging

import pytest

from app.seeds.seed_curriculo import seed_curriculo


def _json_de(comunidad: str, materia: str) -> dict:
    """Un fichero mínimo pero completo, con su comunidad dentro."""
    return {
        "materia_oficial": materia,
        "materia": materia,
        "etapa": "ESO",
        "ciclo": "1º ESO",
        "itinerario": None,
        "cursos_aplicables": ["1º ESO"],
        "comunidad": comunidad,
        "idioma": "es",
        "competencias_especificas": [
            {"codigo": "1", "descripcion": "Interpretar y transmitir.", "descriptores": ["CD2"]},
        ],
        "criterios_evaluacion": [
            {"codigo": "1.1", "competencia": "1", "descripcion": "Analizar conceptos."},
        ],
        "saberes_basicos": [
            {
                "codigo": "A",
                "bloque": "A. Proyecto científico",
                "titulo": "Proyecto científico",
                "items": ["Formulación de hipótesis."],
                "codigos_items": ["BYG.1.A.1"],
            },
        ],
    }


@pytest.fixture()
def carpeta(tmp_path):
    (tmp_path / "biologia__1.json").write_text(
        json.dumps(_json_de("andalucia", "Biología y Geología"), ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


class TestElLogNoContradiceALosDatos:
    def test_no_anuncia_ceuta_al_cargar_andalucia(self, app, db, carpeta, caplog):
        """EL FALLO, tal cual se vio. El defecto a lo largo del proyecto ha
        sido siempre el mismo: algo se afirma antes de saberlo."""
        with caplog.at_level(logging.INFO, logger="seeds.curriculo"):
            seed_curriculo(carpeta)

        arranque = next(
            r.getMessage() for r in caplog.records
            if r.getMessage().startswith("Cargando currículo")
        )

        assert "de ceuta" not in arranque, arranque

    def test_al_terminar_dice_la_comunidad_que_cargo(self, app, db, carpeta, caplog):
        """Al final ya se sabe, porque los ficheros están leídos. Es el dato
        con el que se comprueba que la carga fue donde tenía que ir."""
        with caplog.at_level(logging.INFO, logger="seeds.curriculo"):
            seed_curriculo(carpeta)

        final = next(
            r.getMessage() for r in caplog.records
            if r.getMessage().startswith("Cargado currículo")
        )

        assert "andalucia" in final, final

    def test_el_fichero_manda_sobre_la_opcion(self, app, db, carpeta, caplog):
        """Aunque se pida Ceuta por la orden. Es el comportamiento que ya
        estaba documentado en el comando; aquí se comprueba que el log lo
        cuenta igual que la base de datos."""
        with caplog.at_level(logging.INFO, logger="seeds.curriculo"):
            seed_curriculo(carpeta, comunidad="ceuta", idioma="es")

        final = next(
            r.getMessage() for r in caplog.records
            if r.getMessage().startswith("Cargado currículo")
        )

        assert "andalucia" in final and "ceuta" not in final, final


class TestLosContadoresSiguenSaliendo:
    def test_la_comunidad_no_se_cuela_en_los_totales(self, app, db, carpeta):
        """`comunidad` viaja en el mismo diccionario que los contadores, así
        que si el sumador no la aparta revienta al hacer `int + str`. Con un
        solo fichero no se vería: hace falta que el bucle sume dos veces."""
        total = seed_curriculo(carpeta)

        assert total["ficheros"] == 1
        assert total["cr_nuevos"] == 1
        assert total["sb_nuevos"] == 1
        assert "comunidad" not in total

    def test_repetirlo_no_duplica(self, app, db, carpeta):
        """El seed es idempotente, y esta es la ejecución que ejercita el
        camino del sumador dos veces."""
        seed_curriculo(carpeta)
        segunda = seed_curriculo(carpeta)

        assert segunda["cr_nuevos"] == 0
        assert segunda["sb_nuevos"] == 0
        assert segunda["ce_nuevas"] == 0


class TestElCodigoOficialDelSaber:
    def test_se_guarda_el_del_boletin_y_no_el_contador(self, app, db, carpeta):
        """La razón de ser del cambio: `BYG.1.A.1` es citable y `A.1` no.
        Además `A.1` cambia de valor si mañana se lee un saber más, y las SdA
        ya generadas pasarían a citar otro saber sin que nada avise."""
        from app.models import SaberBasico

        seed_curriculo(carpeta)

        codigos = [s.codigo for s in db.session.query(SaberBasico).all()]

        assert "BYG.1.A.1" in codigos
        assert "A.1" not in codigos
