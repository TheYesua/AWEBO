"""Tests del extractor del DOG (currículo gallego).

No tocan base de datos ni Flask. Se ejecutan contra los **PDF reales**, que no
están en el repositorio público: si no están, la clase se salta entera.

DÓNDE ESTUVO EL RIESGO EN ESTE EXTRACTOR
-----------------------------------------
En lo mismo que en los otros tres, y el patrón ya no sorprende: los fallos no
lanzan excepciones, producen **datos plausibles pero mal**. Los cinco que se
cometieron escribiéndolo:

1. La máquina de estados solo miraba tablas, y en varias materias **la cabecera
   de curso está fuera de una**. Lingua Castelá salía con 97 criterios en 1.º
   en vez de 23, y sin 2.º ni 3.º: los de esos cursos se acumulaban en el
   anterior.
2. Una línea suelta anterior al primer curso creaba un tramo vacío, y con eso
   la materia se daba por «sin curso» y se descartaba **entera**. Bioloxía e
   Xeoloxía tenía sus tres cursos bien leídos y no se guardaba ninguno.
3. `Matematicas.pdf` contiene **tres materias** —Matemáticas, A y B—, y todas
   se sumaban bajo el título de la portada: Matemáticas de 4.º salía con 73
   criterios en vez de 37.
4. El título de la portada se cogía por posición, y los ámbitos de
   diversificación lo llevan partido en dos líneas: se cargaban con el nombre
   «obrigatoria».
5. Siete materias aparecen en dos PDF —el completo y el del curso suelto—, y
   como el nombre del JSON sale de (materia, cursos), **el segundo pisaba al
   primero**. Se imprimían 67 bloques y quedaban 60 ficheros.

Por eso aquí se comprueban cantidades, reparto y unicidad, no que las funciones
devuelvan algo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.curriculo.extractor_dog import (
    CURSOS_DE_LA_GUIA,
    RX_CRITERIO,
    RX_OBXECTIVO,
    _juntar,
    _quitar_repetidas,
    _slug,
    extraer,
)


FUENTES = Path(__file__).resolve().parents[2].parent / "curriculo" / "fuentes" / "galicia"
BIOLOXIA = FUENTES / "Bioloxia-e-Xeoloxia.pdf"
MATEMATICAS = FUENTES / "Matematicas.pdf"
LINGUA = FUENTES / "Lingua-Castela-e-Literatura.pdf"
AMBITO = FUENTES / "Ambito-Cientifico-Tecnoloxico.pdf"


class TestPiezasSueltas:
    """Sin PDF."""

    def test_el_codigo_del_obxectivo_admite_el_espacio(self):
        """EL FALLO 6, que no está en la lista de arriba porque lo destapó un
        aviso del propio extractor y no una lectura: **el boletín no es
        constante**. En Física e Química los cuatro primeros obxectivos se
        escriben «OBX1.» y el quinto y el sexto «OBX 5.». Sin el espacio
        opcional, esa materia salía con cuatro y sus criterios citaban dos que
        no existían."""
        assert RX_OBXECTIVO.match("OBX1. Comprender e relacionar")
        assert RX_OBXECTIVO.match("OBX 5. Utilizar as estratexias")

    def test_el_criterio_admite_o_no_la_vineta(self):
        """La celda a veces la trae y a veces no, según cómo parta la fila."""
        assert RX_CRITERIO.match("▪ CA1.1. Analizar e explicar").group(3).startswith("Analizar")
        assert RX_CRITERIO.match("CA2.3. Describir a célula").group(1) == "2"

    def test_se_deshacen_los_guiones_de_division(self):
        """El PDF parte palabras al final de renglón y en algunos sitios usa un
        carácter de control donde va el guion. Sin deshacerlo, el currículo
        guardado dice «diferen tes»."""
        assert _juntar("utilizando diferen-\ntes formatos") == "utilizando diferentes formatos"
        # Se compara la cadena entera y no con `not in`: «perse» es subcadena
        # de «persegue», así que aquella comprobación fallaba con el resultado
        # correcto delante.
        assert _juntar("perse\x02gue impulsar") == "persegue impulsar"

    def test_de_dos_lecturas_de_lo_mismo_se_queda_la_completa(self):
        """EL FALLO 5. Siete materias salen en dos PDF y el JSON se llama igual
        para las dos, así que una pisaba a la otra sin decir nada."""
        from types import SimpleNamespace as NS

        def sa(n):
            return NS(materia_efectiva="Matemáticas A", cursos_aplicables=["4º ESO"],
                      saberes=[NS(items=list(range(n)))])

        assert len(_quitar_repetidas([sa(81), sa(179)])) == 1
        assert sum(len(b.items) for b in _quitar_repetidas([sa(81), sa(179)])[0].saberes) == 179


@pytest.mark.skipif(not BIOLOXIA.exists(), reason=f"no están los PDF en {FUENTES}")
class TestUnaMateriaDeVariosCursos:
    """Bioloxía e Xeoloxía: 1.º, 3.º y 4.º, con seis obxectivos comunes."""

    @pytest.fixture(scope="class")
    def bloques(self):
        return extraer(BIOLOXIA)

    def test_sale_un_bloque_por_curso(self, bloques):
        """EL FALLO 2: con un tramo vacío colado, esta materia no devolvía
        nada pese a estar bien leída."""
        cursos = sorted(b.cursos_aplicables[0] for b in bloques)

        assert cursos == ["1º ESO", "3º ESO", "4º ESO"]

    def test_los_obxectivos_son_los_mismos_en_los_tres(self, bloques):
        """Los OBX son de la materia, no del curso: lo que cambia entre cursos
        son los criterios y los contidos."""
        codigos = {tuple(c.codigo for c in b.competencias) for b in bloques}

        assert len(codigos) == 1
        assert len(next(iter(codigos))) == 6

    def test_cada_criterio_apunta_a_un_obxectivo_que_existe(self, bloques):
        """La relación va al revés que en las otras comunidades: aquí es el
        criterio quien nombra su OBX, en la segunda columna de la tabla. Si la
        inversión se leyera mal, la conexión curricular se rompería al generar
        y el fallo aparecería muy lejos de aquí."""
        for b in bloques:
            codigos = {c.codigo for c in b.competencias}
            for cr in b.criterios:
                assert cr.competencia in codigos, (
                    f"{b.materia_efectiva} {b.ciclo}: {cr.codigo} cita "
                    f"OBX{cr.competencia}, que no está en {sorted(codigos)}"
                )

    def test_los_contidos_llevan_el_numero_de_bloque_del_decreto(self, bloques):
        """Es la mitad oficial del código: los contidos no tienen número propio,
        pero el bloque sí lo tiene en la norma."""
        b = bloques[0]

        assert b.saberes[0].codigos_items[0] == "1.1"
        assert b.saberes[0].titulo == "Proxecto científico"

    def test_el_texto_llega_entero(self, bloques):
        """Los criterios vienen partidos por el ancho de la celda. Si no se
        vuelven a juntar, se guarda un trozo de frase."""
        crit = bloques[0].criterios[0]

        assert len(crit.descripcion) > 60
        assert crit.descripcion.endswith(".")


@pytest.mark.skipif(not MATEMATICAS.exists(), reason=f"no están los PDF en {FUENTES}")
class TestUnPdfConVariasMaterias:
    """EL FALLO 3, que es el que más datos estropeaba.

    `Matematicas.pdf` trae Matemáticas (1.º a 3.º), Matemáticas A y Matemáticas
    B, cada una con su «Materia de …». Sumándolas bajo el título de la portada,
    Matemáticas de 4.º salía con 73 criterios en vez de 37 y con los contidos
    de las tres mezclados."""

    @pytest.fixture(scope="class")
    def bloques(self):
        return extraer(MATEMATICAS)

    def test_se_reconocen_las_tres(self, bloques):
        assert {b.materia_efectiva for b in bloques} == {
            "Matemáticas", "Matemáticas A", "Matemáticas B",
        }

    def test_matematicas_no_se_lleva_los_criterios_de_a_y_b(self, bloques):
        """El síntoma que lo delató: un curso con el doble de criterios que
        sus hermanos."""
        por_curso = {
            b.cursos_aplicables[0]: len(b.criterios)
            for b in bloques if b.materia_efectiva == "Matemáticas"
        }

        assert sorted(por_curso) == ["1º ESO", "2º ESO", "3º ESO"]
        menor, mayor = min(por_curso.values()), max(por_curso.values())
        assert mayor <= menor * 1.5, f"reparto sospechoso: {por_curso}"


@pytest.mark.skipif(not LINGUA.exists(), reason=f"no están los PDF en {FUENTES}")
class TestLosCursosQueNoEstanEnUnaTabla:
    """EL FALLO 1. En Lingua Castelá las cabeceras de 2.º y 3.º están fuera de
    tabla, así que una máquina de estados que solo mire tablas se salta dos
    cursos y acumula sus criterios en el anterior."""

    def test_salen_los_cuatro_cursos(self):
        bloques = extraer(LINGUA)

        assert sorted(b.cursos_aplicables[0] for b in bloques) == [
            "1º ESO", "2º ESO", "3º ESO", "4º ESO",
        ]

    def test_ningun_curso_acapara_los_criterios_de_otro(self):
        cuentas = [len(b.criterios) for b in extraer(LINGUA)]

        assert max(cuentas) <= min(cuentas) * 2, f"reparto sospechoso: {cuentas}"


@pytest.mark.skipif(not AMBITO.exists(), reason=f"no están los PDF en {FUENTES}")
class TestElTituloDeLaPortada:
    def test_el_nombre_partido_en_dos_lineas_se_junta(self):
        """EL FALLO 4: «Ámbito Científico e» + «Tecnolóxico» en dos renglones.
        Cogiendo la línea por posición salía «obrigatoria» como nombre de la
        materia, y así se cargaba."""
        bloques = extraer(AMBITO)

        nombres = {b.materia_efectiva for b in bloques}
        assert nombres, "el ámbito no devolvió nada"
        assert "obrigatoria" not in nombres
        assert all("Ámbito" in n for n in nombres), nombres


@pytest.mark.skipif(not FUENTES.exists() or not list(FUENTES.glob("*.pdf")),
                    reason=f"no están los PDF en {FUENTES}")
class TestLosTreintaYCinco:
    """El conjunto, que es donde se ven los repartos raros."""

    @pytest.fixture(scope="class")
    def todo(self):
        salida = []
        for pdf in sorted(FUENTES.glob("*.pdf")):
            salida.extend(extraer(pdf))
        return _quitar_repetidas(salida)

    def test_no_hay_dos_entradas_para_la_misma_materia_y_curso(self, todo):
        """Si las hubiera, una pisaría a la otra al volcar el JSON — y el
        recuento seguiría diciendo que están las dos."""
        claves = [(b.materia_efectiva, tuple(b.cursos_aplicables)) for b in todo]

        assert len(claves) == len(set(claves))

    def test_ninguna_sale_a_medias(self, todo):
        cojas = [
            (b.materia_efectiva, b.ciclo)
            for b in todo
            if not b.competencias or not b.criterios or not b.saberes
        ]

        assert cojas == []

    def test_todas_tienen_cursos(self, todo):
        """Una materia sin cursos se carga y queda invisible: no sale en el
        desplegable ni en el contexto del modelo. Es lo que le pasó a Robòtica
        i Programació en Cataluña durante dos días."""
        sin_cursos = [b.materia_efectiva for b in todo if not b.cursos_aplicables]

        assert sin_cursos == []

    def test_los_nombres_de_fichero_no_colisionan(self, todo):
        """El JSON se llama `<slug>__<cursos>.json`. Dos materias distintas con
        el mismo slug se pisarían igual que las repetidas."""
        def nombre(b) -> str:
            # La f-string no puede llevar la barra invertida del patrón, así
            # que el dígito se saca fuera. Es la misma composición que `volcar`.
            digitos = "_".join(re.findall(r"(\d)", " ".join(b.cursos_aplicables)))
            return f"{_slug(b.materia_efectiva)}__{digitos}"

        nombres = [nombre(b) for b in todo]

        assert len(nombres) == len(set(nombres))

    def test_las_excepciones_de_curso_siguen_haciendo_falta(self, todo):
        """`CURSOS_DE_LA_GUIA` existe para las materias cuyo PDF no dice el
        curso. Si alguna dejara de necesitarlo —porque la Xunta reeditara el
        PDF— la excepción sobraría y conviene enterarse."""
        con_cursos = {b.materia_efectiva for b in todo}

        for materia in CURSOS_DE_LA_GUIA:
            assert materia in con_cursos, (
                f"{materia} ya no se extrae: ¿sigue haciendo falta su entrada?"
            )


# ---------------------------------------------------------------------------
# El contraste que faltaba
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _trozos(texto: str, fuente: str) -> int:
    """En cuántos pedazos **seguidos** de la fuente se puede cubrir `texto`.

    Uno es lo normal. Dos, cuando el texto salta de página y los dos lados
    quedan lejos en la linealización. Tres o más significa que en medio hay
    algo que en el PDF no está: una palabra comida por el borde de una celda, o
    una cabecera colada dentro de la frase.

    Es el mismo contraste que destapó los 122 criterios mutilados de Andalucía.
    Allí hizo falta además una segunda linealización por columnas, porque el
    BOJA maqueta en tablas de cinco y el orden de lectura de PyMuPDF entrelaza
    las celdas vecinas. **Aquí no**: medido sobre los 35 PDF, con la
    linealización por líneas sola ya salen todos los criterios de una pieza, y
    añadir la de columnas no cambia ni un número. La Guía LOMLOE gallega usa
    tablas de dos columnas anchas y no se entrelazan.
    """
    trozos, i = 0, 0
    while i < len(texto):
        bajo, alto = 0, len(texto) - i
        while bajo < alto:
            medio = (bajo + alto + 1) // 2
            if texto[i:i + medio] in fuente:
                bajo = medio
            else:
                alto = medio - 1
        trozos += 1
        i += max(bajo, 1)
    return trozos


@pytest.mark.skipif(not FUENTES.exists() or not BIOLOXIA.exists(),
                    reason=f"no están los PDF en {FUENTES}")
class TestCadaPdfContraLoQueSeExtraeDeEl:
    """EL ANCLAJE QUE FALTABA, Y POR QUÉ TARDÓ EN LLEGAR.

    A Cataluña y a Andalucía las auditó la misma comprobación: contar en la
    fuente las líneas que **empiezan por código de criterio** y exigir que
    salgan todas. Encontró 89 criterios catalanes perdidos y 122 andaluces
    mutilados. En Galicia no se podía aplicar tal cual —sus criterios van
    dentro de celdas y la línea no empieza por el código—, y el cabo se quedó
    abierto en la hoja de ruta con la etiqueta de «hace falta otro anclaje».

    El anclaje resultó ser más simple de lo que parecía: **el código está, solo
    que no al principio de la línea**. `CA1.1`, `CA1.2`… se buscan en el texto
    con `\\bCA\\d+\\.\\d+\\b` sin exigirles posición, y eso da el conjunto que
    el PDF promete. Comparado con el que sale del extractor, no falta ninguno.

    Se comprueba **PDF a PDF y no en total**, que es lo que enseñó el LEEME de
    la fuente: siete materias aparecen en dos ficheros —el currículo completo y
    el del curso suelto— y los totales no cuadran por eso, no por una pérdida.
    Sumando se perdía un 11 % aparente que no existía.
    """

    @pytest.fixture(scope="class")
    def lectura(self):
        """Una sola pasada por los 35 PDF: extraer cuesta cuarenta segundos.

        Devuelve, por fichero, lo extraído y su texto normalizado, que es
        contra lo que se contrasta.
        """
        import pymupdf

        from app.curriculo.extractor_dog import RX_PIE

        salida = []
        for pdf in sorted(FUENTES.glob("*.pdf")):
            doc = pymupdf.open(pdf)
            crudo = " ".join(
                l.strip() for p in doc for l in p.get_text().splitlines()
                if l.strip() and not RX_PIE.match(l.strip())
            )
            salida.append((pdf.name, extraer(pdf), _norm(crudo),
                           set(re.findall(r"\bCA(\d{1,2}\.\d{1,2})\b", crudo))))
        assert len(salida) == 35, f"faltan PDF: hay {len(salida)}"
        return salida

    def test_sale_de_cada_pdf_todo_codigo_de_criterio_que_lleva(self, lectura):
        """Cero, y aquí sí se puede exigir cero: el código es del decreto y no
        hay forma de que sobre ni falte uno por maquetación."""
        fallos = []
        for nombre, bloques, _, del_pdf in lectura:
            extraidos = {c.codigo for b in bloques for c in b.criterios}
            if del_pdf - extraidos:
                fallos.append((nombre, sorted(del_pdf - extraidos)[:8]))

        assert fallos == [], f"{len(fallos)} PDF pierden criterios: {fallos[:3]}"

    def test_no_se_inventa_ningun_codigo_que_el_pdf_no_tenga(self, lectura):
        """El reverso, que no es simétrico ni redundante: un código de más
        significa que el extractor ha leído como criterio algo que no lo es, y
        eso llega al docente como un criterio inexistente que podría citar en
        una programación oficial."""
        fallos = []
        for nombre, bloques, _, del_pdf in lectura:
            extraidos = {c.codigo for b in bloques for c in b.criterios}
            if extraidos - del_pdf:
                fallos.append((nombre, sorted(extraidos - del_pdf)[:8]))

        assert fallos == [], f"{len(fallos)} PDF inventan criterios: {fallos[:3]}"

    def test_los_criterios_estan_literalmente_en_su_pdf(self, lectura):
        """LA OTRA MITAD, y la que nunca se había mirado. Que los códigos
        salgan todos no dice nada del **texto**: en Andalucía los 122 criterios
        mutilados tenían su código, su competencia y su curso correctos, y
        media frase de menos.

        Aquí sale cero de 1776. Se deja como cero y no como cota: si algún día
        sube, es una regresión, no deuda conocida.
        """
        rotos = [
            (nombre, b.materia_efectiva, b.ciclo, c.codigo)
            for nombre, bloques, fuente, _ in lectura
            for b in bloques for c in b.criterios
            if _trozos(_norm(c.descripcion), fuente) > 2
        ]

        assert rotos == [], f"{len(rotos)} criterios no salen de una pieza: {rotos[:6]}"

    def test_los_contidos_estan_literalmente_en_su_pdf(self, lectura):
        """Y los contidos, que son la otra mitad de lo que lee el docente.

        En Andalucía este fue el fallo gordo y el último en verse: el último
        saber de cada materia se tragaba la introducción de la siguiente, 59 de
        957 pasaban de 400 caracteres y el peor tenía 4238. Aquí no pasa, y no
        por suerte: la Guía LOMLOE da **un PDF por materia**, así que no hay
        materia siguiente de la que contagiarse.
        """
        rotos = [
            (nombre, b.materia_efectiva, b.ciclo, bl.codigo)
            for nombre, bloques, fuente, _ in lectura
            for b in bloques for bl in b.saberes for item in bl.items
            if _trozos(_norm(item), fuente) > 2
        ]

        assert rotos == [], f"{len(rotos)} contidos no salen de una pieza: {rotos[:6]}"

    def test_ningun_contido_tiene_tamano_de_parrafo_ajeno(self, lectura):
        """La longitud ve lo que los trozos no: texto **pegado** que sí está en
        el PDF, solo que en otra sección. Es lo que distinguió en Andalucía un
        saber de 4238 caracteres de uno legítimamente largo.

        El máximo gallego es 778 y es del decreto: las «funcións comunicativas»
        de Lingua Estranxeira son una enumeración larga de verdad. La mediana
        son 90 caracteres y solo 15 de 5312 pasan de 400.
        """
        largos = sorted(
            (len(item), b.materia_efectiva, b.ciclo, bl.codigo)
            for _, bloques, _, _ in lectura
            for b in bloques for bl in b.saberes for item in bl.items
        )

        assert largos[-1][0] <= 800, f"contido de {largos[-1][0]} caracteres: {largos[-1][1:]}"
        pasados = [l for l in largos if l[0] > 400]
        assert len(pasados) <= 15, f"{len(pasados)} contidos pasan de 400 caracteres"
