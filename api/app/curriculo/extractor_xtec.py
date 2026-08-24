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

from .extractor import BloqueSaberes, CompetenciaEspecifica, Criterio, MateriaCiclo


logger = logging.getLogger("curriculo.extractor_xtec")


# ---------------------------------------------------------------------------
# Reconocimiento
# ---------------------------------------------------------------------------

#: «Competència específica 3»
RX_COMPETENCIA = re.compile(r"^Compet[èe]ncia espec[íi]fica\s+(\d+)\s*$")

#: «Criteris d'avaluació», con apóstrofo tipográfico o recto.
RX_CRITERIOS = re.compile(r"^Criteris d[’']avaluaci[óo]\s*$")

RX_SABERES = re.compile(r"^Sabers\s*$")

#: «1.1 Interpretar problemes…» o «1.1. Analitzar conceptes…». El punto final
#: del código es opcional porque **los PDF no se ponen de acuerdo**: Matemàtiques
#: escribe «1.1 » y Cultura Científica «1.1. ». Sin el punto opcional, la
#: segunda no casaba ni un criterio y la materia salía con cero, sin dar error.
RX_CRITERIO = re.compile(r"^(\d+)\.(\d+)\.?\s+(.*)$")

#: Cabecera de columna: «1r i 2n», «1r, 2n i 3r», «4t», «3r i 4t».
RX_CABECERA_CURSOS = re.compile(r"^(?:1r|2n|3r|4t)(?:[\s,i]+(?:1r|2n|3r|4t))*$")

_ORDINAL_A_CURSO = {"1r": "1º ESO", "2n": "2º ESO", "3r": "3º ESO", "4t": "4º ESO"}

#: Pie de página que se repite en todas las páginas y no es contenido.
RX_PIE = re.compile(r"^Decret 175/2022|^\d+/\d+$")

#: «(matèria optativa de quart d'ESO)» en el título: dice el curso cuando no
#: hay tabla de dos columnas que lo diga.
RX_OPTATIVA_CURSO = re.compile(
    r"optativa de\s+(primer|segon|tercer|quart)(?:\s+a\s+(primer|segon|tercer|quart))?", re.I
)
_ORDINAL_LARGO = {"primer": 1, "segon": 2, "tercer": 3, "quart": 4}


def _cursos_de_cabecera(texto: str) -> list[str]:
    """«1r, 2n i 3r» -> ``["1º ESO", "2º ESO", "3º ESO"]``."""
    return [_ORDINAL_A_CURSO[o] for o in re.findall(r"1r|2n|3r|4t", texto)]


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


def leer_lineas(pdf: Path) -> list[Linea]:
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
                if not texto or RX_PIE.match(texto):
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


def titulos_de(lineas: list[Linea]) -> list[str]:
    """Las materias que cubre el PDF.

    Normalmente una. Pero el bloque lingüístico catalán publica **tres materias
    con un solo currículo compartido** —Aranès, Llengua Castellana y Llengua
    Catalana— en un mismo fichero y con tres títulos en la portada. Devolver
    solo el primero habría dejado dos materias enteras sin currículo, y sin dar
    ningún error: simplemente no aparecerían en el desplegable.
    """
    de_portada = [l for l in lineas if l.pagina == 1]
    if not de_portada:
        return []
    mayor = max(l.tam for l in de_portada)
    crudos = [l.texto for l in de_portada if l.tam >= mayor - 0.1 and len(l.texto) > 3]
    return [_limpiar_titulo(t) for t in crudos]


def _limpiar_titulo(titulo: str) -> str:
    """Quita del título lo que dice el curso, que no es parte del nombre.

    «Cultura Científica (matèria optativa de quart d'ESO)» y «Educació
    Plàstica, Visual i Audiovisual de primer a tercer» son la misma materia con
    y sin coletilla. Si la coletilla se queda dentro, la materia guardada no
    coincide con la que lista el articulado y el desplegable ofrece dos
    entradas para lo mismo.
    """
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


def _agrupar_criterios(lineas: list[Linea], competencia: str) -> list[_Columna]:
    """Los criterios de una competencia, repartidos por columna.

    ``lineas`` va desde la cabecera de columnas hasta el final del bloque.

    El reparto se hace por **cercanía al inicio de cada columna**, no por un
    punto medio fijo: las tablas no están siempre en el mismo sitio y una
    materia sin tabla tiene una sola columna que ocupa todo el ancho.
    """
    cabeceras = [l for l in lineas if RX_CABECERA_CURSOS.match(l.texto)]
    if not cabeceras:
        return []

    # Las de la primera fila: las que comparten la `y` de la primera cabecera.
    y0 = cabeceras[0].y
    cabeceras = [c for c in cabeceras if abs(c.y - y0) < 5]
    cabeceras.sort(key=lambda c: c.x)

    columnas = [_Columna(cursos=_cursos_de_cabecera(c.texto), x_min=c.x, x_max=0)
                for c in cabeceras]

    cuerpo = [l for l in lineas if l.y > y0 + 5]
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
    """
    utiles = [l for l in lineas if not _es_vineta(l.texto)]
    if not utiles:
        return []

    # Los `x` se agrupan, no se listan: dentro de un mismo nivel hay
    # variaciones de dos o tres puntos —103 y 106 son el mismo sangrado— y
    # tomar «el tercer valor distinto» daba 106 en Matemàtiques, con lo que el
    # nivel de subbloque quedaba por encima del umbral y se perdía entero.
    niveles: list[int] = []
    for x in sorted({round(l.x) for l in utiles}):
        if not niveles or x - niveles[-1] > 6:
            niveles.append(x)

    margen = niveles[0]
    # Con tres niveles el segundo es subbloque; con dos, el segundo ya es el
    # item y no hay subbloque que valga.
    hay_subbloque = len(niveles) >= 3
    x_item = niveles[2] if hay_subbloque else (niveles[1] if len(niveles) > 1 else margen)

    bloques: list[BloqueSaberes] = []
    titulo_bloque = ""
    actual: BloqueSaberes | None = None

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

    for l in utiles:
        es_bloque = l.x <= margen + 6 and l.negrita
        es_item = l.x >= x_item - 4

        if es_bloque:
            titulo_bloque = _sin_marca(l.texto).rstrip(".")
            # Sin subbloque, el bloque recoge sus items directamente.
            actual = None if hay_subbloque else abrir(titulo_bloque)
        elif hay_subbloque and not es_item:
            sub = _sin_marca(l.texto).rstrip(".")
            actual = abrir(f"{titulo_bloque} · {sub}" if titulo_bloque else sub)
        elif es_item and actual is not None:
            if actual.items and not re.match(r"^[A-ZÀ-Ú¡¿0-9]", l.texto):
                # Continuación del item anterior, partido por el ancho de la
                # celda. Se decide por la mayúscula inicial: un item nuevo
                # siempre empieza por una.
                actual.items[-1] = f"{actual.items[-1]} {l.texto}".strip()
            else:
                actual.items.append(l.texto)
    return [b for b in bloques if b.items]


def extraer(pdf: Path, etiquetas: dict[str, str] | None = None) -> list[MateriaCiclo]:
    """Devuelve un `MateriaCiclo` por cada (materia, grupo de cursos).

    :param etiquetas: nombre oficial -> etiqueta corta para la aplicación. Lo
        que no esté aquí conserva su nombre oficial.
    """
    etiquetas = etiquetas or {}
    lineas = leer_lineas(pdf)
    if not lineas:
        logger.error("PDF sin texto extraíble: %s", pdf)
        return []

    portada = " ".join(l.texto for l in lineas if l.pagina == 1)
    titulos = titulos_de(lineas)
    if not titulos:
        logger.error("No se encontró ningún título de materia en %s", pdf)
        return []

    # Índice de los hitos del documento.
    hitos: list[tuple[int, str, str]] = []
    for i, l in enumerate(lineas):
        m = RX_COMPETENCIA.match(l.texto)
        if m:
            hitos.append((i, "ce", m.group(1)))
        elif RX_CRITERIOS.match(l.texto):
            hitos.append((i, "criterios", ""))
        elif RX_SABERES.match(l.texto) and l.tam >= 11.5:
            hitos.append((i, "saberes", ""))

    competencias: list[CompetenciaEspecifica] = []
    por_cursos: dict[tuple[str, ...], list[Criterio]] = {}
    saberes: list[BloqueSaberes] = []

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
            for col in _agrupar_criterios(cuerpo, competencia):
                por_cursos.setdefault(tuple(col.cursos), []).extend(col.criterios)
        elif tipo == "saberes":
            saberes = _extraer_saberes(cuerpo)

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

    resultados: list[MateriaCiclo] = []
    for titulo in titulos:
        oficial = titulo
        for cursos, criterios in por_cursos.items():
            resultados.append(
                MateriaCiclo(
                    materia_oficial=oficial,
                    materia_corta=etiquetas.get(oficial, oficial),
                    ciclo=" i ".join(cursos) if cursos else "Únic",
                    cursos_aplicables=list(cursos),
                    competencias=list(competencias),
                    criterios=criterios,
                    saberes=saberes,
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
    return escritos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdfs", type=Path, required=True,
                   help="Carpeta con los PDF por materia (curriculo/fuentes/cataluna/xtec)")
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--comunidad", default="cataluna")
    p.add_argument("--idioma", default="ca")
    p.add_argument("--articulado", type=Path,
                   help="XML del decreto, para los cursos que el PDF no dice.")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s | %(message)s")

    pdfs = sorted(args.pdfs.glob("*.pdf"))
    if not pdfs:
        logger.error("No hay PDF en %s", args.pdfs)
        return 2

    del_articulado = cursos_del_articulado(args.articulado) if args.articulado else {}
    por_clave = {_clave(k): v for k, v in del_articulado.items()}

    todos: list[MateriaCiclo] = []
    for pdf in pdfs:
        res = extraer(pdf)
        if not res:
            logger.warning("Sin resultados: %s", pdf.name)
        for mc in res:
            if not mc.cursos_aplicables:
                mc.cursos_aplicables = list(por_clave.get(_clave(mc.materia_oficial), []))
                mc.ciclo = " i ".join(mc.cursos_aplicables) or "Únic"
        todos.extend(res)

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
