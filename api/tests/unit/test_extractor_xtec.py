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
from app.curriculo.xtec_etapas import ESO as ESO_XTEC
from app.curriculo.xtec_etapas import BACHILLERATO, CURSOS_BACHILLERATO


_FUENTES = Path(__file__).resolve().parents[2].parent / "curriculo" / "fuentes" / "cataluna"
XTEC = _FUENTES / "xtec"
ARTICULADO = _FUENTES / "decret_175_2022.xml"

MATES = XTEC / "Matematiques.pdf"
LENGUAS = XTEC / "Aranes.Castella.-Catala.pdf"
CULTURA = XTEC / "Cultura-Cientifica.pdf"


def _codigos_de_criterio(pdf: Path) -> int:
    """Cuántas líneas del PDF empiezan por un código de criterio, «3.2 ».

    LA COMPROBACIÓN MÁS FUERTE DEL FICHERO, y la que faltaba: aquí sí se puede
    exigir **igualdad**, no una cota. Cada criterio del decreto empieza su
    primera línea con su código, así que contarlos en el PDF da el número
    exacto que tiene que salir del extractor.

    Con ella se encontraron de golpe tres fallos que llevaban meses cargados y
    ninguno daba error:

    - Las tablas que cruzan de página perdían su continuación, porque el corte
      se hacía comparando solo la `y` y en la página siguiente la `y` es
      pequeña. 67 criterios de Bachillerato y 18 de la ESO.
    - «Criteris avaluació» sin la `d'`, en Física i Química: cuatro criterios.
    - Dos columnas cuya cabecera no se reconocía se fundían en un tramo, con
      el código repetido; al cargar, el segundo pisaba al primero.
    """
    import re

    import pymupdf

    doc = pymupdf.open(pdf)
    return sum(
        1
        for pagina in doc
        for bloque in pagina.get_text("dict")["blocks"]
        for linea in bloque.get("lines", [])
        if re.match(r"^\d+\.\d+\.?\s+\S",
                    "".join(s["text"] for s in linea["spans"]).strip())
    )


def _guiones_de_sabers(pdf: Path) -> int:
    """Cuántas líneas del epígrafe «Sabers» empiezan por guion.

    LA GUARDA QUE FALTABA, y por qué se cuenta así. Los tests de este fichero
    detectaban «cero saberes» y «el total se desploma». No detectaban **«sale
    poco, pero no cero»**, que es como falló «Química»: doce items en trece
    páginas de decreto, todos ellos títulos de subbloque, porque ese PDF sangra
    el subbloque a la derecha del saber y no al revés.

    Doce no dispara ninguna alarma y los textos parecen saberes cortos. Lo que
    sí lo delata es que el PDF tiene 44 renglones que empiezan por guion.

    Es una cota, no una igualdad: hay saberes escritos sin guion —«Estada a
    l'Empresa» no usa ninguno— y continuaciones que se vuelven a juntar. Por
    eso la comprobación es «no puede haber menos items que guiones», con dos de
    margen.
    """
    import re

    import pymupdf

    doc = pymupdf.open(pdf)
    dentro, n = False, 0
    for pagina in doc:
        for bloque in pagina.get_text("dict")["blocks"]:
            for linea in bloque.get("lines", []):
                t = "".join(s["text"] for s in linea["spans"]).strip()
                if not t:
                    continue
                if t == "Sabers":
                    dentro = True
                    continue
                if dentro and re.match(r"^[-–—−]($|\s)", t):
                    n += 1
    return n


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

        LA COTA BAJÓ DE 1800 A 1250 EL 03/09, Y NO PORQUE SE PERDIERA NADA.
        Hasta esa fecha nueve materias contaban sus saberes **dos veces**: su
        epígrafe viene partido en «Primer i segon curs» / «Tercer i quart
        curs» y los dos tramos se cargaban con los dos juegos enteros. Al
        repartirlos, el total pasó de 1918 a 1330 sin que desapareciera un solo
        item —lo comprueba `test_el_reparto_por_curso_no_pierde_ni_duplica`—.
        """
        items = sum(len(b.items) for mc in todo for b in mc.saberes)

        assert items > 1250, f"solo {items} items de saberes: algo dejó de leerse"

    def test_el_reparto_por_curso_no_pierde_ni_duplica(self, todo):
        """La propiedad que de verdad importa del reparto por curso.

        Seis PDF de la ESO parten los saberes con «Primer i segon curs» y
        «Tercer i quart curs», y Ciències Socials con «Primer i segon» a secas.
        Antes del 03/09 cada tramo se llevaba los dos juegos: **en 1.º de ESO
        salían los saberes de 4.º**. No fallaba nada; solo era falso.

        Contar items no basta para comprobarlo —repartir mal la mitad da el
        mismo total—, así que lo que se comprueba es que **cada tramo tenga
        saberes que el otro no tenga**. Con el fallo los dos conjuntos eran
        idénticos; ahora tienen que solaparse poco y nada más.

        NO SE EXIGE SOLAPE CERO, y se comprobó antes de rebajarlo: el decreto
        repite literalmente algunos saberes en los dos tramos. «Formulació de
        preguntes, hipòtesis i conjectures científiques» aparece dos veces en
        el PDF de Biologia i Geologia, una por tramo. Son 5 de 43 y 5 de 23.
        """
        por_materia: dict[str, list[set[str]]] = {}
        for mc in todo:
            por_materia.setdefault(mc.materia_oficial, []).append(
                {i for b in mc.saberes for i in b.items}
            )

        # Emprenedoria no sale de un epígrafe partido sino de **dos PDF**
        # distintos, uno de 1.º-3.º y otro de 4.º, y el decreto repite diez
        # saberes idénticos entre los dos. Se comprobó contándolos en el texto
        # de cada fichero: uno y uno, no dos en el mismo.
        DE_DOS_FICHEROS = {"Emprenedoria"}

        iguales = []
        muy_solapados = []
        for m, tramos in por_materia.items():
            if len(tramos) != 2 or not all(tramos) or m in DE_DOS_FICHEROS:
                continue
            uno, otro = tramos
            if uno == otro:
                iguales.append(m)
            elif len(uno & otro) > 0.4 * min(len(uno), len(otro)):
                muy_solapados.append((m, len(uno & otro), len(uno), len(otro)))

        assert iguales == [], f"los dos tramos traen lo mismo: {iguales}"
        assert muy_solapados == [], f"solape sospechoso: {muy_solapados}"

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


@pytest.mark.skipif(not ARTICULADO.exists(), reason=f"no está {ARTICULADO}")
class TestLaMateriaQueElDecretoNoLista:
    """«Robòtica i Programació» la publica la XTEC y el decreto no la nombra.

    EL FALLO QUE ESTO ARREGLA, Y LA REGLA QUE LO CAUSÓ. La regla dice que una
    materia sin cursos **se queda sin cursos y se avisa**, en vez de darle los
    cuatro por defecto; gracias a ella Llatí dejó de ofrecerse en 1.º de ESO.

    Pero tiene un coste que apareció el 16/08: esta materia se cargaba con la
    lista vacía y quedaba **invisible**. No sale en el desplegable ni en el
    contexto del modelo, así que sus 4 competencias, 16 criterios y 13 saberes
    estaban en la base de datos sin que nadie pudiera usarlos. Y no daba error
    al usarla: sencillamente no existía.

    La salida no es relajar la regla sino documentar la excepción con su
    fuente. Es optativa de oferta obligatoria en el primer ciclo, así que va en
    1.º, 2.º y 3.º; **4.º queda fuera**, que ahí ya no es de oferta obligatoria.
    """

    def test_recibe_los_cursos_del_primer_ciclo(self):
        from app.curriculo.extractor_xtec import CURSOS_FUERA_DEL_ARTICULADO

        cursos = {_clave(k): v for k, v in CURSOS_FUERA_DEL_ARTICULADO.items()}

        assert cursos[_clave("Robòtica i Programació")] == ["1º ESO", "2º ESO", "3º ESO"]

    def test_el_decreto_sigue_sin_listarla(self):
        """Si algún día apareciera en el articulado, esta excepción sobra y
        habría que quitarla: el dato del decreto siempre manda sobre el
        nuestro. Este test avisaría."""
        del_decreto = {_clave(k) for k in cursos_del_articulado(ARTICULADO)}

        assert _clave("Robòtica i Programació") not in del_decreto, (
            "el decreto ya la lista: quita la entrada de CURSOS_FUERA_DEL_ARTICULADO"
        )

    def test_la_excepcion_no_pisa_al_articulado(self):
        """El orden importa: primero el decreto, y solo si no dice nada, la
        excepción. Al revés, una materia bien listada podría acabar con los
        cursos que alguien escribió a mano hace meses."""
        import inspect

        from app.curriculo import extractor_xtec as m

        fuente = inspect.getsource(m.main)

        assert "por_clave.get(clave) or fuera.get(clave" in fuente


# ---------------------------------------------------------------------------
# Bachillerato: Decret 171/2022, modificado por el Decret 103/2026
# ---------------------------------------------------------------------------

BATX = (Path(__file__).resolve().parents[2].parent
        / "curriculo" / "fuentes" / "cataluna-batxillerat")


class TestLaTablaDeCursosDeBachillerato:
    """Sin PDF: lo que se transcribió del DOIGC del curso 2026-2027."""

    def test_las_ciencias_de_primero_son_las_unificadas(self):
        """EL CAMBIO DEL DECRET 103/2026, que es lo que más fácil sería cargar
        mal: desde 2026-2027 en 1.º no hay Biologia ni Física por separado,
        sino «Biologia, Geologia i Ciències Ambientals» y «Física i Química».
        Las sueltas son de 2.º.

        El articulado original del 171/2022 —que sigue publicado como texto
        aprobado por el Govern— da el reparto anterior. Si alguien lo usa para
        «corregir» esta tabla, este test lo dice.
        """
        assert CURSOS_BACHILLERATO["Biologia, Geologia i Ciències Ambientals"] == \
            ["1º Bachillerato"]
        assert CURSOS_BACHILLERATO["Física i Química"] == ["1º Bachillerato"]
        assert CURSOS_BACHILLERATO["Biologia"] == ["2º Bachillerato"]
        assert CURSOS_BACHILLERATO["Física"] == ["2º Bachillerato"]
        assert CURSOS_BACHILLERATO["Química"] == ["2º Bachillerato"]
        assert CURSOS_BACHILLERATO["Geologia i Ciències Ambientals"] == \
            ["2º Bachillerato"]

    def test_las_cabeceras_de_columna_de_bachillerato_casan(self):
        """La de la ESO no contempla la palabra «curs». Con ella, las 17
        materias con tabla de dos columnas salían con los criterios de los dos
        cursos revueltos en un solo tramo."""
        assert BACHILLERATO.cursos_de_cabecera("1r curs") == ["1º Bachillerato"]
        assert BACHILLERATO.cursos_de_cabecera("2n curs") == ["2º Bachillerato"]
        assert BACHILLERATO.rx_cabecera_cursos.match("1r curs")
        assert not ESO_XTEC.rx_cabecera_cursos.match("1r curs")

    @pytest.mark.parametrize("cabecera, cursos", [
        ("Primer curs", ["1º Bachillerato"]),
        ("Segon curs", ["2º Bachillerato"]),
    ])
    def test_las_cabeceras_que_parten_los_saberes(self, cabecera, cursos):
        assert BACHILLERATO.curso_de_saberes(cabecera) == cursos

    @pytest.mark.parametrize("cabecera, cursos", [
        ("Primer i segon curs", ["1º ESO", "2º ESO"]),
        ("Primer i segon", ["1º ESO", "2º ESO"]),
        ("De primer a tercer curs", ["1º ESO", "2º ESO", "3º ESO"]),
        ("Primer, segon i tercer curs", ["1º ESO", "2º ESO", "3º ESO"]),
        ("Cursos de primer a tercer", ["1º ESO", "2º ESO", "3º ESO"]),
        ("Matèria optativa de quart curs", ["4º ESO"]),
        ("Quart curs", ["4º ESO"]),
    ])
    def test_las_cinco_maneras_de_decir_lo_mismo_en_la_eso(self, cabecera, cursos):
        """Cada fórmula sale de un PDF distinto, y todas parten los saberes.

        «Matèria optativa de quart curs» estuvo un rato en un test que decía
        justo lo contrario —que NO era una cabecera—, escrito mirando la
        expresión regular en vez del PDF de Música. Lo es, y no reconocerla
        dejaba los dos tramos de Música con los mismos saberes.
        """
        assert ESO_XTEC.curso_de_saberes(cabecera) == cursos

    def test_un_titulo_de_bloque_no_se_confunde_con_una_cabecera(self):
        assert ESO_XTEC.curso_de_saberes("Sentit numèric") is None
        assert ESO_XTEC.curso_de_saberes("A. Escolta i percepció musical") is None


@pytest.mark.skipif(not BATX.exists(), reason=f"no está {BATX}")
class TestElBachilleratoCatalanCompleto:
    """Los 79 PDF de la XTEC, leídos enteros."""

    @pytest.fixture(scope="class")
    def todo(self):
        bloques = []
        for pdf in sorted(BATX.glob("*.pdf")):
            for mc in extraer(pdf, etapa=BACHILLERATO):
                if not mc.cursos_aplicables:
                    mc.cursos_aplicables = list(
                        CURSOS_BACHILLERATO.get(mc.materia_oficial, [])
                    )
                bloques.append(mc)
        return bloques

    def test_todas_las_materias_tienen_cursos(self, todo):
        """Una materia sin cursos no da error: se carga, sale en el
        desplegable y no se ofrece en ninguna parte. Aquí no puede quedar
        ninguna porque la tabla se transcribió entera del DOIGC."""
        sin = sorted({b.materia_oficial for b in todo if not b.cursos_aplicables})

        assert sin == [], f"materias sin cursos: {sin}"

    def test_todas_tienen_competencias(self, todo):
        """El decreto de Bachillerato escribe «Competència 3» y el de la ESO
        «Competència específica 3». Con el patrón de la ESO a secas, las 79
        materias salían con cero competencias y los criterios colgando de una
        competencia «1» inventada."""
        sin = sorted({b.materia_oficial for b in todo if not b.competencias})

        assert sin == []

    def test_las_que_no_traen_criterios_son_las_que_el_decreto_deja_abiertas(self, todo):
        """No es un fallo de lectura: veintiuna optativas no llevan criterios
        ni saberes porque el propio currículo dice que los fija el centro
        —«El professorat establirà els criteris d'avaluació… i seleccionarà
        els sabers»—. Se fija la lista entera para que, si mañana una materia
        con currículo completo se queda sin criterios, salte aquí.
        """
        sin = sorted({b.materia_oficial for b in todo if not b.criterios})

        assert sin == [
            "Biomedicina",
            "Ciutadania, Política i Dret",
            "Comunicació Audiovisual",
            "Creació Fotogràfica i Cinema",
            "Creació Literària",
            "Disseny 2D i 3D",
            "Formació i Orientació Personal i Professional",
            "Funcionament de l’Empresa",
            "Llenguatges Artístics Contemporanis",
            "Matemàtica Aplicada",
            "Món Clàssic",
            "Música i Comunicació",
            "Objectius de Desenvolupament Sostenible (ODS)",
            "Problemàtiques Socials",
            "Programació",
            "Projecte de Comissariat d’Exposicions",
            "Psicologia",
            "Publicitat",
            "Reptes Científics Actuals (Biologia i Geologia)",
            "Reptes Científics Actuals (Física i Química)",
            "Robòtica",
            "Taller de Creació Escènica",
        ], f"lista distinta: {sin}"

    def test_las_de_dos_cursos_no_comparten_saberes(self, todo):
        """En Bachillerato el epígrafe «Sabers» de las materias de dos cursos
        viene partido en «Primer curs» y «Segon curs». Sin reconocerlo, 1.º se
        cargaba con los saberes de 2.º además de los suyos, sin dar error.

        Se indexa por (materia, cursos) y no por materia a secas porque seis
        materias vienen **dos veces**, una por cada sección del portal en que
        se ofertan, con el mismo curso: comparar esas dos copias daría un falso
        positivo, ya que son el mismo fichero.
        """
        por_materia: dict[str, dict[tuple[str, ...], set[str]]] = {}
        for mc in todo:
            por_materia.setdefault(mc.materia_oficial, {})[
                tuple(mc.cursos_aplicables)
            ] = {i for b in mc.saberes for i in b.items}

        iguales = [m for m, tramos in por_materia.items()
                   if len(tramos) == 2 and all(tramos.values())
                   and len(set(map(frozenset, tramos.values()))) == 1]

        assert iguales == [], f"los dos cursos traen lo mismo: {iguales}"

    def test_los_parentesis_del_titulo_no_se_recortan(self, todo):
        """En la ESO el paréntesis del título es una coletilla de curso y se
        quita. En Bachillerato es parte del nombre: recortarlo fundiría las dos
        «Reptes Científics Actuals» en una y la segunda pisaría a la primera.
        """
        nombres = {b.materia_oficial for b in todo}

        assert "Reptes Científics Actuals (Biologia i Geologia)" in nombres
        assert "Reptes Científics Actuals (Física i Química)" in nombres

    def test_los_titulos_no_son_frases_del_cuerpo(self, todo):
        """PyMuPDF da a una línea el tamaño de su fragmento más grande, y en
        seis párrafos de «Biologia, Geologia i Ciències Ambientals» el punto
        final viene un punto mayor que el resto. Tomando «todas las líneas del
        tamaño mayor», esas seis frases se cargaban como materias."""
        largos = sorted(n for n in {b.materia_oficial for b in todo} if len(n) > 50)

        assert largos == [
            "Dibuix Tècnic Aplicat a les Arts Plàstiques i el Disseny",
            "Funcionament de l’Empresa i Disseny de Models de Negoci",
        ]

    @pytest.mark.parametrize("etapa, carpeta", [
        (BACHILLERATO, BATX),
        (ESO_XTEC, XTEC),
    ])
    def test_salen_exactamente_los_criterios_que_hay_en_el_pdf(self, etapa, carpeta):
        """Igualdad, PDF a PDF. Ver `_codigos_de_criterio`.

        Se cuenta por tramo distinto y no por bloque: un PDF con varias
        materias repite los mismos criterios una vez por materia.
        """
        if not carpeta.exists():
            pytest.skip(f"no está {carpeta}")

        descuadres = []
        for pdf in sorted(carpeta.glob("*.pdf")):
            en_el_pdf = _codigos_de_criterio(pdf)
            vistos, extraidos = set(), 0
            for mc in extraer(pdf, etapa=etapa):
                cursos = tuple(mc.cursos_aplicables)
                if cursos in vistos:
                    continue
                vistos.add(cursos)
                extraidos += len(mc.criterios)
            if extraidos != en_el_pdf:
                descuadres.append((pdf.name, en_el_pdf, extraidos))

        assert descuadres == [], f"(fichero, en el PDF, extraídos): {descuadres}"

    @pytest.mark.parametrize("etapa, carpeta", [
        (BACHILLERATO, BATX),
        (ESO_XTEC, XTEC),
    ])
    def test_ningun_codigo_de_criterio_se_repite_dentro_de_un_tramo(self, etapa, carpeta):
        """Un código repetido dentro de (materia, cursos) es la firma de dos
        columnas fundidas: el decreto numera 1.1 en cada curso, no dos veces
        en el mismo.

        Importa porque el cargador hace *upsert* por esa clave: con el código
        repetido, el segundo criterio **actualiza la fila del primero** y el
        texto del primero se pierde. Así estuvieron 50 criterios catalanes
        desde el 14/08.
        """
        if not carpeta.exists():
            pytest.skip(f"no está {carpeta}")

        repetidos = []
        for pdf in sorted(carpeta.glob("*.pdf")):
            for mc in extraer(pdf, etapa=etapa):
                codigos = [c.codigo for c in mc.criterios]
                if len(codigos) != len(set(codigos)):
                    repetidos.append((mc.materia_oficial, mc.ciclo))

        assert repetidos == [], f"códigos repetidos en un tramo: {repetidos}"

    @pytest.mark.parametrize("etapa, carpeta", [
        (BACHILLERATO, BATX),
        (ESO_XTEC, XTEC),
    ])
    def test_no_hay_menos_saberes_que_guiones(self, etapa, carpeta):
        """La guarda del modo de fallo «sale poco, pero no cero».

        Se comprueba PDF a PDF, no en total: en el total, «Química» perdiendo
        32 saberes se compensaba con otras materias y no se notaba.
        """
        if not carpeta.exists():
            pytest.skip(f"no está {carpeta}")

        cortos = []
        for pdf in sorted(carpeta.glob("*.pdf")):
            guiones = _guiones_de_sabers(pdf)
            vistos, items = set(), 0
            for mc in extraer(pdf, etapa=etapa):
                cursos = tuple(mc.cursos_aplicables)
                if cursos in vistos:
                    # Un PDF con varias materias repite los mismos saberes.
                    continue
                vistos.add(cursos)
                items += sum(len(b.items) for b in mc.saberes)
            if items < guiones - 2:
                cortos.append((pdf.name, guiones, items))

        assert cortos == [], f"saberes perdidos: {cortos}"

    def test_la_edicion_anterior_de_llati_no_se_carga_aparte(self, todo):
        """El portal sirve «Llengua i Cultura Llatines» y «Llatí», que son el
        mismo currículo con el nombre que cambió el Decret 103/2026 —difieren
        en 276 caracteres, todos el nombre dentro del texto—. Cargar las dos
        daría dos materias para lo mismo, y por orden alfabético ganaría la
        vieja."""
        nombres = {b.materia_oficial for b in todo}

        assert "Llatí" in nombres
        assert "Llengua i Cultura Llatines" not in nombres
