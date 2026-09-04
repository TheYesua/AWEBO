"""Extractor del currículo catalán a partir de los PDF por materia de la XTEC.

POR QUÉ ES UN MÓDULO APARTE Y NO UN `Perfil` MÁS
-------------------------------------------------
`extractor.py` es una máquina de estados sobre una secuencia de ``(clase,
texto)``: el documento se lee en orden y cada párrafo se interpreta según lo
que vino antes. Eso funciona con el BOE porque el BOE es una columna de texto.

Aquí no se puede. Los criterios de evaluación vienen en una **tabla de dos
columnas** —una por grupo de cursos— y leídos en orden de lectura las dos
columnas se entrelazan: sale el criterio 1.1 de 1.º, luego el 1.1 de 4.º, luego
la segunda línea del de 1.º… Sin mirar la posición horizontal, el resultado no
es un texto peor: es un texto **mezclado entre dos currículos distintos**.

Por eso la abstracción `Perfil` no llega hasta aquí, y forzarla habría sido
peor que no tenerla: el `lector` de `Perfil` devuelve texto plano por diseño, y
lo que hace falta conservar es justo lo que ese diseño tira.

DE DÓNDE SALEN LOS FICHEROS, Y POR QUÉ NO DEL BOLETÍN
------------------------------------------------------
De ``curriculo/fuentes/cataluna/xtec/``, un PDF por materia. El boletín
completo del DOGC también trae los anexos, pero con la codificación de fuente
rota: pierde o sustituye una `v`, una `ç` o una `ò` en cientos de sitios, y los
casos en minúscula (`pròpies` → `przpies`) no se pueden ni detectar. Ver
``curriculo/fuentes/cataluna/dogc/LEEME.md``.

LO QUE ESTE FORMATO TIENE DE MEJOR QUE EL BOE
----------------------------------------------
El reparto por cursos viene **explícito criterio a criterio**, en la cabecera
de cada columna («1r, 2n i 3r» / «4t»). En el BOE hay que deducirlo de los
artículos de la parte dispositiva y cruzarlo con el nombre de la materia.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .extractor import (
    BloqueSaberes,
    CompetenciaEspecifica,
    Criterio,
    MateriaCiclo,
    retirar_huerfanos,
)
from .xtec_etapas import ESO, ETAPAS, EtapaXTEC


logger = logging.getLogger("curriculo.extractor_xtec")


# ---------------------------------------------------------------------------
# Reconocimiento
# ---------------------------------------------------------------------------

#: «Competència específica 3» en la ESO, «Competència 3» en Bachillerato. Los
#: dos decretos son de la misma casa y no llaman igual al mismo epígrafe: con
#: la forma larga sola, las 79 materias de Bachillerato salían con **cero
#: competencias** y los criterios colgados de una competencia «1» inventada.
RX_COMPETENCIA = re.compile(r"^Compet[èe]ncia(?:\s+espec[íi]fica)?\s+(\d+)\s*$")

#: «Criteris d'avaluació», con apóstrofo tipográfico o recto.
#:
#: Y **con la `d'` opcional**, porque en la competencia 6 de Física i Química
#: el decreto escribe «Criteris avaluació», sin ella. No es una errata que se
#: pueda ignorar: sin este epígrafe, el extractor no ve la tabla que viene
#: debajo y esa competencia se queda con cero criterios. Cuatro criterios
#: perdidos, dos por curso, y ningún error.
RX_CRITERIOS = re.compile(r"^Criteris\s+(?:d[’']\s*)?avaluaci[óo]\s*$")

RX_SABERES = re.compile(r"^Sabers\s*$")

#: «1.1 Interpretar problemes…» o «1.1. Analitzar conceptes…». El punto final
#: del código es opcional porque **los PDF no se ponen de acuerdo**: Matemàtiques
#: escribe «1.1 » y Cultura Científica «1.1. ». Sin el punto opcional, la
#: segunda no casaba ni un criterio y la materia salía con cero, sin dar error.
RX_CRITERIO = re.compile(r"^(\d+)\.(\d+)\.?\s+(.*)$")

#: Cabecera de columna de la ESO: «1r i 2n», «1r, 2n i 3r», «4t», «3r i 4t».
#: La de Bachillerato es distinta —«1r curs»— y vive en `xtec_etapas`; esta se
#: conserva como nombre público porque es lo que importan los tests.
RX_CABECERA_CURSOS = ESO.rx_cabecera_cursos

#: Pie de página que se repite en todas las páginas y no es contenido. También
#: depende de la etapa: cita el decreto, y son dos decretos distintos.
RX_PIE = ESO.rx_pie

#: «(matèria optativa de quart d'ESO)» en el título: dice el curso cuando no
#: hay tabla de dos columnas que lo diga. **Solo de la ESO**: en Bachillerato
#: ningún título lleva el curso dentro.
RX_OPTATIVA_CURSO = re.compile(
    r"optativa de\s+(primer|segon|tercer|quart)(?:\s+a\s+(primer|segon|tercer|quart))?", re.I
)
_ORDINAL_LARGO = {"primer": 1, "segon": 2, "tercer": 3, "quart": 4}


#: El curso que el título lleva pegado al final, **sin la palabra «optativa»**:
#: «Educació Plàstica, Visual i Audiovisual de primer a tercer», «Expressió
#: Artística de quart».
RX_CURSO_EN_EL_TITULO = re.compile(
    r"\bde\s+(primer|segon|tercer|quart)(?:\s+a\s+(primer|segon|tercer|quart))?"
    r"\s*$", re.I
)


def _cursos_del_titulo_propio(titulo: str) -> list[str] | None:
    """Los cursos que declara **ese** título, no los de la portada entera.

    PARA QUÉ HACE FALTA, HABIENDO YA `_cursos_del_titulo`. Aquel lee la portada
    como un bloque y sirve para las optativas, que solo cubren un tramo. Este
    hace falta cuando **un PDF trae dos materias que van a cursos distintos**:
    «Educació Plàstica, Visual i Audiovisual de primer a tercer» y «Expressió
    Artística de quart» comparten fichero y comparten competencias, pero cada
    una tiene su columna de criterios.

    Sin distinguirlas, las dos se llevaban las dos columnas: Expressió
    Artística, que es de 4.º, cargaba también los criterios de 1.º a 3.º.
    """
    m = RX_CURSO_EN_EL_TITULO.search(titulo)
    if not m:
        return None
    ini = _ORDINAL_LARGO[m.group(1).lower()]
    fin = _ORDINAL_LARGO[m.group(2).lower()] if m.group(2) else ini
    return [f"{n}º ESO" for n in range(ini, fin + 1)]


def _cursos_del_titulo(titulo: str) -> list[str] | None:
    """Cursos que declara el propio título, si es una optativa.

    Las optativas no traen tabla de dos columnas —su currículo es de un solo
    curso o tramo—, así que sin esto se quedarían sin cursos y el formulario
    las ofrecería en los cuatro.
    """
    m = RX_OPTATIVA_CURSO.search(titulo)
    if not m:
        return None
    ini = _ORDINAL_LARGO[m.group(1).lower()]
    fin = _ORDINAL_LARGO[m.group(2).lower()] if m.group(2) else ini
    return [f"{n}º ESO" for n in range(ini, fin + 1)]


# ---------------------------------------------------------------------------
# Lectura posicional
# ---------------------------------------------------------------------------


@dataclass
class Linea:
    """Una línea del PDF con lo que hace falta para saber qué papel juega."""

    pagina: int
    x: float
    y: float
    tam: float
    negrita: bool
    texto: str


def leer_lineas(pdf: Path, etapa: EtapaXTEC = ESO) -> list[Linea]:
    """Todas las líneas del PDF, en orden de lectura, con su posición.

    Se conserva ``x`` porque es lo único que distingue la columna de 1.º de la
    de 4.º, y ``tam``/``negrita`` porque es lo único que distingue un título de
    bloque de saberes de un item.
    """
    doc = pymupdf.open(pdf)
    lineas: list[Linea] = []
    for n, pagina in enumerate(doc, start=1):
        for bloque in pagina.get_text("dict")["blocks"]:
            for linea in bloque.get("lines", []):
                spans = linea["spans"]
                texto = "".join(s["text"] for s in spans).strip()
                if not texto or etapa.rx_pie.match(texto):
                    continue
                lineas.append(
                    Linea(
                        pagina=n,
                        x=linea["bbox"][0],
                        y=linea["bbox"][1],
                        tam=max(s["size"] for s in spans),
                        negrita=any("Bold" in s["font"] for s in spans),
                        texto=texto,
                    )
                )
    return lineas


def titulos_de(lineas: list[Linea], etapa: EtapaXTEC = ESO,
               limpiar: bool = True) -> list[str]:
    """Las materias que cubre el PDF.

    Normalmente una. Pero el bloque lingüístico catalán publica **tres materias
    con un solo currículo compartido** —Aranès, Llengua Castellana y Llengua
    Catalana— en un mismo fichero y con tres títulos en la portada. Devolver
    solo el primero habría dejado dos materias enteras sin currículo, y sin dar
    ningún error: simplemente no aparecerían en el desplegable.

    NO VALE «TODAS LAS LÍNEAS DEL TAMAÑO MAYOR», que es lo que hacía antes.
    PyMuPDF da como tamaño de una línea el mayor de sus fragmentos, y en los
    PDF de Bachillerato **el punto final de algunos párrafos viene un punto más
    grande que el resto**: seis frases sueltas de la introducción de «Biologia,
    Geologia i Ciències Ambientals» se colaban como si fueran materias, y se
    cargaban como tales, con el currículo entero repetido debajo de cada una.

    El título es la **primera tanda** de líneas grandes de la portada: en
    cuanto aparece una línea normal, lo que venga después es cuerpo.
    """
    de_portada = [l for l in lineas if l.pagina == 1]
    if not de_portada:
        return []
    mayor = max(l.tam for l in de_portada)
    crudos: list[str] = []
    for l in de_portada:
        if l.tam >= mayor - 0.1:
            if len(l.texto) > 3:
                crudos.append(l.texto)
        elif crudos:
            break
    # `limpiar=False` devuelve el título tal cual viene en la portada. Lo pide
    # `extraer` porque la coletilla que aquí se quita —«de primer a tercer»—
    # es lo único que dice a qué columna de criterios pertenece cada materia
    # cuando el PDF trae dos.
    return [_limpiar_titulo(t, etapa) if limpiar else t for t in crudos]


def _limpiar_titulo(titulo: str, etapa: EtapaXTEC = ESO) -> str:
    """Quita del título lo que dice el curso, que no es parte del nombre.

    «Cultura Científica (matèria optativa de quart d'ESO)» y «Educació
    Plàstica, Visual i Audiovisual de primer a tercer» son la misma materia con
    y sin coletilla. Si la coletilla se queda dentro, la materia guardada no
    coincide con la que lista el articulado y el desplegable ofrece dos
    entradas para lo mismo.

    EN BACHILLERATO EL PARÉNTESIS SÍ ES PARTE DEL NOMBRE, y por eso la limpieza
    es opcional: «Reptes Científics Actuals (Biologia i Geologia)» y «Reptes
    Científics Actuals (Física i Química)» son **dos materias distintas** con
    currículos distintos, y recortarlas por el paréntesis las fundiría en una
    —la segunda pisando a la primera— sin dar ningún error.
    """
    if not etapa.limpiar_coletilla_de_curso:
        return titulo.strip(" .,")
    limpio = re.sub(r"\s*\(.*", "", titulo)
    limpio = re.sub(
        r"\s+(?:de|d[’'])\s+(?:primer|segon|tercer|quart)\b.*$", "", limpio, flags=re.I
    )
    return limpio.strip(" .,")


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------


@dataclass
class _Columna:
    cursos: list[str]
    x_min: float
    x_max: float
    criterios: list[Criterio] = field(default_factory=list)


def _agrupar_criterios(lineas: list[Linea], competencia: str,
                       etapa: EtapaXTEC = ESO) -> list[_Columna]:
    """Los criterios de una competencia, repartidos por columna.

    ``lineas`` va desde la cabecera de columnas hasta el final del bloque.

    El reparto se hace por **cercanía al inicio de cada columna**, no por un
    punto medio fijo: las tablas no están siempre en el mismo sitio y una
    materia sin tabla tiene una sola columna que ocupa todo el ancho.
    """
    cabeceras = [l for l in lineas if etapa.rx_cabecera_cursos.match(l.texto)]
    if not cabeceras:
        return []

    # Las de la primera fila: las que comparten página y `y` con la primera.
    pagina0, y0 = cabeceras[0].pagina, cabeceras[0].y
    cabeceras = [c for c in cabeceras
                 if c.pagina == pagina0 and abs(c.y - y0) < 5]
    cabeceras.sort(key=lambda c: c.x)

    columnas = [_Columna(cursos=etapa.cursos_de_cabecera(c.texto), x_min=c.x, x_max=0)
                for c in cabeceras]

    # LA `y` SOLA NO ORDENA UN DOCUMENTO DE VARIAS PÁGINAS, y aquí estaba
    # comparándose como si sí. Una tabla que empieza al pie de una página y
    # sigue en la siguiente tiene su continuación con una `y` **pequeña**, así
    # que `l.y > y0 + 5` la descartaba entera. Educació Plàstica perdía 2
    # criterios de cada columna por eso, y el síntoma era el de siempre:
    # ninguno.
    cuerpo = [l for l in lineas if (l.pagina, l.y) > (pagina0, y0 + 5)]
    if not cuerpo:
        return columnas

    # FRONTERAS, NO DISTANCIAS
    # ------------------------
    # La cabecera está **centrada** sobre su columna y el texto **alineado a la
    # izquierda**: en Matemàtiques las cabeceras caen en x=173 y x=413, y el
    # texto en x=91 y x=313. Comparar la x del texto con la de su cabecera da
    # el resultado equivocado, y no de forma escandalosa: manda toda la segunda
    # columna a la primera, y la segunda se queda con cero criterios. Un curso
    # entero sin currículo y ningún error.
    #
    # La frontera entre dos columnas es el punto medio entre sus cabeceras.
    fronteras = [(columnas[i].x_min + columnas[i + 1].x_min) / 2
                 for i in range(len(columnas) - 1)]

    def columna_de(l: Linea) -> _Columna:
        for i, frontera in enumerate(fronteras):
            if l.x < frontera:
                return columnas[i]
        return columnas[-1]

    actual: dict[int, Criterio] = {}
    for l in cuerpo:
        col = columna_de(l)
        i = columnas.index(col)
        m = RX_CRITERIO.match(l.texto)
        if m:
            crit = Criterio(
                codigo=f"{m.group(1)}.{m.group(2)}",
                competencia=competencia,
                descripcion=m.group(3).strip(),
            )
            col.criterios.append(crit)
            actual[i] = crit
        elif i in actual:
            # Continuación de un criterio partido en varias líneas.
            actual[i].descripcion = f"{actual[i].descripcion} {l.texto}".strip()
    return columnas


def _es_vineta(texto: str) -> bool:
    """Una línea que solo contiene la marca de una viñeta, no contenido.

    Se mira carácter a carácter en vez de con una lista cerrada porque cada PDF
    trae la suya, y varias vienen del área de uso privado de Unicode (U+E000 a
    U+F8FF), donde el carácter no significa nada fuera de su fuente.

    OJO A LO QUE **NO** HACE: esto descarta la línea que es *solo* la marca.
    Cuando la marca comparte renglón con el texto —«● Context»— la línea no se
    descarta y la marca se queda pegada. Para eso está `_sin_marca`.
    """
    return all(c in "-–—−·•*" or "\ue000" <= c <= "\uf8ff" or c.isspace()
               for c in texto)


#: Viñeta al principio de una línea que **también** trae texto. Así acabaron
#: **146 de los 384** bloques catalanes: «Comunicació · ● Context». No es un
#: fallo de lectura sino basura tipográfica, pero llega hasta el documento que
#: lee el docente y hasta el listado que se le pasa al modelo.
_RX_MARCA_INICIAL = re.compile("^[\\s\\-–—−·•*●○▪◦-]+")


def _sin_marca(texto: str) -> str:
    """Quita la viñeta inicial y normaliza los espacios de dentro.

    Los espacios múltiples vienen del mismo sitio: «●   Context» deja tres al
    retirar la marca.
    """
    return re.sub(r"\s{2,}", " ", _RX_MARCA_INICIAL.sub("", texto)).strip()


def _extraer_saberes(lineas: list[Linea]) -> list[BloqueSaberes]:
    """Los saberes, que vienen en **dos o tres** niveles de sangrado.

    Matemàtiques y otras seis usan tres:

        Sentit de la mesura        x≈85, negrita   bloque
          Magnitud                 x≈103           subbloque
            - Atributs mesurables  x≈120           item

    Las otras diecisiete usan dos, sin subbloque:

        Bloc 1. La cèl·lula        x≈85, negrita   bloque
          - La teoria cel·lular    x≈103           item

    LA VERSIÓN ANTERIOR DABA POR HECHO QUE SIEMPRE ERAN TRES, y con dos
    clasificaba el x≈103 como subbloque: cada línea de contenido creaba un
    subbloque vacío y **ningún item caía en ninguno**. Diecisiete materias con
    cero saberes, cargadas en la base de datos sin dar ningún error.

    Y no se detectó antes porque el arreglo se comprobó en Matemàtiques, que es
    justo la que tiene tres niveles: el caso que ya funcionaba.

    Y LOS NIVELES SE CUENTAN POR BLOQUE, NO POR DOCUMENTO. Esa es la tercera
    versión, y la puso «Segona Llengua Estrangera»: ahí el bloque
    «Comunicació» usa tres niveles y los otros cuatro usan dos, en el mismo
    fichero. Contando los niveles de todo el documento salían tres, así que en
    los bloques de dos cada item se tomaba por un subbloque vacío y los cuatro
    bloques se perdían: catorce saberes en vez de treinta y tantos. El mismo
    fallo de siempre, ahora dentro de un solo PDF.
    """
    utiles = [l for l in lineas if not _es_vineta(l.texto)]
    if not utiles:
        return []

    def _agrupar(xs) -> list[int]:
        """Los `x` se agrupan, no se listan.

        Dentro de un mismo nivel hay variaciones de dos o tres puntos —103 y
        106 son el mismo sangrado— y tomar «el tercer valor distinto» daba 106
        en Matemàtiques, con lo que el nivel de subbloque quedaba por encima
        del umbral y se perdía entero.
        """
        niveles: list[int] = []
        for x in sorted({round(v) for v in xs}):
            if not niveles or x - niveles[-1] > 6:
                niveles.append(x)
        return niveles

    margen = _agrupar(l.x for l in utiles)[0]

    # SIN SANGRADO, LA VIÑETA ES LO ÚNICO QUE QUEDA
    # ----------------------------------------------
    # En los PDF reeditados de Bachillerato todo va al mismo margen: título de
    # bloque e items comparten `x`, y lo único que los separa es que el item
    # empieza por guion. Encima la negrita está mal aplicada —se derrama sobre
    # la primera línea de cada bloque y sobre alguna frase suelta de la
    # introducción—, así que con la negrita a secas «- Descripció i anàlisi de
    # les diferents fases del mètode científic» se cargaba como **título de
    # bloque** y su propio texto quedaba de item.
    #
    # Cuando se da ese caso, y solo entonces, la viñeta manda: lo que empieza
    # por ella es item pase lo que pase, y lo que no empieza por ella y no
    # continúa a un item anterior no es nada. En la ESO no se activa, y hace
    # falta que no se active: allí hay títulos de bloque que **sí** empiezan
    # por viñeta —«● Context»— y los sangrados distinguen los niveles.
    def _con_vineta(texto: str) -> bool:
        m = _RX_MARCA_INICIAL.match(texto)
        return bool(m) and m.group(0).strip() != ""

    #: EL GUION ES DEL ITEM; LAS DEMÁS VIÑETAS, NO. Los PDF usan dos marcas a la
    #: vez y no significan lo mismo: en «Química» el subbloque lleva «•» y el
    #: saber «-», y en «Educació Física» el subbloque lleva «●» y el guion de
    #: cada saber va en su propia línea. En las dos, la marca de item es el
    #: guion. Distinguirlas es lo que permite leer «Química», que reparte los
    #: niveles al revés que las demás: el subbloque **sangrado** y el saber al
    #: margen. Sin esto se cargaban sus doce subbloques como si fueran los
    #: saberes, y los sesenta saberes de verdad se perdían.
    def _con_guion(texto: str) -> bool:
        return bool(re.match(r"^[-–—−]\s+\S", texto))

    hay_sangrado = len(_agrupar(l.x for l in utiles)) > 1
    estricto = not hay_sangrado and sum(_con_vineta(l.texto) for l in utiles) >= 3

    def es_titulo_de_bloque(l: Linea) -> bool:
        return (l.x <= margen + 6 and l.negrita
                and not (estricto and _con_vineta(l.texto)))

    bloques: list[BloqueSaberes] = []

    def abrir(nombre: str) -> BloqueSaberes:
        # EL CÓDIGO ES NUESTRO, NO DEL DECRETO. Conviene tenerlo claro porque
        # durante días se trató como si fuera oficial.
        #
        # El Decret 175/2022 **no numera** sus bloques de saberes: los nombra.
        # Se comprobó en los 24 PDF de la XTEC y ni uno lleva «Bloc N». Así que
        # este número es un índice de orden dentro de la materia, y `20.1` no
        # aparece en ningún boletín: no se puede citar en una programación ni
        # buscar en la norma.
        #
        # Se conserva porque hace falta **un** identificador para emparejar lo
        # que cita el modelo con la fila del catálogo, que es lo que detecta
        # los códigos inventados. Pero desde el 16/08 **no se enseña en el
        # documento exportado**: allí van el bloque y el texto del saber, que
        # es como el decreto lo identifica. Ver `filas_de_conexion`.
        #
        # Lo que sigue sin resolver: si el extractor mejora y encuentra un
        # bloque más en una materia, los códigos posteriores **de esa materia**
        # se desplazan. No es silencioso —el saber deja de casar y el documento
        # lo dice—, pero conviene recargar esa comunidad entera cuando pase.
        #
        # Numérico y no `chr(ord("A") + n)`: hay materias con más de 26
        # subbloques y eso se salía del alfabeto, dando códigos como "[".
        b = BloqueSaberes(codigo=str(len(bloques) + 1), titulo=nombre)
        bloques.append(b)
        return b

    def añadir(bloque: BloqueSaberes, l: Linea) -> None:
        # LA VIÑETA MANDA SOBRE LA MAYÚSCULA, y esto es lo segundo que cambia
        # en Bachillerato. En la ESO el guion de cada item va en su propia
        # línea a la izquierda —`_es_vineta` la descarta— y el texto empieza
        # sangrado y en mayúscula, así que la mayúscula basta para saber dónde
        # empieza uno.
        #
        # En los PDF que la XTEC volvió a publicar en 2026 el guion va
        # **pegado al texto**, todo en el mismo renglón y al mismo margen:
        # «- Identificació i argumentació del desenvolupament…». Con la regla
        # de la mayúscula, ninguna línea empieza item y los cuatro o cinco de
        # cada bloque se fundían en uno solo, larguísimo: Física i Química se
        # cargaba con 9 saberes en vez de 19.
        vineta = _con_vineta(l.texto)
        texto = _sin_marca(l.texto)
        if not texto:
            return
        if estricto and not vineta and not bloque.items:
            # Prosa colada entre el título y el primer item, o bajo un título
            # que en realidad no lo era —de los que crea la negrita mal
            # aplicada—. No es un saber.
            return
        if bloque.items and not vineta and not re.match(r"^[A-ZÀ-Ú¡¿0-9]", texto):
            # Continuación del item anterior, partido por el ancho de la celda.
            bloque.items[-1] = f"{bloque.items[-1]} {texto}".strip()
        else:
            bloque.items.append(texto)

    # El documento se parte en bloques y **cada uno decide si tiene
    # subbloques**. Los items son siempre el nivel más profundo del bloque.
    #
    # QUÉ ES UN SUBBLOQUE Y QUÉ ES PROSA, que es lo único difícil de aquí. Un
    # subbloque o está sangrado más que el título del bloque —«Comptatge» a
    # x≈103 en Matemàtiques— o lleva viñeta —«● Esquema corporal» en Educació
    # Física, que además va **cuatro puntos a la izquierda** del título de su
    # bloque, así que por sangrado no se distingue de él—. Lo que no cumple
    # ninguna de las dos y no es item es la prosa introductoria del bloque, y
    # esa no es un saber.
    cortes = [i for i, l in enumerate(utiles) if es_titulo_de_bloque(l)]
    for n, ini in enumerate(cortes):
        fin = cortes[n + 1] if n + 1 < len(cortes) else len(utiles)
        titulo_bloque = _sin_marca(utiles[ini].texto).rstrip(".")
        cuerpo = utiles[ini + 1:fin]
        if not cuerpo:
            continue

        # El nivel de los items lo marca el guion cuando lo hay; si no, es el
        # más profundo del bloque.
        con_guion = [l for l in cuerpo if _con_guion(l.texto)]
        x_item = (_agrupar(l.x for l in con_guion)[0] if len(con_guion) >= 2
                  else _agrupar(l.x for l in cuerpo)[-1])

        def es_item(l: Linea) -> bool:
            return abs(l.x - x_item) <= 6

        def es_subbloque(l: Linea) -> bool:
            return (not es_item(l)
                    and (l.x > margen + 6 or _con_vineta(l.texto)))

        con_subbloques = any(es_subbloque(l) for l in cuerpo)
        actual = None if con_subbloques else abrir(titulo_bloque)
        for l in cuerpo:
            if es_item(l):
                if actual is not None:
                    añadir(actual, l)
            elif es_subbloque(l):
                sub = _sin_marca(l.texto).rstrip(".")
                actual = abrir(f"{titulo_bloque} · {sub}" if titulo_bloque else sub)
    return [b for b in bloques if b.items]


def _saberes_por_curso(
    lineas: list[Linea], etapa: EtapaXTEC
) -> dict[tuple[str, ...], list[BloqueSaberes]]:
    """Los saberes, repartidos por curso si el epígrafe viene partido.

    EL CASO QUE ESTO RESUELVE, Y POR QUÉ NO SE VE VENIR
    ----------------------------------------------------
    En la ESO el epígrafe «Sabers» es uno y vale para todos los cursos que
    cubra el PDF. En Bachillerato **no**: las 17 materias que duran dos cursos
    ponen dentro «Primer curs» y «Segon curs», en negrita y al mismo sangrado
    que los títulos de bloque, y debajo de cada uno los suyos.

    Leídos sin distinguir, los dos juegos salen en una sola lista y esa lista
    se guarda **entera en los dos tramos**: 1.º de Dibuix Tècnic recibiría los
    saberes de 2.º además de los suyos. El síntoma es ninguno —no falta nada,
    sobra—, y el error solo aparece cuando un docente ve en su curso un saber
    que no toca.

    Devuelve ``{(): [...]}`` cuando no hay partición, que es el caso de la ESO
    y el de las 62 materias de Bachillerato de un solo curso.
    """
    if etapa.rx_curso_saberes is None:
        return {(): _extraer_saberes(lineas)}

    # Índice de las cabeceras «Primer curs» / «Segon curs». Se exige negrita
    # porque la misma frase aparece en la prosa introductoria del epígrafe.
    cortes = [(i, etapa.curso_de_saberes(l.texto))
              for i, l in enumerate(lineas)
              if l.negrita and etapa.curso_de_saberes(l.texto)]
    if not cortes:
        return {(): _extraer_saberes(lineas)}

    por_curso: dict[tuple[str, ...], list[BloqueSaberes]] = {}
    for n, (idx, cursos) in enumerate(cortes):
        fin = cortes[n + 1][0] if n + 1 < len(cortes) else len(lineas)
        # Lo de antes del primer corte es la prosa introductoria del epígrafe,
        # que no es un saber de nadie: se queda fuera a propósito.
        por_curso[tuple(cursos)] = _extraer_saberes(lineas[idx + 1:fin])
    return por_curso


def extraer(pdf: Path, etiquetas: dict[str, str] | None = None,
            etapa: EtapaXTEC = ESO) -> list[MateriaCiclo]:
    """Devuelve un `MateriaCiclo` por cada (materia, grupo de cursos).

    :param etiquetas: nombre oficial -> etiqueta corta para la aplicación. Lo
        que no esté aquí conserva su nombre oficial.
    """
    etiquetas = etiquetas or {}
    lineas = leer_lineas(pdf, etapa)
    if not lineas:
        logger.error("PDF sin texto extraíble: %s", pdf)
        return []

    portada = " ".join(l.texto for l in lineas if l.pagina == 1)
    titulos = titulos_de(lineas, etapa)
    if not titulos:
        logger.error("No se encontró ningún título de materia en %s", pdf)
        return []

    # Ediciones anteriores que el portal sigue sirviendo: mismo currículo con
    # el nombre viejo. Se renombran aquí, no se descartan, para que el aviso
    # diga qué fichero era.
    # Se guardan los crudos en paralelo: el limpio es el nombre de la materia
    # y el crudo es el que dice a qué cursos va.
    crudos = titulos_de(lineas, etapa, limpiar=False)
    vigentes: list[tuple[str, str]] = []
    for t, crudo in zip(titulos, crudos):
        nuevo = etapa.ediciones_anteriores.get(t)
        if nuevo:
            logger.info("«%s» es la edición anterior de «%s» (%s): se usa el "
                        "nombre vigente", t, nuevo, pdf.name)
        vigentes.append((nuevo or t, crudo))

    # Índice de los hitos del documento.
    hitos: list[tuple[int, str, str]] = []
    for i, l in enumerate(lineas):
        m = RX_COMPETENCIA.match(l.texto)
        if m:
            hitos.append((i, "ce", m.group(1)))
        elif RX_CRITERIOS.match(l.texto):
            hitos.append((i, "criterios", ""))
        elif RX_SABERES.match(l.texto) and (l.tam >= 11.5 or l.negrita):
            # El tamaño solo no basta. Las materias que la XTEC volvió a
            # publicar tras el Decret 103/2026 —las diez de ciencias, Grec y
            # Llatí— maquetan el epígrafe en negrita **del mismo cuerpo que el
            # texto**, y con el umbral de tamaño a secas se quedaban con cero
            # saberes. La palabra «Sabers» a solas en una línea no aparece en
            # el cuerpo de ningún PDF, así que la negrita es suficiente.
            hitos.append((i, "saberes", ""))

    competencias: list[CompetenciaEspecifica] = []
    por_cursos: dict[tuple[str, ...], list[Criterio]] = {}
    # Arranca con la lista vacía compartida y no en blanco: hay 21 optativas
    # de Bachillerato que **no traen epígrafe de saberes** —el currículo deja
    # que los fije el profesorado— y sin esto se avisaba de un reparto por
    # curso que en ese PDF ni existe.
    saberes_por_cursos: dict[tuple[str, ...], list[BloqueSaberes]] = {(): []}

    for n, (idx, tipo, dato) in enumerate(hitos):
        fin = hitos[n + 1][0] if n + 1 < len(hitos) else len(lineas)
        cuerpo = lineas[idx + 1:fin]

        if tipo == "ce":
            competencias.append(
                CompetenciaEspecifica(
                    codigo=dato,
                    descripcion=" ".join(l.texto for l in cuerpo).strip(),
                )
            )
        elif tipo == "criterios":
            competencia = competencias[-1].codigo if competencias else "1"
            for col in _agrupar_criterios(cuerpo, competencia, etapa):
                por_cursos.setdefault(tuple(col.cursos), []).extend(col.criterios)
        elif tipo == "saberes":
            saberes_por_cursos = _saberes_por_curso(cuerpo, etapa)

    if not por_cursos:
        # Materia sin tabla de dos columnas: los cursos los dice el título, y
        # si tampoco, se deja vacío para que se note en vez de inventarlos.
        cursos = _cursos_del_titulo(portada) or []
        criterios: list[Criterio] = []
        for n, (idx, tipo, _d) in enumerate(hitos):
            if tipo != "criterios":
                continue
            fin = hitos[n + 1][0] if n + 1 < len(hitos) else len(lineas)
            comp = next((c for i, t, c in reversed(hitos[:n]) if t == "ce"), "1")
            for l in lineas[idx + 1:fin]:
                m = RX_CRITERIO.match(l.texto)
                if m:
                    criterios.append(Criterio(f"{m.group(1)}.{m.group(2)}", comp,
                                              m.group(3).strip()))
                elif criterios:
                    criterios[-1].descripcion += " " + l.texto
        por_cursos[tuple(cursos)] = criterios

    # Saberes de cada tramo. Cuando el epígrafe no viene partido —la ESO
    # entera y las materias de un solo curso— hay una sola lista y vale para
    # todos los tramos; cuando sí, cada tramo se lleva **los suyos**, y si no
    # los encuentra se queda vacío en vez de heredar los del otro curso.
    unicos = saberes_por_cursos.get(())

    def saberes_de(cursos: tuple[str, ...]) -> list[BloqueSaberes]:
        if unicos is not None:
            return unicos
        propios = saberes_por_cursos.get(cursos)
        if propios is None:
            logger.warning(
                "%s: el tramo %s no tiene saberes propios en un epígrafe "
                "partido por curso", pdf.name, " i ".join(cursos) or "Únic")
            return []
        return propios

    resultados: list[MateriaCiclo] = []
    for oficial, crudo in vigentes:
        # SI EL TÍTULO DICE SU CURSO, MANDA SOBRE EL PRODUCTO CRUZADO. Con dos
        # materias y dos columnas, cruzarlas da cuatro bloques y dos de ellos
        # son falsos: Expressió Artística, que es de 4.º, se llevaba también
        # los criterios de 1.º a 3.º.
        suyos = _cursos_del_titulo_propio(crudo) if len(vigentes) > 1 else None
        for cursos, criterios in por_cursos.items():
            if suyos is not None and cursos and set(cursos) != set(suyos):
                continue
            resultados.append(
                MateriaCiclo(
                    materia_oficial=oficial,
                    materia_corta=etiquetas.get(oficial, oficial),
                    ciclo=" i ".join(cursos) if cursos else "Únic",
                    cursos_aplicables=list(cursos),
                    etapa=etapa.nombre,
                    competencias=list(competencias),
                    criterios=criterios,
                    saberes=saberes_de(cursos),
                )
            )
    return resultados


# ---------------------------------------------------------------------------
# Los cursos que no dice el PDF
# ---------------------------------------------------------------------------


#: Títulos de los artículos del Decret 175/2022 que reparten materias por
#: curso, con los cursos que otorga cada uno. Se identifican por **título** y no
#: por número porque el Akoma Ntoso del EADOP no numera los artículos en el
#: cuerpo: solo en el índice.
_ARTICULOS_CURSOS = {
    "Matèries de l'educació secundària obligatòria de primer a tercer curs":
        ["1º ESO", "2º ESO", "3º ESO"],
    "Matèries de l'educació secundària obligatòria a quart curs": ["4º ESO"],
}


#: Materias que la XTEC publica y **el articulado no lista**, con los cursos
#: que les corresponden y de dónde sale el dato.
#:
#: POR QUÉ EXISTE ESTA EXCEPCIÓN, HABIENDO UNA REGLA CONTRA INVENTAR CURSOS.
#: La regla —una materia sin cursos se queda sin cursos y se dice— sigue en
#: pie, y es la que evitó que Llatí se ofreciera en 1.º de ESO. Pero tiene un
#: coste que se vio el 16/08: «Robòtica i Programació» se cargaba con la lista
#: vacía y quedaba **invisible**. No aparecía en el desplegable ni en el
#: contexto del modelo: cuatro competencias, dieciséis criterios y trece
#: saberes muertos en la base de datos, sin que nada lo dijera al usarla.
#:
#: La diferencia con inventar es la fuente. Estos cursos no se deducen del
#: PDF ni se suponen «por si acaso»: están en la normativa que obliga a los
#: centros a ofertar la materia, y se anota cuál para poder revisarlo.
#:
#: La clave va con el nombre **literal** y se normaliza con `_clave` en el
#: punto de uso, no aquí: esta constante se evalúa al importar el módulo y
#: `_clave` se define más abajo, así que llamarla desde el diccionario rompe el
#: import entero con `NameError`.
CURSOS_FUERA_DEL_ARTICULADO: dict[str, list[str]] = {
    # Optativa de oferta obligatoria en el primer ciclo: los centros deben
    # ofrecerla en alguno de los tres cursos, y cada uno decide en cuál —lo
    # habitual es 3.º— o si la reparte. Como el currículo es el mismo para los
    # tres, se declara en los tres y que el docente elija el suyo.
    #
    # **4.º queda fuera a propósito**: ahí la materia ya no es de oferta
    # obligatoria, y los centros que la mantienen suelen integrarla en
    # Tecnologia i Digitalització, que tiene su propio currículo.
    "Robòtica i Programació": ["1º ESO", "2º ESO", "3º ESO"],
}


def cursos_del_articulado(xml: Path) -> dict[str, list[str]]:
    """``materia -> cursos`` leyendo el articulado del decreto.

    POR QUÉ HACE FALTA
    ------------------
    Las materias comunes traen su reparto dentro del PDF, en la cabecera de las
    columnas. Las **optativas no**: su PDF no tiene tabla de dos columnas y la
    coletilla «(matèria optativa de quart d'ESO)» solo la llevan algunas.

    Sin esto se quedan con la lista de cursos vacía, y una materia sin cursos
    no es un error visible: es una materia que el desplegable ofrece en los
    cuatro cursos, o en ninguno. Filosofia en 1.º de ESO otra vez.
    """
    from html import unescape

    from lxml import etree

    ns = {"a": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}
    raiz = etree.parse(str(xml)).getroot()
    cuerpo = raiz.find("a:act", ns).find("a:body", ns)

    cursos_de: dict[str, list[str]] = {}
    for contenedor in cuerpo.iter(f"{{{ns['a']}}}hcontainer"):
        cab = contenedor.find(f"{{{ns['a']}}}heading")
        titulo = " ".join(cab.itertext()).strip() if cab is not None else ""
        cursos = _ARTICULOS_CURSOS.get(titulo)
        if not cursos:
            continue
        contenido = contenedor.find(f"{{{ns['a']}}}content")
        crudo = unescape(contenido.get("period") or "") if contenido is not None else ""
        for trozo in re.split(r"(?i)</p\s*>|<br\s*/?>", crudo):
            limpio = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", trozo)).strip()
            m = re.match(r"^[a-z]\)\s+(.+?)\.?$", limpio)
            if not m:
                continue
            materia = m.group(1).strip()
            if "No vigent" in materia or " i/o " in materia:
                # «Biologia i Geologia i/o Física i Química» no es una materia:
                # es una elección entre dos que ya están listadas por separado.
                continue
            cursos_de.setdefault(materia, [])
            for c in cursos:
                if c not in cursos_de[materia]:
                    cursos_de[materia].append(c)
    return cursos_de


def _clave(s: str) -> str:
    """Forma comparable de un nombre de materia: sin tildes, ni signos, ni caso.

    El PDF escribe «Llatí: Llengua i Cultura» y el articulado «Llatí: Llengua i
    Cultura»; parecen iguales y difieren en el apóstrofo tipográfico y en algún
    espacio. Comparar en crudo dejaría materias sin emparejar sin decir por qué.
    """
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


# ---------------------------------------------------------------------------
# Línea de órdenes
# ---------------------------------------------------------------------------


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def volcar(resultados: list[MateriaCiclo], salida: Path, comunidad: str,
           idioma: str) -> list[Path]:
    """Un JSON por (materia, cursos), con la comunidad y el idioma dentro.

    Los dos campos van en el fichero y no en el nombre porque el que los lee
    —`seed_curriculo`— los necesita en cada fila: sin ellos, cargar el decreto
    catalán actualizaría las filas de Ceuta en vez de añadir las suyas.
    """
    salida.mkdir(parents=True, exist_ok=True)
    escritos = []
    for mc in resultados:
        d = mc.to_dict()
        d["comunidad"] = comunidad
        d["idioma"] = idioma
        digitos = "_".join(re.findall(r"(\d)", " ".join(mc.cursos_aplicables))) or "unico"
        ruta = salida / f"{_slug(mc.materia_efectiva)}__{digitos}.json"
        ruta.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        escritos.append(ruta)
    # Los JSON de una extracción anterior se retiran: el nombre lleva los
    # cursos dentro, así que al cambiarlos queda el viejo y `seed_curriculo`
    # cargaría las dos versiones. Ver `extractor.retirar_huerfanos`.
    retirar_huerfanos(salida, escritos)
    return escritos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdfs", type=Path, required=True,
                   help="Carpeta con los PDF por materia (curriculo/fuentes/cataluna/xtec)")
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--comunidad", default="cataluna")
    p.add_argument("--idioma", default="ca")
    p.add_argument("--articulado", type=Path,
                   help="XML del decreto, para los cursos que el PDF no dice. "
                        "Solo la ESO: los de Bachillerato están en xtec_etapas.")
    p.add_argument("--etapa", choices=sorted(ETAPAS), default="eso",
                   help="Qué decreto se está leyendo (por defecto, la ESO).")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s | %(message)s")

    etapa = ETAPAS[args.etapa]

    pdfs = sorted(args.pdfs.glob("*.pdf"))
    if not pdfs:
        logger.error("No hay PDF en %s", args.pdfs)
        return 2

    del_articulado = cursos_del_articulado(args.articulado) if args.articulado else {}
    por_clave = {_clave(k): v for k, v in del_articulado.items()}
    # La tabla de la etapa se une a la del articulado. En la ESO está vacía y
    # manda el articulado; en Bachillerato es al revés.
    por_clave.update({_clave(k): v for k, v in etapa.cursos.items()})

    todos: list[MateriaCiclo] = []
    # EL PORTAL SIRVE LA MISMA MATERIA MÁS DE UNA VEZ. Seis materias de
    # Bachillerato valen para dos modalidades y la XTEC publica un PDF por
    # sección: los ficheros son idénticos byte a byte, comprobado. Sin esto
    # salen duplicadas en el recuento y `volcar` escribe dos veces el mismo
    # fichero, lo que no rompe nada pero esconde el día que **dejen** de ser
    # idénticas.
    vistas: dict[tuple[str, tuple[str, ...]], str] = {}
    for pdf in pdfs:
        res = extraer(pdf, etapa=etapa)
        if not res:
            logger.warning("Sin resultados: %s", pdf.name)
        for mc in res:
            if not mc.cursos_aplicables:
                clave = _clave(mc.materia_oficial)
                fuera = {_clave(k): v for k, v in CURSOS_FUERA_DEL_ARTICULADO.items()}
                mc.cursos_aplicables = list(
                    por_clave.get(clave) or fuera.get(clave, [])
                )
                mc.ciclo = " i ".join(mc.cursos_aplicables) or "Únic"
            clave_mc = (mc.materia_efectiva, tuple(mc.cursos_aplicables))
            anterior = vistas.get(clave_mc)
            if anterior is not None:
                logger.info("«%s» (%s) ya venía de %s: se ignora la copia de %s",
                            mc.materia_efectiva, mc.ciclo, anterior, pdf.name)
                continue
            vistas[clave_mc] = pdf.name
            todos.append(mc)

    sin_cursos = sorted({mc.materia_oficial for mc in todos if not mc.cursos_aplicables})
    if sin_cursos:
        # No se inventan: una materia sin cursos se queda sin cursos y se dice.
        # Ponerle los cuatro por defecto es lo que hacía que el formulario
        # ofreciera Llatí en 1.º de ESO.
        logger.error(
            "%d materias sin cursos, no se cargarán bien: %s",
            len(sin_cursos), ", ".join(sin_cursos),
        )

    escritos = volcar(todos, args.salida, args.comunidad, args.idioma)
    materias = {mc.materia_efectiva for mc in todos}
    print(f"\n{len(pdfs)} PDF -> {len(materias)} materias, {len(todos)} bloques, "
          f"{len(escritos)} ficheros en {args.salida}")
    for mc in sorted(todos, key=lambda m: (m.materia_efectiva, m.ciclo)):
        print(f"  {mc.materia_efectiva:46s} {str(mc.cursos_aplicables):34s} "
              f"CE={len(mc.competencias):2d} crit={len(mc.criterios):3d} "
              f"sab={sum(len(b.items) for b in mc.saberes):3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
