"""Tests del extractor de los PDF por materia de la XTEC (currículo catalán).

No tocan base de datos ni Flask. Se ejecutan contra los **PDF reales**, que no
están en el repositorio por tamaño: si no están, la clase se salta entera.

DÓNDE ESTÁ EL RIESGO EN ESTE EXTRACTOR
---------------------------------------
No en que falle, sino en que **acierte a medias sin decirlo**. Los tres fallos
que se cometieron escribiéndolo tenían el mismo síntoma —ninguno—:

1. Los criterios de la segunda columna se iban todos a la primera, porque la
   cabecera está centrada y el texto alineado a la izquierda. Resultado: 4.º de
   ESO con cero criterios y 1.º con el doble.
2. `1.1 ` casaba y `1.1. ` no, porque unos PDF ponen punto tras el código y
   otros no. Resultado: una materia entera con cero criterios.
3. Los umbrales de sangrado de los saberes estaban copiados de Matemàtiques.
   Resultado: cero saberes en la mitad de las materias.

Ninguno de los tres lanza una excepción. Por eso los tests de aquí comprueban
**cantidades y reparto**, no que la función devuelva algo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.curriculo.extractor_xtec import (
    _clave,
    _limpiar_titulo,
    cursos_del_articulado,
    extraer,
    titulos_de,
    leer_lineas,
)


_FUENTES = Path(__file__).resolve().parents[2].parent / "curriculo" / "fuentes" / "cataluna"
XTEC = _FUENTES / "xtec"
ARTICULADO = _FUENTES / "decret_175_2022.xml"

MATES = XTEC / "Matematiques.pdf"
LENGUAS = XTEC / "Aranes.Castella.-Catala.pdf"
CULTURA = XTEC / "Cultura-Cientifica.pdf"


class TestLimpiezaDeTitulos:
    """Sin PDF: la coletilla del curso no es parte del nombre de la materia."""

    @pytest.mark.parametrize("crudo, limpio", [
        ("Cultura Científica (matèria optativa de quart d’ESO)", "Cultura Científica"),
        ("Educació Plàstica, Visual i Audiovisual de primer a tercer",
         "Educació Plàstica, Visual i Audiovisual"),
        ("Expressió Artística de quart", "Expressió Artística"),
        ("Matemàtiques", "Matemàtiques"),
    ])
    def test_se_queda_solo_el_nombre(self, crudo, limpio):
        """Si la coletilla se cuela, la materia guardada no coincide con la que
        lista el articulado y el desplegable ofrece dos entradas para lo mismo."""
        assert _limpiar_titulo(crudo) == limpio

    def test_la_clave_ignora_tildes_y_signos(self):
        """El PDF y el articulado escriben los mismos nombres con apóstrofos
        distintos. Comparar en crudo dejaría materias sin emparejar, y sin
        cursos, sin decir por qué."""
        assert _clave("Llatí: Llengua i Cultura") == _clave("Llati Llengua i Cultura")
        assert _clave("Aranès i Literatura a l’Aran") == _clave("Aranes i Literatura a l'Aran")


@pytest.mark.skipif(not ARTICULADO.exists(), reason=f"no está {ARTICULADO}")
class TestCursosDelArticulado:
    """Los cursos que el PDF no dice salen del decreto."""

    def test_las_optativas_de_cuarto_salen_como_de_cuarto(self):
        """Sin esto, Filosofia y Llatí se quedan sin cursos, y una materia sin
        cursos acaba ofreciéndose en los cuatro: Llatí en 1.º de ESO, que es el
        fallo del 03/08 con otro decreto."""
        cursos = {_clave(k): v for k, v in cursos_del_articulado(ARTICULADO).items()}

        assert cursos[_clave("Filosofia")] == ["4º ESO"]
        assert cursos[_clave("Llatí: Llengua i Cultura")] == ["4º ESO"]

    def test_las_comunes_de_primero_a_tercero(self):
        cursos = {_clave(k): v for k, v in cursos_del_articulado(ARTICULADO).items()}

        assert cursos[_clave("Tecnologia i Digitalització")] == ["1º ESO", "2º ESO", "3º ESO"]

    def test_musica_esta_en_los_cuatro_cursos(self):
        """Aparece en los dos artículos, así que acumula. Si se sobrescribiera
        en vez de acumular, se quedaría solo con el último."""
        cursos = {_clave(k): v for k, v in cursos_del_articulado(ARTICULADO).items()}

        assert cursos[_clave("Música")] == ["1º ESO", "2º ESO", "3º ESO", "4º ESO"]

    def test_las_agrupaciones_no_son_materias(self):
        """«Biologia i Geologia i/o Física i Química» es una elección entre dos
        materias que ya están listadas por separado. Guardarla crearía una
        materia fantasma en el desplegable."""
        nombres = cursos_del_articulado(ARTICULADO)

        assert not any(" i/o " in n for n in nombres)


@pytest.mark.skipif(not MATES.exists(), reason=f"no está {MATES}")
class TestUnaMateriaConTablaDeDosColumnas:
    """Matemàtiques: 9 competencias y criterios repartidos en 1r-3r / 4t."""

    @pytest.fixture(scope="class")
    def bloques(self):
        return extraer(MATES)

    def test_salen_dos_bloques_uno_por_grupo_de_cursos(self, bloques):
        cursos = sorted(tuple(b.cursos_aplicables) for b in bloques)

        assert cursos == [("1º ESO", "2º ESO", "3º ESO"), ("4º ESO",)]

    def test_las_dos_columnas_tienen_criterios(self, bloques):
        """EL TEST QUE IMPORTA. La cabecera de columna está centrada y el texto
        alineado a la izquierda: comparando la x del texto con la de su
        cabecera, toda la segunda columna se iba a la primera. 4.º se quedaba
        con cero criterios y nadie se enteraba."""
        por_cursos = {tuple(b.cursos_aplicables): len(b.criterios) for b in bloques}

        assert all(n > 0 for n in por_cursos.values()), por_cursos
        # Y no una desproporción que delate que se mezclaron.
        menor, mayor = sorted(por_cursos.values())
        assert mayor <= menor * 2, f"reparto sospechoso: {por_cursos}"

    def test_las_competencias_son_las_mismas_en_los_dos_bloques(self, bloques):
        """Las competencias específicas son de la materia, no del curso: lo que
        cambia entre 1.º-3.º y 4.º son los criterios."""
        codigos = {tuple(c.codigo for c in b.competencias) for b in bloques}

        assert len(codigos) == 1
        assert len(next(iter(codigos))) == 9

    def test_los_criterios_llevan_su_competencia_y_su_codigo(self, bloques):
        crit = bloques[0].criterios[0]

        assert crit.codigo.startswith("1.")
        assert crit.competencia == "1"
        assert len(crit.descripcion) > 20

    def test_el_texto_se_guarda_en_catalan_y_entero(self, bloques):
        """Los criterios vienen partidos en varias líneas por el ancho de la
        celda. Si no se vuelven a juntar, se guarda un trozo de frase."""
        textos = " ".join(c.descripcion for c in bloques[0].criterios)

        assert "matemàtic" in textos.lower()
        assert not any(c.descripcion.endswith(" i") for c in bloques[0].criterios)

    def test_hay_saberes_con_sus_bloques(self, bloques):
        """Los umbrales de sangrado se calculan del documento, no se escriben:
        copiados de un PDF, daban cero saberes en la mitad de las materias."""
        saberes = bloques[0].saberes

        assert len(saberes) >= 5
        assert all(b.items for b in saberes)
        assert any("·" in b.titulo for b in saberes), "no se anidó bloque y subbloque"


@pytest.mark.skipif(not LENGUAS.exists(), reason=f"no está {LENGUAS}")
class TestTresMateriasEnUnSoloPDF:
    """El bloque lingüístico: tres materias con un currículo compartido."""

    def test_se_reconocen_las_tres(self):
        """Aranès, Llengua Castellana y Llengua Catalana comparten currículo y
        van en un solo fichero. Quedarse con el primer título habría dejado dos
        materias sin currículo, y sin dar ningún error: simplemente no saldrían
        en el desplegable."""
        titulos = titulos_de(leer_lineas(LENGUAS))

        assert "Aranès i Literatura a l’Aran" in titulos
        assert "Llengua Castellana i Literatura" in titulos
        assert "Llengua Catalana i Literatura" in titulos

    def test_cada_una_recibe_el_curriculo_completo(self):
        bloques = extraer(LENGUAS)
        materias = {b.materia_oficial for b in bloques}

        assert len(materias) == 3
        for m in materias:
            suyos = [b for b in bloques if b.materia_oficial == m]
            assert len(suyos) == 2, f"{m} no tiene los dos grupos de cursos"
            assert all(b.criterios for b in suyos), f"{m} sin criterios"


@pytest.mark.skipif(not CULTURA.exists(), reason=f"no está {CULTURA}")
class TestUnaMateriaSinTabla:
    """Cultura Científica: una sola columna y el código con punto final."""

    def test_el_codigo_con_punto_tambien_casa(self):
        """Matemàtiques escribe «1.1 » y Cultura Científica «1.1. ». Sin el
        punto opcional en el patrón, esta materia salía con cero criterios y no
        daba ningún error."""
        bloques = extraer(CULTURA)

        assert bloques
        assert sum(len(b.criterios) for b in bloques) > 0


@pytest.mark.skipif(not XTEC.exists() or not ARTICULADO.exists(), reason="faltan fuentes")
class TestElConjuntoCompleto:
    """La comprobación de conjunto: que no se cuele una materia rota."""

    @pytest.fixture(scope="class")
    def todo(self):
        from app.curriculo.extractor_xtec import _clave as clave

        cursos = {clave(k): v for k, v in cursos_del_articulado(ARTICULADO).items()}
        bloques = []
        for pdf in sorted(XTEC.glob("*.pdf")):
            for mc in extraer(pdf):
                if not mc.cursos_aplicables:
                    mc.cursos_aplicables = list(cursos.get(clave(mc.materia_oficial), []))
                bloques.append(mc)
        return bloques

    def test_todas_las_materias_tienen_criterios(self, todo):
        """La que más importa de todo el fichero: una materia sin criterios se
        carga en la base de datos igual de bien que una completa, sale en el
        desplegable, y la SdA se genera sin currículo que la ancle."""
        sin = sorted({b.materia_oficial for b in todo if not b.criterios})

        assert sin == [], f"materias sin criterios: {sin}"

    def test_todas_tienen_competencias(self, todo):
        sin = sorted({b.materia_oficial for b in todo if not b.competencias})

        assert sin == []

    def test_casi_todas_tienen_cursos(self, todo):
        """«Robòtica i Programació» no aparece en los artículos 9 ni 10: es una
        optativa que autoriza el centro, y la norma no le fija curso. Es el
        mismo caso que las tres optativas de Ceuta.

        Se fija la lista **entera** a propósito: si mañana otra materia se queda
        sin cursos, este test lo dice en vez de dejarlo pasar por ser «pocas».
        """
        sin = sorted({b.materia_oficial for b in todo if not b.cursos_aplicables})

        assert sin == ["Robòtica i Programació"], sin

    def test_ninguna_materia_arrastra_la_coletilla_del_curso(self, todo):
        malas = [b.materia_oficial for b in todo
                 if " de quart" in b.materia_oficial or "optativa" in b.materia_oficial]

        assert malas == []

    def test_el_volumen_de_saberes_no_se_desploma(self, todo):
        """Guarda de regresión sobre el cambio más frágil del extractor.

        Los umbrales de sangrado se calculan agrupando las `x` del documento, y
        ese cálculo es sensible: al agrupar con una tolerancia mal elegida,
        Matemàtiques pasó de 176 items a **cero**, sin dar ningún error.

        Se fija una cota inferior y no un número exacto porque lo que hay que
        detectar es el desplome, no una variación de dos items.
        """
        items = sum(len(b.items) for mc in todo for b in mc.saberes)

        assert items > 1800, f"solo {items} items de saberes: algo dejó de leerse"

    def test_NINGUNA_materia_se_queda_sin_saberes(self, todo):
        """Estuvo en 17 durante una tarde, anotado como deuda con este mismo
        test fijando el número. La deuda era un fallo mío, no una fuente que
        faltara: diecisiete PDF usan **dos** niveles de sangrado —bloque e
        item— y el extractor daba por hecho que siempre eran tres.

        Se comprobó el arreglo en Matemàtiques, que es de las que tienen tres:
        el caso que ya funcionaba. De ahí que pasara por bueno.
        """
        sin = sorted({b.materia_oficial for b in todo if not b.saberes})

        assert sin == [], f"materias sin saberes: {sin}"

    def test_los_dos_formatos_de_sangrado_dan_saberes(self, todo):
        """Uno de cada, explícitos, porque el fallo consistió justamente en
        probar solo el formato que funcionaba."""
        por_materia = {b.materia_oficial: b.saberes for b in todo}

        assert por_materia["Matemàtiques"], "tres niveles: bloque · subbloque · item"
        assert por_materia["Biologia i Geologia"], "dos niveles: bloque · item"

    def test_el_anidamiento_solo_aparece_donde_lo_hay(self, todo):
        """Con tres niveles el título lleva «bloque · subbloque»; con dos, solo
        el bloque. Si se anidara siempre, las materias de dos niveles saldrían
        con un separador colgando y un subbloque inventado."""
        de_dos = [b for b in todo if b.materia_oficial == "Biologia i Geologia"][0]
        de_tres = [b for b in todo if b.materia_oficial == "Matemàtiques"][0]

        assert not any(" · " in s.titulo for s in de_dos.saberes)
        assert any(" · " in s.titulo for s in de_tres.saberes)

    def test_hay_al_menos_las_materias_comunes_de_la_eso(self, todo):
        nombres = {b.materia_oficial for b in todo}
        comunes = [
            "Matemàtiques", "Llengua Catalana i Literatura",
            "Llengua Castellana i Literatura", "Llengua Estrangera",
            "Biologia i Geologia", "Física i Química", "Educació Física",
            "Música", "Tecnologia i Digitalització",
            "Ciències Socials: Geografia i Història",
        ]

        assert [c for c in comunes if c not in nombres] == []

    def test_los_titulos_no_arrastran_la_vineta(self, todo):
        """`_es_vineta` descarta la línea que es SOLO la marca. Cuando la marca
        comparte renglón con el título —«● Context»— no se descartaba nada y la
        marca se quedaba pegada: **146 de los 384** bloques salían como
        «Comunicació · ● Context».

        No es un fallo de lectura y por eso no lo veía ningún test: los saberes
        estaban todos, con su texto correcto. Pero el título viaja al documento
        que lee el docente y al listado que se le pasa al modelo."""
        sucios = [
            s.titulo for b in todo for s in b.saberes
            if any(c in s.titulo for c in "●•○▪◦") or "  " in s.titulo
        ]

        assert sucios == [], f"{len(sucios)} títulos con viñeta: {sucios[:3]}"

    def test_el_decreto_no_numera_sus_bloques(self, todo):
        """LA COMPROBACIÓN QUE DESHIZO LA CONFUSIÓN, y merece quedar fijada.

        El código de estos saberes se trató durante días como si fuera del
        boletín, y no lo es: el Decret 175/2022 nombra sus bloques, no los
        numera. Ni uno de los 24 PDF lleva «Bloc N».

        Si algún día apareciera, este test fallaría — y sería una buena
        noticia: significaría que hay un identificador oficial que usar en vez
        del índice de orden que ponemos nosotros."""
        import re

        con_numero = [
            s.titulo for b in todo for s in b.saberes
            if re.match(r"(?i)^\s*bloc\s*\d", s.titulo)
        ]

        assert con_numero == [], (
            "el decreto SÍ numera: revisar si conviene usar su número como "
            f"código en vez del contador. Ejemplos: {con_numero[:3]}"
        )
