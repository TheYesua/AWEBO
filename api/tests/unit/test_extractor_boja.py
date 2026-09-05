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
7. El borde de columna que da `find_tables()` cae **dentro del párrafo** —298,1
   cuando la raya dibujada está en 311,2—: 122 de 737 criterios llegaban
   mutilados y cuatro materias-curso enteras. Se arregla leyendo las rayas que
   el PDF dibuja en vez de fiarse de la agrupación de PyMuPDF.
8. Cuando la columna es estrecha el código se queda **solo en su renglón**
   («2.1.»), no abre criterio y su texto se pega al anterior: Matemáticas 1.º
   salía con 17 criterios en vez de 23.
9. Y el mismo maquetado parte **dentro de la palabra sin poner guion**:
   «conocimiento» / «s necesarios».
10. El último saber de cada materia se tragaba la **introducción de la
    siguiente**, que empieza en la misma página: 59 de 957 pasaban de 400
    caracteres y el peor tenía 4238, con otra materia dentro.
11. Y un saber partido entre dos páginas cuya segunda mitad vuelve a salir en
    una tabla propia: llegaba con la coletilla dicha dos veces.

Ninguno de los once lanza una excepción. Por eso los tests de aquí comprueban
**cantidades, reparto y longitudes**, no que la función devuelva algo.

Y una advertencia sobre el propio contraste: el que buscaba los criterios en el
texto del boletín **sobrecontaba**, porque el orden de lectura de PyMuPDF
entrelaza las columnas vecinas. Ver `_texto_del_boletin` y `_trozos`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.curriculo.extractor_boja import (
    _criterios_de_celda,
    _es_tabla_de_criterios,
    _limpiar_titulo,
    _pegar_partidas,
    _restos_de,
    _sin_cola_repetida,
    _solo_del_prefijo,
    bordes_de_columna,
    extraer,
    extraer_saberes,
    rayas_verticales,
    unir,
)
from app.curriculo.extractor import BloqueSaberes


_FUENTES = Path(__file__).resolve().parents[2].parent / "curriculo" / "fuentes" / "andalucia"
PDF1 = _FUENTES / "BOJA23-104-00289-9727-01_00284752.pdf"
PDF2 = _FUENTES / "BOJA23-104-00246-9727-02_00284752.pdf"

#: El **Anexo II** —materias comunes y optativas— va de la página 49 del primer
#: PDF a la 16 del segundo; el **Anexo III** —las optativas propias de
#: Andalucía— ocupa el resto hasta el Anexo IV, que empieza en la 119.
#: Se cargan los dos: el III trae 376 criterios que hasta el 05/09/2026 no
#: llegaban a la aplicación, y no por una decisión sino por un descuido.
TRAMOS = [(PDF1, 49, None), (PDF2, 0, 16), (PDF2, 16, 119)]


def _texto_del_boletin() -> str:
    """El boletín en las **dos linealizaciones**, para buscar texto dentro.

    `get_text()` devuelve las líneas en orden de lectura, y en una tabla de
    cinco columnas eso **entrelaza celdas vecinas**: el criterio 2.1 de
    Geografía e Historia 1.º está entero y aun así no aparece seguido, porque
    entre sus renglones se cuelan los de la columna de al lado. Buscándolo solo
    ahí, 62 criterios parecían rotos y **cuarenta y ocho de ellos estaban
    bien**: la cota de este fichero llevaba semanas midiendo el orden de
    lectura de PyMuPDF y no el extractor.

    Por eso se añade una segunda pasada en **orden columna-mayor**: las
    palabras se agrupan por bandas verticales libres y cada banda se lee de
    arriba abajo. Lo que esté en cualquiera de las dos cuenta como presente.

    El pie se retira antes de unir: un criterio partido entre dos páginas lo
    lleva justo en medio y parecería que no está.
    """
    import pymupdf

    from app.curriculo.extractor_boja import RX_PIE

    paginas = [p for pdf, desde, hasta in TRAMOS
               for p in list(pymupdf.open(pdf))[desde:hasta]]

    def columna_mayor(pagina, hueco: float = 8.0) -> str:
        palabras = [w for w in pagina.get_text("words")
                    if w[4].strip() and not RX_PIE.match(w[4].strip())]
        if not palabras:
            return ""
        cortes, fin = [], sorted(palabras)[0][2]
        for x0, _, x1, *_ in sorted(palabras):
            if x0 - fin >= hueco:
                cortes.append((fin + x0) / 2)
            fin = max(fin, x1)
        cortes = [-1e9, *cortes, 1e9]
        trozos = []
        for i in range(len(cortes) - 1):
            banda = [w for w in palabras
                     if cortes[i] <= (w[0] + w[2]) / 2 < cortes[i + 1]]
            banda.sort(key=lambda w: (round(w[1] / 2), w[0]))
            if banda:
                trozos.append(" ".join(w[4] for w in banda))
        return " ".join(trozos)

    lineal = " ".join(l.strip() for p in paginas
                      for l in p.get_text().splitlines()
                      if l.strip() and not RX_PIE.match(l.strip()))
    # La barra impide que un trozo case a caballo de las dos linealizaciones.
    return _norm(lineal) + "|" + _norm(" ".join(columna_mayor(p) for p in paginas))


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _trozos(texto: str, boletin: str) -> int:
    """Cuántos pedazos **seguidos** del boletín hacen falta para cubrir `texto`.

    Uno es lo normal. Dos, cuando el criterio salta de página o de columna y
    los dos lados quedan lejos en la linealización. Tres o más significa que en
    medio hay algo que en el boletín no está: una palabra comida por el borde
    de la tabla, o una cabecera de página colada dentro de la frase.

    Se prefiere esto a «¿están los primeros sesenta caracteres?» porque aquella
    pregunta no distingue un criterio roto de uno partido en dos.
    """
    trozos, i = 0, 0
    while i < len(texto):
        bajo, alto = 0, len(texto) - i
        while bajo < alto:
            medio = (bajo + alto + 1) // 2
            if texto[i:i + medio] in boletin:
                bajo = medio
            else:
                alto = medio - 1
        trozos += 1
        i += max(bajo, 1)
    return trozos


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

    def test_el_codigo_solo_en_su_renglon_abre_criterio(self):
        """EL FALLO 8. En Matemáticas 1.º caben tres cursos en la misma tabla y
        la columna mide sesenta puntos: «2.1.» no entra con la primera palabra
        al lado y se queda solo en su renglón. Sin reconocerlo, el criterio no
        empieza y su texto se pega al anterior: 1.3 salía con 2.1 y 2.2 dentro
        —677 caracteres— y la materia con 17 criterios en vez de 23."""
        celda = "1.3. Obtener las\nsoluciones.\n2.1.\nComprobar la\ncorrección."
        _, criterios = _criterios_de_celda(celda)

        assert criterios == [("1.3", "Obtener las soluciones."),
                             ("2.1", "Comprobar la corrección.")]

    def test_la_palabra_partida_sin_guion_se_recompone(self):
        """EL FALLO 9. El mismo maquetado estrecho parte dentro de la palabra y
        **no pone guion**: «conocimiento» cierra un renglón y «s necesarios,»
        abre el siguiente. Uniendo con un espacio, el docente lee «activando
        los conocimiento s necesarios»."""
        vocabulario = {"conocimientos", "activando", "los", "necesarios"}

        assert _pegar_partidas("activando los conocimiento\ns necesarios,",
                               vocabulario) == "activando los conocimientos\nnecesarios,"

    def test_no_se_pegan_dos_palabras_que_lo_son_por_separado(self):
        """La prueba de que se pegan la da el propio PDF —la palabra resultante
        tiene que estar en la página—, pero eso solo no basta: «el» y «los» son
        palabras las dos y «ellos» existe. Se exige además que **al menos uno
        de los dos trozos no sea palabra**."""
        vocabulario = {"el", "los", "ellos", "coche"}

        assert _pegar_partidas("el\nlos coche", vocabulario) == "el\nlos coche"

    def test_el_final_repetido_al_saltar_de_pagina_se_quita(self):
        """EL FALLO 11. Un saber que se parte entre dos páginas y cuya segunda
        mitad vuelve a aparecer en una tabla propia de la página siguiente. El
        docente leía `TYD.3.E.2` con la coletilla dos veces."""
        t = ("Tecnología sostenible. Valoración crítica de la contribución a la "
             "consecución de los Objetivos de Desarrollo Sostenible. contribución "
             "a la consecución de los Objetivos de Desarrollo Sostenible.")

        assert _sin_cola_repetida(t) == (
            "Tecnología sostenible. Valoración crítica de la contribución a la "
            "consecución de los Objetivos de Desarrollo Sostenible."
        )

    def test_una_repeticion_corta_y_legitima_no_se_toca(self):
        """La cota de treinta caracteres es lo que separa el fallo de una
        repetición del boletín. «Suma, resta» dos veces seguidas es texto."""
        t = "Operaciones con ángulos. Suma, resta. Suma, resta."

        assert _sin_cola_repetida(t) == t

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
    """Los dos anexos unidos: 32 materias repartidas en 60 bloques."""

    @pytest.fixture(scope="class")
    def bloques(self, tmp_path_factory):
        unido = unir([p for p, _, _ in TRAMOS],
                     tmp_path_factory.mktemp("boja") / "anexo.pdf",
                     [(d, h) for _, d, h in TRAMOS])
        return extraer(unido)

    @pytest.fixture(scope="class")
    def boletin(self):
        return _texto_del_boletin()

    def test_el_borde_sale_de_la_raya_dibujada_y_no_de_pymupdf(self):
        """LA CAUSA RAÍZ DE LOS CRITERIOS MUTILADOS, medida en su página.

        La tabla de criterios de Educación Física 1.º y 2.º está en la página
        89 del primer PDF. `find_tables()` agrupa las verticales con tolerancia
        y coloca el borde entre criterios y saberes en **298,1**, que cae
        dentro del párrafo; el PDF **dibuja** la raya en **311,2**.

        Trece puntos de diferencia son dos o tres caracteres por renglón, y son
        los que se perdían. Este test no comprueba el texto —de eso se encargan
        los de más abajo— sino que el extractor prefiere la raya.
        """
        import pymupdf

        pagina = pymupdf.open(PDF1)[89]
        tabla = pagina.find_tables().tables[1]
        de_pymupdf = sorted({round(v, 1) for f in tabla.rows for c in f.cells if c
                             for v in (c[0], c[2])})

        assert 298.1 in de_pymupdf
        assert any(abs(x - 311.2) < 0.5 for x in rayas_verticales(pagina, tabla))
        assert any(abs(x - 311.2) < 0.5 for x in bordes_de_columna(pagina, tabla))
        assert not any(abs(x - 298.1) < 0.5 for x in bordes_de_columna(pagina, tabla))

    def test_salen_las_treinta_y_dos_materias(self, bloques):
        """Diecinueve del Anexo II y trece del III. Si aparece una de más, se
        ha colado una cabecera de tabla como materia —«Materias optativas
        propias de la Comunidad Andaluza», que es el título del Anexo III, es
        justo la que el extractor descarta por venir sin criterios ni
        saberes—; si falta alguna, se ha fundido con la anterior."""
        materias = {b.materia_efectiva for b in bloques}

        assert len(materias) == 32, sorted(materias)
        assert "Biología y Geología" in materias          # Anexo II
        assert "Tecnología y Digitalización" in materias  # Anexo II
        assert "Cultura del Flamenco" in materias         # Anexo III
        assert "Computación y Robótica" in materias       # Anexo III
        assert "Materias optativas propias de la Comunidad Andaluza" not in materias

    def test_las_optativas_propias_traen_sus_criterios(self, bloques):
        """El Anexo III no estaba cargado y no fue una decisión: nadie lo
        escribió en ninguna parte. Se descubrió contando los códigos de
        criterio de los dos anexos y viendo cuáles llegaban a la salida.

        Las cifras son del PDF, no de una ejecución anterior: son las trece
        materias del anexo, en diecinueve bloques.
        """
        del_tercero = {
            (b.materia_efectiva, b.ciclo): len(b.criterios) for b in bloques
            if b.materia_efectiva in {
                "Ampliación de Cultura Clásica", "Aprendizaje Social y Emocional",
                "Artes Escénicas y Danza", "Computación y Robótica",
                "Cultura Científica", "Cultura Clásica", "Cultura del Flamenco",
                "Dibujo Técnico", "Filosofía", "Filosofía y Argumentación",
                "Iniciación a la Actividad Emprendedora y Empresarial",
                "Oratoria y Debate", "Proyecto de Educación Plástica y Audiovisual",
            }
        }

        assert len(del_tercero) == 19, sorted(del_tercero)
        assert sum(del_tercero.values()) == 370
        # Oratoria y Debate 3.º salía con CERO: el borde de PyMuPDF caía diez
        # puntos a la izquierda del bueno y se comía el primer dígito de cada
        # código, así que «1.1» llegaba como «.1» y no casaba como criterio.
        assert del_tercero[("Oratoria y Debate", "3º ESO")] == 20

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
        debajo del enunciado y en redonda.

        LA COTA DE PORCENTAJE SE CAMBIÓ POR UNA LISTA. Estaba en «más del 80 %»
        y al cargar el Anexo III bajó a 79,7 %, que no dice nada de si algo se
        ha roto: sube y baja según cuántas materias haya. Lo que importa es
        **cuáles** se quedan sin ninguno, y son las que no tienen sección de
        competencias en texto corrido y hay que leer de la tabla, donde el
        boletín no imprime los descriptores. Son cuatro y están medidas.
        """
        sin_ninguno = sorted({
            b.materia_efectiva for b in bloques
            if not any(c.descriptores for c in b.competencias)
        })

        assert sin_ninguno == ["Computación y Robótica", "Dibujo Técnico",
                               "Matemáticas A", "Matemáticas B"]
        con = [c for b in bloques for c in b.competencias if c.descriptores]
        total = [c for b in bloques for c in b.competencias]
        assert len(con) > len(total) * 0.75

    def test_todas_las_materias_declaran_un_solo_curso(self, bloques):
        """En Andalucía el currículo va curso a curso, no por ciclos: una
        materia con dos cursos en la misma fila sería un reparto mal leído."""
        for b in bloques:
            assert len(b.cursos_aplicables) == 1, (b.materia_efectiva, b.cursos_aplicables)
            assert b.cursos_aplicables[0].endswith("º ESO")

    def test_los_criterios_estan_literalmente_en_el_boletin(self, bloques, boletin):
        """EL FALLO 7, Y EL PEOR DE TODOS: criterios mutilados.

        PyMuPDF sitúa el borde de columna **dentro del párrafo** —en Educación
        Física 1.º lo pone en x=298,1 cuando la raya dibujada está en 311,2— y
        `tabla.extract()` corta ahí. El final de cada renglón —«rar», «or-»,
        «del»— se va a la celda de los códigos de saber y se pierde. El
        criterio llegaba al docente así:

            «Identificar y establec secuencias sencillas de ac vidad física,
             orientada concepto integral de salu»

        **122 de los 737 criterios estaban así**, y cuatro materias-curso al
        completo. Ninguna comprobación lo veía: el criterio existía, tenía su
        código, su competencia y su curso, y hasta la longitud parecía
        razonable. Solo se ve comparándolo con el boletín.

        CÓMO SE MIDE, Y POR QUÉ SE CAMBIÓ LA MEDIDA
        --------------------------------------------
        La versión anterior preguntaba si los primeros sesenta caracteres
        estaban seguidos en el texto del boletín, y **sobrecontaba**: en una
        tabla de cinco columnas el orden de lectura de PyMuPDF entrelaza las
        celdas vecinas, así que un criterio intacto puede no aparecer seguido.
        De los 62 que señalaba, 48 estaban bien. Se contaba el orden de lectura
        de PyMuPDF, no el extractor.

        Ahora se cuenta **en cuántos pedazos seguidos del boletín se puede
        cubrir cada criterio** —ver `_trozos`—. Uno o dos es normal: dos es un
        criterio que salta de página. Tres o más significa que hay algo en
        medio que en el boletín no está.

        SE COMPRUEBA CON UNA COTA Y NO CON CERO, y la cota es deuda escrita.
        Quedan cinco, de tres causas distintas y todas medidas:

          * dos con la cabecera de la página siguiente metida dentro de la
            frase («…entre los pueblos. Geografía e Historia Criterios de
            evaluación»),
          * uno con una palabra en cursiva descolocada al final («…el big y la
            inteligencia artificial… ético. data»),
          * dos de Matemáticas 3.º con una palabra de menos.

        Si el número sube, algo ha empeorado. Si baja, se baja la cota.
        """
        rotos = [
            (b.materia_efectiva, b.ciclo, cr.codigo)
            for b in bloques for cr in b.criterios
            if _trozos(_norm(cr.descripcion), boletin) > 2
        ]

        assert len(rotos) <= 5, (
            f"{len(rotos)} criterios no se encuentran de una pieza en el BOJA "
            f"(la cota es 5): {rotos[:8]}"
        )

    def test_ningun_saber_se_traga_el_texto_de_la_materia_siguiente(self, bloques, boletin):
        """EL MISMO FALLO QUE EL DE ARRIBA, EN LA OTRA MITAD DEL CATÁLOGO.

        Una materia acaba a media página y la siguiente empieza debajo, así que
        la última página de su tramo trae las dos. El último saber es el que
        queda abierto, y se comía la introducción entera de la materia
        siguiente: **59 de los 957 saberes medían más de 400 caracteres y el
        peor 4238**, con el texto de otra materia dentro. Iba al documento del
        docente tal cual, y ni el recuento —los saberes salían todos— ni el
        reparto por bloques lo notaban.

        Estuvo así desde que se cargó Andalucía. Lo destapó cargar el Anexo III:
        el último saber de Tecnología y Digitalización 3.º, que es la última
        materia del Anexo II, se tragó la portada del Anexo III y la
        introducción de Ampliación de Cultura Clásica.

        Se comprueba de dos maneras porque miden cosas distintas: la longitud
        ve el texto pegado de otra sección, y los trozos ven los renglones
        entrelazados de la columna de al lado, que no alargan nada.
        """
        largos = sorted(
            (len(item), b.materia_efectiva, b.ciclo, codigo)
            for b in bloques for bl in b.saberes
            for codigo, item in zip(bl.codigos_items, bl.items)
        )
        assert largos[-1][0] <= 1100, f"saber de {largos[-1][0]} caracteres: {largos[-1][1:]}"

        rotos = [
            (b.materia_efectiva, b.ciclo, codigo)
            for b in bloques for bl in b.saberes
            for codigo, item in zip(bl.codigos_items, bl.items)
            if _trozos(_norm(item), boletin) > 2
        ]
        # Seis, y dos de ellos son del propio boletín: «Software» va en cursiva
        # y sale del PDF como «Sofwt are».
        assert len(rotos) <= 6, (
            f"{len(rotos)} saberes no se encuentran de una pieza en el BOJA "
            f"(la cota es 6): {rotos[:8]}"
        )

    def test_ningun_saber_acaba_con_el_nombre_de_otra_materia(self, bloques):
        """La otra mitad del fallo anterior, y **no la ve ninguna cota**.

        Cortar por la altura del título de la materia siguiente arregla la
        introducción entera, pero no el título en sí cuando `find_tables()` lo
        mete **dentro** de la caja de la última tabla: ahí ya no es una línea
        suelta y el filtro por altura no lo alcanza. Trece saberes acababan
        así, y ninguno era largo ni dejaba de estar en el boletín:

            «…para la autoevaluación, la coevaluación y la autorreparación.
             Lengua Castellana y Literatura»

        Aquí sí se exige cero: el título de la materia siguiente se conoce, y
        una línea que sea exactamente ese título no es un saber.
        """
        nombres = {b.materia_efectiva for b in bloques}
        colados = [
            (b.materia_efectiva, b.ciclo, codigo, nombre)
            for b in bloques for bl in b.saberes
            for codigo, item in zip(bl.codigos_items, bl.items)
            for nombre in nombres
            if item.rstrip().endswith(nombre) and item.strip() != nombre
        ]

        assert colados == []

    @pytest.mark.parametrize("materia, curso", [
        ("Matemáticas", "2º ESO"),
        ("Lengua Castellana y Literatura", "1º ESO"),
        ("Educación Física", "1º ESO"),
        ("Educación Física", "3º ESO"),
        ("Oratoria y Debate", "3º ESO"),
    ])
    def test_las_que_estaban_rotas_enteras(self, bloques, boletin, materia, curso):
        """Las materias-curso donde **todos** los criterios estaban mutilados.
        Se fijan una a una porque una cota global las dejaría volver sin que
        nadie lo notara: cinco sobre 1113 no llama la atención.

        Oratoria y Debate 3.º es la quinta y es del Anexo III: allí el borde
        caía al otro lado y se comía el primer dígito del código, así que la
        materia salía con cero criterios en vez de con veinte.
        """
        suyos = [b for b in bloques
                 if b.materia_efectiva == materia and b.cursos_aplicables == [curso]]
        assert suyos, f"no está {materia} · {curso}"

        rotos = [cr.codigo for b in suyos for cr in b.criterios
                 if _trozos(_norm(cr.descripcion), boletin) > 2]

        assert rotos == [], f"{materia} {curso}: {len(rotos)} mutilados, {rotos[:6]}"
