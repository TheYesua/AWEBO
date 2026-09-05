"""Tests del extractor del BOJA (currículo andaluz).

No tocan base de datos ni Flask. Se ejecutan contra los **PDF reales**, que no
están en el repositorio por tamaño: si no están, la clase se salta entera.

DÓNDE ESTÁ EL RIESGO EN ESTE EXTRACTOR
---------------------------------------
En lo mismo que en el catalán: no en que falle, sino en que **acierte a medias
sin decirlo**. Todos los fallos que se cometieron escribiéndolo tuvieron el
mismo síntoma —ninguno— y salieron a la luz contando, no ejecutando:

1. «Competencias específicas» encabeza además la primera columna de la tabla de
   criterios, así que cada materia se partía en dos. La primera mitad se
   quedaba sin saberes y sin criterios.
2. «Música» y «Matemáticas A» aparecen otra vez como cabecera de su tabla, en
   negrita y centradas igual que en la portada: salían dos materias con el
   mismo nombre, la segunda vacía.
3. La tabla de criterios de una materia ocupa hasta siete páginas y solo la
   primera lleva cabecera. Buscándola, Biología y Geología salía con **un**
   criterio en lugar de diecinueve.
4. La tabla de saberes de Matemáticas tiene tres columnas —tres cursos— y la
   heurística de forma la confundía con una tabla de criterios: Matemáticas se
   quedaba sin un solo saber en 1.º, 2.º ni 3.º.
5. El código de saber queda partido por el borde de la tabla («GE» en una celda
   y «H.3.A.2.» en la siguiente), y como el curso sale del código, cuatro
   materias se quedaban con cero criterios en un curso.
6. Los criterios largos se parten entre dos páginas y la continuación no lleva
   código: sesenta y siete se guardaban a medias, con código y competencia
   correctos y dos tercios de la frase de menos.

Ninguno de los seis lanza una excepción. Por eso los tests de aquí comprueban
**cantidades, reparto y longitudes**, no que la función devuelva algo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.curriculo.extractor_boja import (
    _criterios_de_celda,
    _es_tabla_de_criterios,
    _limpiar_titulo,
    _restos_de,
    _solo_del_prefijo,
    extraer,
    extraer_saberes,
    unir,
)
from app.curriculo.extractor import BloqueSaberes


_FUENTES = Path(__file__).resolve().parents[2].parent / "curriculo" / "fuentes" / "andalucia"
PDF1 = _FUENTES / "BOJA23-104-00289-9727-01_00284752.pdf"
PDF2 = _FUENTES / "BOJA23-104-00246-9727-02_00284752.pdf"

#: El Anexo II ocupa de la página 49 del primero al principio del segundo.
TRAMOS = [(49, None), (0, 16)]


# ---------------------------------------------------------------------------
# Sin PDF
# ---------------------------------------------------------------------------


class TestPiezasSueltas:
    """Lo que se puede comprobar sin abrir ningún fichero."""

    @pytest.mark.parametrize("crudo, limpio", [
        ("Educación en Valores Cívicos y Éticos.", "Educación en Valores Cívicos y Éticos"),
        ("Biología y Geología", "Biología y Geología"),
    ])
    def test_el_punto_final_del_titulo_no_es_parte_del_nombre(self, crudo, limpio):
        """El boletín lo pone en unos títulos y no en otros. Si se conserva,
        «Educación en Valores Cívicos y Éticos.» y la misma materia sin punto
        son dos entradas distintas del desplegable."""
        assert _limpiar_titulo(crudo) == limpio

    def test_los_restos_van_de_mas_largo_a_mas_corto(self):
        """Se quita el mayor que encaje: buscando «G» antes que «GEH» quedaría
        «EH» pegado al final del criterio."""
        assert _restos_de("GEH") == ["GEH", "GE", "G"]
        assert _restos_de("") == []

    def test_se_barre_el_resto_del_codigo_partido_por_el_borde(self):
        """EL FALLO: la línea vertical de la tabla parte «GEH.3.A.2.» y deja
        «GE» en la celda del criterio. Sin barrerlo, el docente lee «Elaborar
        contenidos GE propios en distintos GE formatos»."""
        celda = "1.1. Elaborar contenidos GE\npropios en distintos GE\nformatos."
        _, criterios = _criterios_de_celda(celda, "GEH")

        assert criterios == [("1.1", "Elaborar contenidos propios en distintos formatos.")]

    def test_no_se_barren_mayusculas_que_no_son_del_codigo(self):
        """Barrer cualquier sigla al final de línea se comería texto legítimo.
        Solo se quitan prefijos propios del código de esta materia."""
        _, criterios = _criterios_de_celda("1.1. Usar la norma UNE\ny la ISO.", "GEH")

        assert criterios[0][1] == "Usar la norma UNE y la ISO."

    def test_lo_que_va_antes_del_primer_codigo_se_devuelve_aparte(self):
        """Es la cola del criterio de la celda de arriba. Descartándola, 67
        criterios se guardaban partidos."""
        preludio, criterios = _criterios_de_celda(
            "y sostenible en el tiempo.\n2.1. Analizar los datos.", ""
        )

        assert preludio == "y sostenible en el tiempo."
        assert criterios == [("2.1", "Analizar los datos.")]

    def test_una_tabla_de_saberes_de_tres_columnas_no_es_de_criterios(self):
        """EL FALLO 4. La de Matemáticas tiene tres columnas —una por curso— y
        está llena de códigos. Clasificándola por la forma se saltaba entera y
        Matemáticas se quedaba sin saberes en tres cursos."""
        saberes = [["PRIMERO", "SEGUNDO", "TERCERO"],
                   ["MAT.1.A.1. Conteo.", "MAT.2.A.1. Conteo.", "MAT.3.A.1. Conteo."]]

        assert not _es_tabla_de_criterios(saberes)

    def test_una_tabla_con_criterios_si_lo_es(self):
        criterios = [["Competencias", "Criterios", "Saberes"],
                     ["1. Interpretar…", "1.1. Analizar…", "MAT.1.A.1."]]

        assert _es_tabla_de_criterios(criterios)

    def test_el_curso_sale_del_codigo_y_no_del_orden(self):
        """Es la propiedad que hace este boletín distinto de todos los demás:
        cada saber dice de qué curso es. Aunque el texto venga entremezclado
        entre dos columnas, cada item acaba en su curso."""
        por_curso = extraer_saberes([
            "A. Proyecto científico.",
            "BYG.1.A.1. Formulación de hipótesis.",
            "BYG.3.A.1. Formulación de hipótesis, con más detalle.",
        ])

        assert sorted(por_curso) == [1, 3]
        assert por_curso[1][0].codigos_items == ["BYG.1.A.1"]
        assert por_curso[3][0].codigos_items == ["BYG.3.A.1"]

    def test_un_saber_sin_texto_no_se_guarda(self):
        """Un código que quedó suelto de su contenido. Guardarlo daría una fila
        de currículo sin descripción, que no se puede ni mostrar ni citar."""
        por_curso = extraer_saberes(["A. Bloque.", "BYG.1.A.1.", "BYG.1.A.2. Con texto."])

        assert por_curso[1][0].codigos_items == ["BYG.1.A.2"]

    def test_las_continuaciones_se_pegan_al_saber_abierto(self):
        por_curso = extraer_saberes([
            "A. Proyecto científico.",
            "BYG.1.A.1. Formulación de hipótesis, preguntas y",
            "conjeturas: planteamiento con perspectiva científica.",
        ])

        assert por_curso[1][0].items[0].endswith("perspectiva científica.")

    def test_una_competencia_con_el_numero_solo_en_su_linea(self):
        """La justificación deja «2.» en una línea y el enunciado en la
        siguiente. Pasa en Tecnología y Digitalización, y el efecto era que esa
        competencia **no existía**: se cargaban las otras seis y los criterios
        2.1 a 2.4 apuntaban a una competencia ausente."""
        from app.curriculo.extractor_boja import Linea, extraer_competencias

        comps = extraer_competencias([
            Linea(0, 64.5, 0, True, "Competencias específicas."),
            Linea(0, 64.5, 1, True, "1. Buscar y seleccionar la información."),
            Linea(0, 64.5, 2, False, "CPSAA4, CE1."),
            Linea(0, 64.5, 3, True, "2."),
            Linea(0, 81.1, 4, True, "Abordar problemas tecnológicos con autonomía,"),
            Linea(0, 64.5, 5, True, "aplicando conocimientos interdisciplinares."),
            Linea(0, 64.5, 6, False, "CD2, CE3."),
        ])

        assert [c.codigo for c in comps] == ["1", "2"]
        assert comps[1].descripcion.startswith("Abordar problemas")
        assert comps[1].descripcion.endswith("interdisciplinares.")

    def test_se_descartan_los_saberes_de_otra_materia(self):
        """El tramo de páginas de una materia se solapa con la primera de la
        siguiente. Sin filtrar, aparecía una «Matemáticas 4º» fantasma con
        cinco saberes de Matemáticas A y ningún criterio."""
        entrada = {4: [BloqueSaberes(
            codigo="A", titulo="Sentido numérico",
            items=["Conteo.", "Cantidad."],
            codigos_items=["MAT.4.A.1", "MAA.4.A.2"],
        )]}

        limpio = _solo_del_prefijo(entrada, "MAT")

        assert limpio[4][0].codigos_items == ["MAT.4.A.1"]


# ---------------------------------------------------------------------------
# Contra los PDF reales
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not PDF1.exists() or not PDF2.exists(),
                    reason=f"no están los PDF del BOJA en {_FUENTES}")
class TestElAnexoEntero:
    """Los dos PDF unidos: 19 materias repartidas en 41 bloques."""

    @pytest.fixture(scope="class")
    def bloques(self, tmp_path_factory):
        unido = unir([PDF1, PDF2], tmp_path_factory.mktemp("boja") / "anexo.pdf", TRAMOS)
        return extraer(unido)

    def test_salen_las_diecinueve_materias(self, bloques):
        """Si aparecen veinte, se ha colado una cabecera de tabla como materia;
        si diecisiete, dos se han fundido con la anterior."""
        materias = {b.materia_efectiva for b in bloques}

        assert len(materias) == 19, sorted(materias)
        assert "Biología y Geología" in materias
        assert "Tecnología y Digitalización" in materias

    def test_ninguna_materia_sale_dos_veces_con_el_mismo_curso(self, bloques):
        """EL FALLO 2. «Música» aparece en su portada y otra vez como cabecera
        de su tabla de criterios, con el mismo formato. Salían dos materias, la
        segunda con cero competencias y cero saberes."""
        claves = [(b.materia_efectiva, b.ciclo) for b in bloques]

        assert len(claves) == len(set(claves)), "hay bloques duplicados"

    def test_ningun_bloque_sale_a_medias(self, bloques):
        """EL TEST QUE IMPORTA. Un bloque sin criterios o sin saberes no da
        error en ninguna capa: se carga, sale en el desplegable, y al generar
        una SdA con él la conexión curricular queda vacía."""
        cojos = [
            (b.materia_efectiva, b.ciclo,
             len(b.competencias), len(b.criterios), len(b.saberes))
            for b in bloques
            if not b.competencias or not b.criterios or not b.saberes
        ]

        assert cojos == []

    def test_matematicas_de_cuarto_son_dos_itinerarios(self, bloques):
        """A y B son itinerarios, no materias sueltas, y el modelo ya lo
        contempla. Además **no tienen sección de competencias en texto
        corrido**: si no se leyeran de la tabla saldrían con cero."""
        por_nombre = {b.materia_efectiva: b for b in bloques if b.ciclo == "4º ESO"}

        assert por_nombre["Matemáticas A"].itinerario == "A"
        assert por_nombre["Matemáticas B"].itinerario == "B"
        assert len(por_nombre["Matemáticas A"].competencias) == 10
        # Y no una tercera «Matemáticas» de 4.º, que sería la fusión de las dos.
        assert "Matemáticas" not in por_nombre

    def test_biologia_y_geologia_tiene_los_saberes_que_dice_el_boletin(self, bloques):
        """Recuento hecho a mano sobre el PDF: bloques A(9) B(8) C(3) D(6) E(8).
        Es el contraste que detectó que los saberes se estaban contando por
        duplicado —salían 89— al solaparse los tramos de página."""
        b = next(x for x in bloques
                 if x.materia_efectiva == "Biología y Geología" and x.ciclo == "1º ESO")

        assert sum(len(bl.items) for bl in b.saberes) == 34
        assert [bl.codigo for bl in b.saberes] == ["A", "B", "C", "D", "E"]
        assert len(b.saberes[0].items) == 9

    def test_cada_saber_conserva_el_codigo_oficial(self, bloques):
        """Es lo que este boletín da y los demás no. Sin él, el cargador les
        pone un contador propio que no aparece en ninguna norma."""
        b = next(x for x in bloques
                 if x.materia_efectiva == "Biología y Geología" and x.ciclo == "1º ESO")

        assert b.saberes[0].codigos_items[0] == "BYG.1.A.1"
        for bl in b.saberes:
            assert len(bl.items) == len(bl.codigos_items)

    def test_el_curso_del_codigo_coincide_con_el_del_bloque(self, bloques):
        """La comprobación cruzada que en Cataluña no se podía hacer: allí el
        curso solo venía del reparto en columnas, así que una columna mal
        partida se tragaba media materia en silencio."""
        for b in bloques:
            esperado = b.cursos_aplicables[0][0]      # "3º ESO" -> "3"
            for bl in b.saberes:
                for codigo in bl.codigos_items:
                    assert codigo.split(".")[1] == esperado, (
                        f"{b.materia_efectiva} {b.ciclo}: {codigo}"
                    )

    def test_los_criterios_llegan_enteros(self, bloques):
        """EL FALLO 6. Los criterios largos se parten entre dos páginas y la
        continuación no lleva código. Se perdían 67 de 737, con el código y la
        competencia correctos y la frase a medias: nada que un test de
        «devuelve algo» pueda ver."""
        criterios = [c for b in bloques for c in b.criterios]

        assert len(criterios) > 700
        cortados = [c.codigo for c in criterios if len(c.descripcion) < 40]
        assert len(cortados) <= 5, f"{len(cortados)} criterios a medias: {cortados[:10]}"

    def test_cada_criterio_apunta_a_una_competencia_que_existe(self, bloques):
        """Un criterio que cite una competencia inexistente rompe el enlace
        curricular al generar, y el fallo aparece muy lejos de aquí."""
        for b in bloques:
            codigos = {c.codigo for c in b.competencias}
            for cr in b.criterios:
                assert cr.competencia in codigos, (
                    f"{b.materia_efectiva} {b.ciclo}: criterio {cr.codigo} "
                    f"apunta a CE{cr.competencia}, que no está en {sorted(codigos)}"
                )

    def test_las_competencias_traen_sus_descriptores(self, bloques):
        """Los del perfil de salida («STEM3, CD1, CE3»), que van en la línea de
        debajo del enunciado y en redonda. Solo las que se leen de la tabla
        —Matemáticas A y B— pueden no tenerlos."""
        con = [c for b in bloques for c in b.competencias if c.descriptores]
        total = [c for b in bloques for c in b.competencias]

        assert len(con) > len(total) * 0.8

    def test_todas_las_materias_declaran_un_solo_curso(self, bloques):
        """En Andalucía el currículo va curso a curso, no por ciclos: una
        materia con dos cursos en la misma fila sería un reparto mal leído."""
        for b in bloques:
            assert len(b.cursos_aplicables) == 1, (b.materia_efectiva, b.cursos_aplicables)
            assert b.cursos_aplicables[0].endswith("º ESO")

    def test_los_criterios_estan_literalmente_en_el_boletin(self, bloques):
        """EL FALLO 7, Y EL PEOR DE TODOS: criterios mutilados.

        PyMuPDF detecta en muchas páginas **una columna de más**, con la línea
        vertical cayendo a mitad del texto de los criterios. `tabla.extract()`
        corta ahí, y el final de cada renglón —«rar», «or-», «del»— se va a la
        celda de los códigos de saber y se pierde. El criterio llega al docente
        así:

            «Identificar y establec secuencias sencillas de ac vidad física,
             orientada concepto integral de salu»

        **122 de los 737 criterios andaluces estaban así**, y cuatro
        materias-curso al completo. Ninguna comprobación lo veía: el criterio
        existía, tenía su código, su competencia y su curso, y hasta la
        longitud parecía razonable. Solo se ve comparándolo con el boletín.

        SE COMPRUEBA CON UNA COTA Y NO CON CERO, y la cota es deuda escrita.
        Quedan 63: el mismo fallo cuando lo que se pierde es una palabra corta
        —«y», «la», «de»—. Detectarlos es fácil; arreglarlos activa la
        reconstrucción en tablas donde `extract()` acierta y la reconstrucción
        no, y esa causa **no está demostrada**. Ver la hoja de ruta.

        Si el número sube, algo ha empeorado. Si baja, se baja la cota.
        """
        import re
        import unicodedata

        import pymupdf

        from app.curriculo.extractor_boja import RX_PIE

        def norm(s: str) -> str:
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
            return re.sub(r"[^a-z0-9]+", "", s.lower())

        # El pie se retira antes de unir: un criterio partido entre dos páginas
        # lo lleva justo en medio y parecería que no está.
        crudo = " ".join(
            l.strip()
            for pdf, (desde, hasta) in zip((PDF1, PDF2), TRAMOS)
            for pagina in list(pymupdf.open(pdf))[desde:hasta]
            for l in pagina.get_text().splitlines()
            if l.strip() and not RX_PIE.match(l.strip())
        )
        boletin = norm(crudo)

        sueltos = [
            (b.materia_efectiva, b.ciclo, cr.codigo)
            for b in bloques for cr in b.criterios
            if norm(cr.descripcion)[:60] not in boletin
        ]

        assert len(sueltos) <= 63, (
            f"{len(sueltos)} criterios no aparecen literalmente en el BOJA "
            f"(la cota es 63): {sueltos[:8]}"
        )

    @pytest.mark.parametrize("materia, curso", [
        ("Matemáticas", "2º ESO"),
        ("Lengua Castellana y Literatura", "1º ESO"),
        ("Educación Física", "1º ESO"),
        ("Educación Física", "3º ESO"),
    ])
    def test_las_cuatro_que_estaban_rotas_enteras(self, bloques, materia, curso):
        """Las cuatro materias-curso donde **todos** los criterios estaban
        mutilados. Se fijan una a una porque una cota global las dejaría
        volver sin que nadie lo notara: 63 sobre 737 no llama la atención.
        """
        import re
        import unicodedata

        import pymupdf

        from app.curriculo.extractor_boja import RX_PIE

        def norm(s: str) -> str:
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
            return re.sub(r"[^a-z0-9]+", "", s.lower())

        boletin = norm(" ".join(
            l.strip()
            for pdf, (desde, hasta) in zip((PDF1, PDF2), TRAMOS)
            for pagina in list(pymupdf.open(pdf))[desde:hasta]
            for l in pagina.get_text().splitlines()
            if l.strip() and not RX_PIE.match(l.strip())
        ))
        suyos = [b for b in bloques
                 if b.materia_efectiva == materia and b.cursos_aplicables == [curso]]
        assert suyos, f"no está {materia} · {curso}"

        rotos = [cr.codigo for b in suyos for cr in b.criterios
                 if norm(cr.descripcion)[:60] not in boletin]

        assert len(rotos) <= 10, f"{materia} {curso}: {len(rotos)} mutilados, {rotos[:6]}"
