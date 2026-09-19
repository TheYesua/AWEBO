"""Ceuta y Melilla comparten currículo, y la aplicación tiene que saberlo.

EL FALLO QUE ESTO EVITA
------------------------
`provincias.py` mandaba Melilla a una comunidad `melilla` para la que no había
—ni podía haber— currículo: lo que está cargado bajo `ceuta` son las Órdenes
EFP/754 (ESO) y EFP/755 (Bachillerato), que se titulan las dos «de Ceuta y
Melilla» y aplican a las dos ciudades por igual. Un docente de Melilla elegía su
ciudad en el desplegable y se quedaba con el catálogo vacío, sin que nada se lo
explicara.

Estuvo así desde el principio y no lo destapó ningún test, porque ninguno
preguntaba por Melilla: se vio el 19/09/2026 leyendo el PDF de una SdA recién
generada, que decía «Currículo aplicado: Ceuta (Orden EFP/755/2022)» cuando esa
Orden es de las dos ciudades.

No hizo falta migrar nada: `geografia.comunidad_de` deriva la comunidad de la
provincia **al leer**.
"""
from __future__ import annotations

import pytest

from app.curriculo import comunidades, provincias


class TestMelillaLlegaAlCurriculoQueLeCorresponde:

    @pytest.mark.parametrize("provincia", ["ceuta", "melilla"])
    def test_las_dos_ciudades_van_a_la_misma_comunidad(self, provincia):
        assert provincias.comunidad_de(provincia) == "ceuta"

    def test_el_nombre_que_se_muestra_nombra_a_las_dos(self):
        """Es lo que acaba en el PDF, detrás de «Currículo aplicado:». Decir
        solo «Ceuta» atribuía a una ciudad una norma de las dos."""
        assert comunidades.nombre("ceuta") == "Ceuta y Melilla"

    def test_ya_no_hay_un_codigo_melilla_sin_curriculo(self):
        assert "melilla" not in comunidades.COMUNIDADES

    @pytest.mark.parametrize("guardado", [
        "Melilla", "melilla", "MELILLA", "  Melilla  ",
        "Ceuta", "ceuta", "Ceuta y Melilla",
    ])
    def test_las_filas_antiguas_siguen_resolviendo(self, guardado):
        """`comunidad_autonoma` es texto libre y hay filas anteriores a que
        existiera la provincia. Sin alias, las que dicen «Melilla» resolverían
        a None —`normalizar` no inventa— y se quedarían sin currículo igual que
        antes; el arreglo solo habría servido para las cuentas nuevas."""
        assert comunidades.normalizar(guardado) == "ceuta"


class TestLaTablaDeProvinciasEsCoherente:
    """Una guarda estructural, no de dominio: que los códigos casen.

    No comprueba que una comunidad tenga currículo —trece no lo tienen todavía
    y es lo esperado—, sino que ninguna provincia apunte a un código que no
    existe. Es lo que convertiría una errata en un desplegable silenciosamente
    vacío.
    """

    def test_toda_provincia_apunta_a_una_comunidad_que_existe(self):
        huerfanas = {
            codigo: comunidad
            for codigo, (_, comunidad) in provincias.PROVINCIAS.items()
            if comunidad not in comunidades.COMUNIDADES
        }

        assert huerfanas == {}

    def test_toda_comunidad_es_alcanzable_desde_alguna_provincia(self):
        """Al revés: una comunidad a la que no llega ninguna provincia no se
        puede elegir, así que o sobra o falta la provincia que la nombra."""
        alcanzadas = {c for _, c in provincias.PROVINCIAS.values()}
        sueltas = set(comunidades.COMUNIDADES) - alcanzadas

        assert sueltas == set()
