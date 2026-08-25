"""Extractor del currículo andaluz a partir del BOJA (Orden de 30 de mayo de 2023).

POR QUÉ OTRO MÓDULO, Y NO UN `Perfil` NI UNA VARIANTE DEL CATALÁN
------------------------------------------------------------------
`extractor.py` lee el BOE como una columna de texto y decide por el orden.
`extractor_xtec.py` lee tablas de dos columnas y decide por la posición
horizontal. El BOJA no es ninguna de las dos cosas: **cada materia trae cinco
piezas con maquetaciones distintas** —introducción a una columna, saberes a una
o dos columnas, y tablas de criterios de tres o de cinco columnas—, y las tres
convivan en la misma materia.

LO QUE ESTE BOLETÍN TIENE QUE NO TIENE NINGÚN OTRO
---------------------------------------------------
**Los saberes traen código oficial**: `BYG.1.A.8` es «Biología y Geología,
primer curso, bloque A, octavo saber», y lo escribe la norma. Esto resuelve de
un plumazo tres problemas que en Cataluña siguen abiertos:

1. **El curso no hay que deducirlo.** El segundo campo lo dice. En Cataluña
   había que cruzar el nombre de la materia con los artículos del decreto, y
   una materia que no casara se quedaba sin cursos.
2. **El identificador no hay que inventarlo.** El cargador venía numerando los
   saberes con un contador propio (`bloque.1`, `bloque.2`), que no existe en
   ningún boletín y no se puede citar. Aquí se guarda el de la norma.
3. **La separación de columnas se puede comprobar.** Si al partir la tabla en
   dos columnas una de ellas contiene códigos de dos cursos distintos, la
   partición está mal. En Cataluña ese fallo fue silencioso —4.º de ESO se
   quedó con cero criterios— porque no había nada con que contrastarlo. Aquí
   sí: ver `_comprobar_columnas`.

Y la tabla de criterios trae **una columna con los códigos de los saberes que
cada criterio moviliza**. Esa relación es de la norma, no una inferencia
nuestra, y es justo lo que la conexión curricular necesita.

DE DÓNDE SALEN LOS FICHEROS
----------------------------
De ``curriculo/fuentes/andalucia/``, los PDF del BOJA núm. 104 de 2 de junio de
2023. El Anexo II («Materias comunes obligatorias y optativas») es el que trae
el currículo por materia. Ver el LEEME de esa carpeta.
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


logger = logging.getLogger("curriculo.extractor_boja")


# ---------------------------------------------------------------------------
# Reconocimiento
# ---------------------------------------------------------------------------

#: Código de saber básico del BOJA: `BYG.1.A.8`, `MAT.2.D.6`, `GEH.2.B.11`.
#: El punto final es opcional porque el boletín no es constante: unas veces
#: escribe «BYG.1.A.8. Valoración…» y otras «BYG.1.A.8 Valoración…».
RX_SABER = re.compile(r"^([A-Z]{2,4})\.(\d)\.([A-Z])\.(\d+)\.?\s*(.*)$")

#: El mismo código, para buscarlo dentro de una celda de la tabla de criterios.
#: **El prefijo es opcional aquí, y no por comodidad.** En algunas tablas el
#: código queda escrito a caballo del borde entre la celda de criterios y la de
#: saberes, y PyMuPDF lo reparte tal cual: la primera se queda con «GE» y la
#: segunda con «H.3.A.2.». Exigiendo las dos a cuatro mayúsculas iniciales no
#: casaba ninguno, y el efecto era que Geografía e Historia 3.º, Lengua
#: Castellana 3.º, Lengua Extranjera 3.º y Física y Química 2.º salían con
#: **cero criterios**, sin ningún error: la columna existía y se leía, pero no
#: se sabía a qué curso asignarla.
RX_SABER_SUELTO = re.compile(r"\b[A-Z]{0,4}\.?(\d)\.[A-Z]\.\d+\.?")

#: Cabecera de bloque de saberes: «A. Proyecto científico.»
RX_BLOQUE = re.compile(r"^([A-Z])\.\s+(.+?)\.?\s*$")

#: Criterio de evaluación: «1.1. Analizar y describir…». El punto tras el
#: código es opcional por la misma razón que arriba.
RX_CRITERIO = re.compile(r"^(\d{1,2})\.(\d{1,2})\.?\s+(.*)$")

#: Competencia específica en el texto corrido: «3. Planificar y desarrollar…».
#: Se distingue de un criterio porque **no lleva subnúmero**.
RX_COMPETENCIA = re.compile(r"^(\d{1,2})\.\s+([A-ZÁÉÍÓÚÑ].*)$")

#: El mismo número, cuando la justificación lo deja **solo en su línea** y el
#: enunciado empieza en la siguiente. Pasa en Tecnología y Digitalización con
#: la competencia 2, y el efecto era que esa competencia no existía: se
#: cargaban las seis restantes y los criterios 2.1 a 2.4 apuntaban a una
#: competencia que no estaba, así que la conexión curricular quedaba coja
#: justo en el bloque que más se usa.
RX_COMPETENCIA_SOLA = re.compile(r"^(\d{1,2})\.$")

#: Línea de descriptores del perfil de salida: «STEM3, CD1, CPSAA3, CE3.»
RX_DESCRIPTORES = re.compile(
    r"^((?:CCL|CP|STEM|CD|CPSAA|CC|CE|CCEC)\d[, ]*)+\.?\s*$"
)

RX_MARCA_COMPETENCIAS = re.compile(r"^Competencias espec[íi]ficas\.?\s*$")
RX_MARCA_SABERES = re.compile(r"^Saberes b[áa]sicos\b.*$")

#: Pie y cabecera que se repiten en todas las páginas y no son contenido.
RX_PIE = re.compile(
    r"^(N[úu]mero \d+ -|p[áa]gina \d+/|\d{8}$|BOJA$|Bolet[íi]n Oficial|"
    r"Dep[óo]sito Legal|https?://|#CODIGO)"
)

#: Cabeceras de la tabla de criterios, que no son contenido de ninguna celda.
_CABECERAS_TABLA = {
    "competencias especificas", "criterios de evaluacion", "criterios evaluacion",
    "saberes basicos", "saberes", "basicos",
}

#: «Biología y Geología 1º», «Música Primer curso», «Matemáticas A».
#: El curso de la cabecera se usa **solo para avisar** si no coincide con el
#: que dicen los códigos: el que manda es el código.
RX_CURSO_CABECERA = re.compile(r"\b([1-4])\.?[ºo]\s*$")
_ORDINAL_TEXTO = {
    "primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3, "cuarto": 4,
}

_CURSO = {1: "1º ESO", 2: "2º ESO", 3: "3º ESO", 4: "4º ESO"}

#: El cuerpo del texto arranca en x≈64,5 y la tabla de criterios en x≈87. Todo
#: lo que esté a la izquierda de este valor es texto corrido, no celda.
_MARGEN = 80.0

#: Encabezados del anexo que tienen el mismo formato que un título de materia
#: —negrita, centrados, fuera de tabla— y no lo son.
_NO_SON_MATERIAS = {
    "materias comunes obligatorias y optativas",
    "anexo ii", "anexo iii",
}

#: Prefijos que denotan un itinerario de 4.º, no una materia distinta.
#: `MAA`/`MAB` son «Matemáticas A» y «Matemáticas B», que el modelo de datos ya
#: contempla con el campo `itinerario`.
_ITINERARIOS = {"MAA": "A", "MAB": "B"}


# ---------------------------------------------------------------------------
# Lectura del PDF
# ---------------------------------------------------------------------------


@dataclass
class Linea:
    """Una línea con lo que hace falta para saber dónde está y qué es."""

    pagina: int
    x: float
    y: float
    negrita: bool
    texto: str

    #: Si cae dentro de una tabla. Es lo que distingue el título de una materia
    #: («Música», centrado y en negrita en su página de portada) de la
    #: **cabecera de la tabla de criterios**, que dice exactamente lo mismo con
    #: el mismo formato unas páginas después. Sin este dato, «Música» salía dos
    #: veces y la segunda sin competencias ni saberes.
    en_tabla: bool = False


def _dentro(caja: tuple[float, float, float, float], tablas: list) -> bool:
    x0, y0, x1, y1 = caja
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(bx0 <= cx <= bx1 and by0 <= cy <= by1 for bx0, by0, bx1, by1 in tablas)


def leer_lineas(pdf: Path, desde: int = 0, hasta: int | None = None) -> list[Linea]:
    """Líneas del PDF en orden de lectura, sin pies ni cabeceras.

    Se conserva la ``x`` porque las tablas de saberes van a dos columnas y sin
    ella se entrelazan. Se conserva la negrita porque es lo único que distingue
    el título de una materia del párrafo que lo sigue. Y se anota si la línea
    cae dentro de una tabla, que es lo único que lo distingue de la cabecera de
    esa tabla.
    """
    doc = pymupdf.open(pdf)
    hasta = len(doc) if hasta is None else min(hasta, len(doc))
    lineas: list[Linea] = []
    for pno in range(desde, hasta):
        tablas = [t.bbox for t in doc[pno].find_tables().tables]
        for bloque in doc[pno].get_text("dict")["blocks"]:
            for linea in bloque.get("lines", []):
                spans = [s for s in linea["spans"] if s["text"].strip()]
                if not spans:
                    continue
                texto = "".join(s["text"] for s in linea["spans"]).strip()
                if not texto or RX_PIE.match(texto):
                    continue
                lineas.append(Linea(
                    pagina=pno,
                    x=round(linea["bbox"][0], 1),
                    y=round(linea["bbox"][1], 1),
                    # Negrita solo si lo es la línea entera: el primer span de
                    # una línea normal aparece en negrita con más frecuencia de
                    # la que uno esperaría, y eso convertía finales de párrafo
                    # («…biológicas.») en falsos títulos de materia.
                    negrita=all(s["flags"] & 2 ** 4 for s in spans),
                    texto=texto,
                    en_tabla=_dentro(linea["bbox"], tablas),
                ))
    doc.close()
    return lineas


# ---------------------------------------------------------------------------
# Troceo en materias
# ---------------------------------------------------------------------------


@dataclass
class _Materia:
    nombre: str
    inicio: int          # índice en la lista de líneas
    fin: int = 0
    marca_competencias: int = 0


def _es_titulo_candidato(ln: Linea) -> bool:
    """Negrita y **centrada**: el margen del cuerpo está en x≈64.

    El centrado es lo que separa el título de la materia de todo lo demás que
    va en negrita —los enunciados de las competencias, las cabeceras de bloque
    de saberes—, que van pegados al margen.
    """
    if not ln.negrita or ln.x < 150 or len(ln.texto) > 70 or ln.en_tabla:
        return False
    t = ln.texto
    # Un código de saber o una cabecera de bloque también pueden quedar
    # centrados dentro de una celda estrecha. No son títulos.
    if RX_SABER.match(t) or RX_BLOQUE.match(t):
        return False
    # «TERCER CURSO» encabeza una columna de la tabla de saberes y está
    # centrada y en negrita como un título. Si se cuela, parte la materia en
    # dos por la mitad y la primera mitad se queda sin saberes ni criterios.
    if _es_cabecera_curso(t):
        return False
    if _norm(t) in _NO_SON_MATERIAS:
        return False
    return not _norm(t) in _CABECERAS_TABLA


def trocear_materias(lineas: list[Linea]) -> list[_Materia]:
    """Una materia por cada título centrado **fuera de tabla**.

    EL CRITERIO, Y LOS DOS QUE SE DESCARTARON ANTES:

    *Por «Competencias específicas.»*, que parece el más seguro porque es una
    frase fija: no vale. **Matemáticas A y Matemáticas B no tienen esa
    sección** —van directas del título a los saberes—, así que las dos
    desaparecían. Y como la misma frase encabeza la primera columna de la tabla
    de criterios, las demás materias salían por duplicado.

    *Por título centrado en negrita*, sin más: tampoco. Las cabeceras de la
    tabla de criterios («Música», «Matemáticas A», «Lengua Extranjera 1º») son
    también negrita centrada, y repiten el nombre de la materia unas páginas
    después de su portada.

    Lo que separa los dos casos no es el formato —es idéntico— sino **estar o
    no dentro de una tabla**, que es exactamente lo que dice `en_tabla`.
    """
    materias: list[_Materia] = []
    for i, ln in enumerate(lineas):
        if not _es_titulo_candidato(ln):
            continue
        nombre = _limpiar_titulo(ln.texto)
        if materias and _norm(materias[-1].nombre) == _norm(nombre):
            # El mismo nombre dos veces seguidas es una portada repetida, no
            # una materia nueva.
            continue
        materias.append(_Materia(nombre=nombre, inicio=i))

    for a, b in zip(materias, materias[1:]):
        a.fin = b.inicio
    if materias:
        materias[-1].fin = len(lineas)

    # La sección de competencias en texto corrido, si la hay. Es opcional: sin
    # ella las competencias se quedan en las que cite la tabla de criterios.
    for mat in materias:
        mat.marca_competencias = next(
            (
                i for i in range(mat.inicio, mat.fin)
                if RX_MARCA_COMPETENCIAS.match(lineas[i].texto)
                and lineas[i].negrita and not lineas[i].en_tabla
            ),
            mat.inicio,
        )
    return materias


def _limpiar_titulo(t: str) -> str:
    """«Educación en Valores Cívicos y Éticos.» -> sin el punto final.

    El punto lo pone el boletín en unos títulos y en otros no. Dejarlo crearía
    dos materias distintas para la misma cosa en cuanto otro documento la
    escribiera sin él.
    """
    return t.strip().rstrip(".").strip()


# ---------------------------------------------------------------------------
# Competencias específicas
# ---------------------------------------------------------------------------


def extraer_competencias(lineas: list[Linea]) -> list[CompetenciaEspecifica]:
    """Del texto corrido en negrita que sigue a «Competencias específicas.».

    Se toman de aquí y no de la primera columna de la tabla de criterios porque
    en la tabla vienen **recortadas** para que quepan en la celda; aquí están
    enteras y además traen los descriptores del perfil de salida.
    """
    comps: list[CompetenciaEspecifica] = []
    actual: CompetenciaEspecifica | None = None
    for ln in lineas:
        if RX_MARCA_SABERES.match(ln.texto):
            break
        if not ln.negrita:
            # Los descriptores («STEM3, CD1, CE3.») van en redonda justo debajo.
            if actual is not None and RX_DESCRIPTORES.match(ln.texto):
                actual.descriptores = [
                    d for d in re.split(r"[,\s]+", ln.texto.rstrip(".")) if d
                ]
            continue
        m = RX_COMPETENCIA.match(ln.texto)
        sola = RX_COMPETENCIA_SOLA.match(ln.texto)
        if m or sola:
            actual = CompetenciaEspecifica(
                codigo=(m or sola).group(1),
                descripcion=m.group(2) if m else "",
            )
            comps.append(actual)
        elif actual is not None and not actual.descriptores:
            # Continuación del enunciado, que ocupa varias líneas. Solo mientras
            # no hayan llegado los descriptores: después de ellos, lo que venga
            # es ya de la competencia siguiente.
            actual.descripcion = f"{actual.descripcion} {ln.texto}".strip()
    for c in comps:
        c.descripcion = _juntar(c.descripcion)
    return comps


# ---------------------------------------------------------------------------
# Saberes básicos
# ---------------------------------------------------------------------------


def _columna_de(x: float, frontera: float) -> int:
    return 0 if x < frontera else 1


def _frontera(lineas: list[Linea]) -> float:
    """Punto medio entre la columna izquierda y la derecha, si hay dos.

    Se calcula del hueco más ancho entre valores de ``x`` consecutivos, no de
    un número escrito a mano: los PDF de esta orden no coinciden en el margen y
    una constante copiada de una materia daba cero saberes en otra.
    """
    xs = sorted({ln.x for ln in lineas})
    if len(xs) < 2:
        return float("inf")
    hueco, corte = 0.0, float("inf")
    for a, b in zip(xs, xs[1:]):
        if b - a > hueco:
            hueco, corte = b - a, (a + b) / 2
    # Menos de 100 pt de separación no es una segunda columna, es sangrado.
    return corte if hueco >= 100 else float("inf")


def texto_de_saberes(pdf: Path, desde: int, hasta: int) -> list[str]:
    """Las líneas de los saberes, **desenredadas por celdas**.

    POR QUÉ NO BASTA CON LA POSICIÓN HORIZONTAL, que es lo que se hizo primero
    y lo que funciona en el extractor catalán: aquí los saberes van dentro de
    una tabla con bordes, y las celdas tienen sangrados internos. Calcular la
    frontera entre columnas como «el hueco más ancho entre valores de x»
    acertaba en unas materias y en otras elegía un sangrado, con dos efectos
    igual de silenciosos: saberes **truncados** —«Formulación de hipótesis,
    preguntas y», sin el resto— y saberes **mezclados**, con media frase de la
    columna de tercero pegada a la de primero.

    Teniendo bordes de verdad, la separación ya está hecha en el PDF: basta con
    leer celda por celda y no reconstruir nada. Lo que queda fuera de tablas
    —las materias cuyos saberes van a una columna— se lee en orden normal.
    """
    doc = pymupdf.open(pdf)
    salida: list[str] = []
    try:
        for pno in range(desde, min(hasta, len(doc))):
            pagina = doc[pno]
            tablas = [t for t in pagina.find_tables().tables]
            cajas = [t.bbox for t in tablas]
            sueltas = [
                (linea["bbox"][1], "".join(s["text"] for s in linea["spans"]).strip())
                for bloque in pagina.get_text("dict")["blocks"]
                for linea in bloque.get("lines", [])
                if not _dentro(linea["bbox"], cajas)
            ]
            for _, t in sorted(sueltas):
                if t and not RX_PIE.match(t):
                    salida.append(t)
            for tabla in tablas:
                filas = tabla.extract()
                if _es_tabla_de_criterios(filas):
                    continue
                # Columna por columna: dentro de una columna las filas van en
                # orden, y así un saber partido en dos filas se vuelve a juntar.
                for col in range(max((len(f) for f in filas), default=0)):
                    for fila in filas:
                        if col >= len(fila) or not fila[col]:
                            continue
                        for t in fila[col].split("\n"):
                            t = t.strip()
                            if t and not RX_PIE.match(t):
                                salida.append(t)
    finally:
        doc.close()
    return salida


def extraer_saberes(textos: list[str]) -> dict[int, list[BloqueSaberes]]:
    """Saberes por curso, tomando el curso **del propio código**.

    NO SE DEDUCE DE LA COLUMNA, aunque la columna también lo diga. El código es
    la fuente: si una tabla se lee mal y un saber de tercero acaba en la
    columna de primero, el código lo delata y sigue guardándose bien.
    """
    # Se acumula plano y se agrupa al final: un saber puede continuar en la
    # página siguiente, y agrupar sobre la marcha obligaría a volver atrás.
    encontrados: list[_Saber] = []
    titulo_de: dict[str, str] = {}          # letra de bloque -> título
    actual: _Saber | None = None

    for t in textos:
        if _norm(t) in _CABECERAS_TABLA or _es_cabecera_curso(t):
            continue
        m = RX_SABER.match(t)
        if m:
            prefijo, curso, letra, num, resto = m.groups()
            actual = _Saber(
                curso=int(curso),
                letra=letra,
                codigo=f"{prefijo}.{curso}.{letra}.{num}",
                texto=resto,
            )
            encontrados.append(actual)
            continue
        mb = RX_BLOQUE.match(t)
        if mb and len(t) < 90 and not t[0].islower():
            letra, titulo = mb.groups()
            titulo_de[letra] = titulo
            # Un bloque abre sección: lo que venga detrás ya no es continuación
            # del saber anterior.
            actual = None
            continue
        if actual is not None:
            actual.texto = f"{actual.texto} {t}".strip()

    resultado: dict[int, list[BloqueSaberes]] = {}
    vistos: dict[str, int] = {}
    for sab in encontrados:
        # Un saber sin texto es un código que quedó suelto de su contenido. No
        # se guarda: una fila sin descripción no se puede citar ni mostrar.
        if not sab.texto.strip():
            continue
        # Un código repetido es el mismo saber leído dos veces —lo cita la
        # tabla de criterios, o la tabla se solapa entre dos páginas—. Se queda
        # la versión con más texto, que es la de la tabla de saberes; la citada
        # trae solo el código y lo que le siguiera en la celda.
        if sab.codigo in vistos:
            i = vistos[sab.codigo]
            if len(sab.texto) > len(encontrados[i].texto):
                encontrados[i].texto = sab.texto
            continue
        vistos[sab.codigo] = encontrados.index(sab)
        bloques = resultado.setdefault(sab.curso, [])
        blo = next((b for b in bloques if b.codigo == sab.letra), None)
        if blo is None:
            blo = BloqueSaberes(codigo=sab.letra, titulo=titulo_de.get(sab.letra, ""))
            bloques.append(blo)
        blo.items.append(_juntar(sab.texto))
        blo.codigos_items.append(sab.codigo)

    for bloques in resultado.values():
        bloques.sort(key=lambda b: b.codigo)
        for b in bloques:
            if not b.titulo:
                b.titulo = titulo_de.get(b.codigo, f"Bloque {b.codigo}")
    return resultado


@dataclass
class _Saber:
    curso: int
    letra: str
    codigo: str
    texto: str


def _es_cabecera_curso(t: str) -> bool:
    return _norm(t) in {
        "primer curso", "segundo curso", "tercer curso", "cuarto curso",
    }


# ---------------------------------------------------------------------------
# Criterios de evaluación
# ---------------------------------------------------------------------------


def extraer_criterios(
    pdf: Path, desde: int, hasta: int, prefijo: str = ""
) -> dict[int, list[Criterio]]:
    """Criterios por curso, de las tablas con cabecera «Criterios de evaluación».

    Aquí sí se usan las tablas que detecta PyMuPDF, y no el análisis posicional
    del extractor catalán: **estas tablas tienen bordes de verdad**, así que la
    partición en celdas viene dada y no hay que reconstruirla desde las ``x``.

    El curso de cada criterio se toma de los **saberes que cita**, no de la
    columna. Es la misma decisión que en `extraer_saberes` y por el mismo
    motivo: el código es de la norma y la columna es de la maquetación.
    """
    doc = pymupdf.open(pdf)
    por_curso: dict[int, dict[str, Criterio]] = {}
    # El «último criterio abierto» por columna. **Sobrevive al cambio de
    # página**, porque una tabla de siete páginas es siete tablas para PyMuPDF
    # y los criterios largos se parten justo por ahí. Se reinicia solo si
    # cambia el número de columnas, que es lo que marca el paso de la tabla de
    # 1.º y 3.º a la de 4.º: allí la columna 1 pasa a significar otro curso y
    # arrastrar el estado pegaría el texto al criterio equivocado.
    abiertos: dict[int, tuple[int, str]] = {}
    anchura = 0
    try:
        for pno in range(desde, min(hasta, len(doc))):
            for tabla in doc[pno].find_tables().tables:
                filas = tabla.extract()
                if not _es_tabla_de_criterios(filas):
                    continue
                if len(filas[0]) != anchura:
                    anchura, abiertos = len(filas[0]), {}
                for fila in filas:
                    _leer_fila_de_criterios(fila, por_curso, prefijo, abiertos)
    finally:
        doc.close()
    return {
        c: [cr for _, cr in sorted(d.items(), key=_orden_criterio)]
        for c, d in sorted(por_curso.items())
    }


def competencias_de_tabla(pdf: Path, desde: int, hasta: int) -> list[CompetenciaEspecifica]:
    """Competencias de la primera columna de la tabla, como último recurso.

    **Matemáticas A y Matemáticas B no traen la sección «Competencias
    específicas» en texto corrido**: van del título a los saberes. Sus
    competencias solo existen en la primera columna de la tabla de criterios, y
    sin leerlas de ahí las dos materias se cargaban con cero, que es lo mismo
    que no poder generar una SdA para 4.º de la ESO en Matemáticas.

    El texto sale más pobre que el de la sección —la celda lo recorta y aquí no
    hay descriptores del perfil de salida—, así que esto solo se usa cuando la
    sección no existe.
    """
    doc = pymupdf.open(pdf)
    trozos: dict[str, list[str]] = {}
    orden: list[str] = []
    try:
        for pno in range(desde, min(hasta, len(doc))):
            for tabla in doc[pno].find_tables().tables:
                filas = tabla.extract()
                if not _es_tabla_de_criterios(filas):
                    continue
                actual: str | None = None
                for fila in filas:
                    for linea in (fila[0] or "").split("\n"):
                        linea = linea.strip()
                        if not linea or _norm(linea) in _CABECERAS_TABLA:
                            continue
                        m = RX_COMPETENCIA.match(linea)
                        if m:
                            actual = m.group(1)
                            if actual not in trozos:
                                trozos[actual] = []
                                orden.append(actual)
                            trozos[actual].append(m.group(2))
                        elif actual is not None:
                            trozos[actual].append(linea)
    finally:
        doc.close()
    return [
        CompetenciaEspecifica(codigo=c, descripcion=_juntar(" ".join(trozos[c])))
        for c in sorted(orden, key=int)
    ]


def _orden_criterio(par: tuple[str, Criterio]) -> tuple[int, int]:
    a, _, b = par[0].partition(".")
    return int(a), int(b or 0)


def _es_tabla_de_criterios(filas: list[list[str | None]]) -> bool:
    """Por la **forma** y el contenido, no por la cabecera.

    Buscar «Criterios de evaluación» parece lo natural y es lo que se hizo
    primero, pero solo funciona en la primera página: una tabla que ocupa siete
    páginas lleva cabecera en una y en las otras seis no. Con ese criterio,
    Biología y Geología salía con **un** criterio en vez de treinta y tantos, y
    sin ningún error, porque las seis páginas restantes simplemente se
    ignoraban.

    La forma sí se conserva: número **impar** de columnas —una de competencias
    más un par (criterios, saberes) por curso— y al menos una celda que
    contenga un criterio o un código de saber. La tabla de saberes tiene dos
    columnas, así que no se cuela.
    """
    if not filas or len(filas[0]) < 3 or len(filas[0]) % 2 == 0:
        return False
    # Y **contiene criterios**, no solo códigos de saber. La condición parece
    # redundante y no lo es: la tabla de saberes de Matemáticas tiene tres
    # columnas —una por curso, que allí son tres— y está llena de códigos, así
    # que la forma sola la clasificaba como tabla de criterios y se saltaba
    # entera. Matemáticas se quedaba sin un solo saber en 1.º, 2.º ni 3.º.
    return any(
        RX_CRITERIO.match(linea.strip())
        for fila in filas for celda in fila if celda
        for linea in celda.split("\n")
    )


def _leer_fila_de_criterios(
    fila: list[str | None],
    por_curso: dict[int, dict[str, Criterio]],
    prefijo: str = "",
    abiertos: dict[int, tuple[int, str]] | None = None,
) -> None:
    """Cada celda de criterios va seguida de su celda de saberes.

    Una fila de la tabla de cinco columnas es
    ``[competencia, criterios 1º, saberes 1º, criterios 3º, saberes 3º]``; la
    de tres, ``[competencia, criterios 4º, saberes 4º]``. En los dos casos el
    par (criterios, saberes) empieza en la segunda celda y va de dos en dos,
    así que **no hace falta saber cuántos cursos hay**: se recorre por pares.
    """
    abiertos = {} if abiertos is None else abiertos
    for i in range(1, len(fila), 2):
        celda = fila[i] or ""
        codigos_celda = fila[i + 1] if i + 1 < len(fila) else ""
        cursos_citados = _cursos_de(codigos_celda or "")
        preludio, criterios = _criterios_de_celda(celda, prefijo)

        # Lo que hay antes del primer código de la celda es la cola del
        # criterio de la celda de arriba. Sin recuperarlo, sesenta y siete
        # criterios se guardaban partidos —«Identificar, valorar y», y ahí se
        # acababa— sin que nada fallara: el criterio existía, tenía su código y
        # su competencia, y solo le faltaban dos tercios de la frase.
        if preludio and i in abiertos:
            curso, codigo = abiertos[i]
            anterior = por_curso.get(curso, {}).get(codigo)
            if anterior is not None:
                anterior.descripcion = _juntar(f"{anterior.descripcion} {preludio}")

        for codigo, texto in criterios:
            # El curso sale de los saberes que la norma asocia al criterio. Si
            # la celda de saberes viniera vacía —pasa cuando la fila es la
            # continuación de la de la página anterior— se usa el criterio ya
            # abierto con ese código, que ya tiene curso.
            for curso in cursos_citados or _cursos_ya_vistos(codigo, por_curso):
                d = por_curso.setdefault(curso, {})
                if codigo in d:
                    d[codigo].descripcion = _juntar(f"{d[codigo].descripcion} {texto}")
                else:
                    d[codigo] = Criterio(
                        codigo=codigo,
                        competencia=codigo.split(".")[0],
                        descripcion=_juntar(texto),
                    )
                abiertos[i] = (curso, codigo)


def _restos_de(prefijo: str) -> list[str]:
    """Los trozos con que puede quedarse la celda de criterios: «GEH», «GE», «G».

    De más largo a más corto, para quitar el mayor que encaje. Solo prefijos
    propios del código de esta materia: barrer cualquier sigla al final de
    línea se comería mayúsculas legítimas del texto.
    """
    return [prefijo[:n] for n in range(len(prefijo), 0, -1)] if prefijo else []


def _cursos_de(celda: str) -> list[int]:
    return sorted({int(c) for c in RX_SABER_SUELTO.findall(celda)})


def _cursos_ya_vistos(
    codigo: str, por_curso: dict[int, dict[str, Criterio]]
) -> list[int]:
    return [c for c, d in por_curso.items() if codigo in d]


def _criterios_de_celda(
    celda: str, prefijo: str = ""
) -> tuple[str, list[tuple[str, str]]]:
    """Parte una celda en (cola del criterio anterior, criterios que empiezan aquí).

    Una celda puede traer varios criterios, y **casi siempre empieza a mitad de
    uno**: la tabla parte los criterios largos entre dos filas o dos páginas.
    Ese arranque no lleva código, así que devolverlo aparte es lo que permite
    pegarlo donde corresponde.

    El ``prefijo`` sirve para barrer los restos del código de saber que se
    quedaron en esta celda cuando el borde de la tabla partió el código por la
    mitad. Sin barrerlos, el criterio se guarda como «Elaborar contenidos GE
    propios en distintos GE formatos», con la sigla intercalada en mitad de la
    frase, y eso va tal cual al documento que ve el docente.
    """
    trozos = _restos_de(prefijo)
    salida: list[tuple[str, str]] = []
    preludio: list[str] = []
    for linea in celda.split("\n"):
        linea = linea.strip()
        for resto in trozos:
            if linea.endswith(" " + resto):
                linea = linea[: -len(resto)].rstrip()
                break
        if not linea or _norm(linea) in _CABECERAS_TABLA:
            continue
        m = RX_CRITERIO.match(linea)
        if m:
            salida.append((f"{m.group(1)}.{m.group(2)}", m.group(3)))
        elif salida:
            codigo, texto = salida[-1]
            salida[-1] = (codigo, f"{texto} {linea}")
        else:
            preludio.append(linea)
    return " ".join(preludio), salida


# ---------------------------------------------------------------------------
# Comprobaciones
# ---------------------------------------------------------------------------


def _comprobar_columnas(lineas: list[Linea], saberes: dict[int, list[BloqueSaberes]]) -> None:
    """Avisa si una columna mezcla cursos: señal de que la frontera está mal.

    ESTE ES EL CONTRASTE QUE EN CATALUÑA NO EXISTÍA. Allí el reparto por
    columnas era la única fuente del curso, así que una frontera mal puesta se
    tragaba media materia sin que nada lo dijera. Aquí hay dos fuentes —la
    columna y el código— y discrepar significa que una de las dos falla.
    """
    frontera = _frontera(lineas)
    if frontera == float("inf"):
        return
    por_columna: dict[int, set[int]] = {0: set(), 1: set()}
    for ln in lineas:
        m = RX_SABER.match(ln.texto)
        if m:
            por_columna[_columna_de(ln.x, frontera)].add(int(m.group(2)))
    for col, cursos in por_columna.items():
        if len(cursos) > 1:
            logger.warning(
                "La columna %d mezcla los cursos %s: la frontera x=%.0f puede "
                "estar mal puesta. Los saberes se guardan por su código igual.",
                col, sorted(cursos), frontera,
            )


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", "", s).strip()


def _juntar(t: str) -> str:
    """Junta líneas partidas por el ancho de la celda y arregla los guiones."""
    t = re.sub(r"(\w)-\s+(\w)", r"\1\2", t)
    return re.sub(r"\s+", " ", t).strip()


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def _prefijo_de(saberes: dict[int, list[BloqueSaberes]]) -> str:
    """El prefijo mayoritario de los códigos: «BYG», «MAT», «MAA».

    Mayoritario y no el primero que aparezca, porque el tramo de páginas de una
    materia se solapa con la primera página de la siguiente —hace falta ese
    margen para no cortar una tabla que termina ahí— y por el borde se cuelan
    unos pocos códigos ajenos.
    """
    cuenta: dict[str, int] = {}
    for bloques in saberes.values():
        for b in bloques:
            for c in b.codigos_items:
                p = c.split(".")[0]
                cuenta[p] = cuenta.get(p, 0) + 1
    return max(cuenta, key=lambda k: cuenta[k]) if cuenta else ""


def _solo_del_prefijo(
    saberes: dict[int, list[BloqueSaberes]], prefijo: str
) -> dict[int, list[BloqueSaberes]]:
    """Descarta los saberes que no son de esta materia.

    Sin esto aparecía una «Matemáticas 4º» fantasma con cinco saberes de
    Matemáticas A y ningún criterio: una entrada más en el desplegable que al
    elegirla no daba currículo con que generar nada.
    """
    limpio: dict[int, list[BloqueSaberes]] = {}
    for curso, bloques in saberes.items():
        nuevos = []
        for b in bloques:
            pares = [
                (c, i) for c, i in zip(b.codigos_items, b.items)
                if c.startswith(f"{prefijo}.")
            ]
            if pares:
                b.codigos_items = [c for c, _ in pares]
                b.items = [i for _, i in pares]
                nuevos.append(b)
        if nuevos:
            limpio[curso] = nuevos
    return limpio


# ---------------------------------------------------------------------------
# Montaje
# ---------------------------------------------------------------------------


def unir(pdfs: list[Path], salida: Path, tramos: list[tuple[int, int | None]]) -> Path:
    """Concatena los tramos de anexo de varios PDF en uno solo.

    HACE FALTA, no es comodidad. El Anexo II ocupa el final del primer PDF y el
    principio del segundo, y **Tecnología queda partida por la costura**: su
    portada y sus competencias están en un fichero y sus saberes y criterios en
    el otro. Extrayendo por separado sale dos veces y las dos incompletas, sin
    que nada falle: una materia con competencias y sin saberes, y otra con
    saberes y sin nombre.
    """
    destino = pymupdf.open()
    for pdf, (desde, hasta) in zip(pdfs, tramos):
        origen = pymupdf.open(pdf)
        destino.insert_pdf(
            origen, from_page=desde, to_page=(hasta - 1) if hasta else origen.page_count - 1
        )
        origen.close()
    destino.save(salida)
    destino.close()
    return salida


def extraer(pdf: Path, desde: int = 0, hasta: int | None = None) -> list[MateriaCiclo]:
    """Un `MateriaCiclo` por cada (materia, curso) del anexo."""
    lineas = leer_lineas(pdf, desde, hasta)
    materias = trocear_materias(lineas)
    if not materias:
        logger.error("No se reconoció ninguna materia en %s", pdf.name)
        return []

    resultados: list[MateriaCiclo] = []
    for mat in materias:
        trozo = lineas[mat.marca_competencias:mat.fin]
        competencias = extraer_competencias(trozo)

        # Los saberes empiezan en la primera marca «Saberes básicos…».
        arranque = next(
            (i for i, ln in enumerate(trozo) if RX_MARCA_SABERES.match(ln.texto)),
            None,
        )
        # Matemáticas A y B no tienen sección de competencias, así que su
        # cuerpo empieza en el título. Si tampoco hubiera marca de saberes se
        # arranca ahí mismo, en vez de descartar la materia entera.
        cuerpo = trozo[arranque:] if arranque is not None else trozo

        p_ini = cuerpo[0].pagina if cuerpo else 0
        p_fin = (lineas[mat.fin].pagina + 1) if mat.fin < len(lineas) else (hasta or 10 ** 6)

        saberes = extraer_saberes(texto_de_saberes(pdf, p_ini, p_fin))
        prefijo = _prefijo_de(saberes)
        saberes = _solo_del_prefijo(saberes, prefijo)
        criterios = extraer_criterios(pdf, p_ini, p_fin, prefijo)
        if not competencias:
            competencias = competencias_de_tabla(pdf, p_ini, p_fin)
            if competencias:
                logger.info(
                    "%s: sin sección de competencias, se toman de la tabla (%d)",
                    mat.nombre, len(competencias),
                )

        # «Matemáticas A» ya lleva el itinerario en el nombre. Dejarlo en los
        # dos sitios da «Matemáticas A A» en el desplegable, porque
        # `materia_efectiva` concatena los dos campos.
        itinerario = _ITINERARIOS.get(prefijo)
        nombre = mat.nombre
        if itinerario and nombre.endswith(f" {itinerario}"):
            nombre = nombre[: -2].strip()

        cursos = sorted(set(saberes) | set(criterios))
        if not cursos:
            logger.error("%s: ni saberes ni criterios, no se guarda", nombre)
            continue
        for curso in cursos:
            if curso not in saberes:
                logger.warning("%s %sº: criterios sin saberes", nombre, curso)
            if curso not in criterios:
                logger.warning("%s %sº: saberes sin criterios", nombre, curso)
            resultados.append(MateriaCiclo(
                materia_oficial=nombre,
                materia_corta=nombre,
                ciclo=_CURSO[curso],
                cursos_aplicables=[_CURSO[curso]],
                itinerario=itinerario,
                competencias=list(competencias),
                criterios=criterios.get(curso, []),
                saberes=saberes.get(curso, []),
            ))
    return resultados


def volcar(resultados: list[MateriaCiclo], salida: Path, comunidad: str,
           idioma: str) -> list[Path]:
    """Un JSON por (materia, curso), con la comunidad y el idioma dentro.

    Los saberes se vuelcan **con su código oficial**, no como una lista de
    textos: es lo único que este boletín da y los demás no, y perderlo aquí
    haría que el cargador volviera a numerarlos con un contador inventado.
    """
    salida.mkdir(parents=True, exist_ok=True)
    escritos = []
    for mc in resultados:
        d = mc.to_dict()
        d["comunidad"] = comunidad
        d["idioma"] = idioma
        d["saberes_basicos"] = [
            {
                "codigo": b.codigo,
                "bloque": f"{b.codigo}. {b.titulo}",
                "titulo": b.titulo,
                "items": b.items,
                "codigos_items": b.codigos_items,
            }
            for b in mc.saberes
        ]
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
    p.add_argument("--pdf", action="append", required=True, metavar="RUTA[:DESDE:HASTA]",
                   help="PDF del BOJA con el tramo del anexo, 0-based y HASTA "
                        "excluido. Se puede repetir: los tramos se concatenan "
                        "en el orden dado.")
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--comunidad", default="andalucia")
    p.add_argument("--idioma", default="es")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s | %(message)s")

    pdfs, tramos = [], []
    for spec in args.pdf:
        partes = spec.rsplit(":", 2)
        if len(partes) == 3 and partes[1].isdigit():
            pdfs.append(Path(partes[0]))
            tramos.append((int(partes[1]), int(partes[2]) if partes[2] else None))
        else:
            pdfs.append(Path(spec))
            tramos.append((0, None))
    for ruta in pdfs:
        if not ruta.exists():
            logger.error("No existe: %s", ruta)
            return 2

    args.salida.mkdir(parents=True, exist_ok=True)
    unido = unir(pdfs, args.salida / "_anexo_unido.pdf", tramos)
    todos = extraer(unido)
    unido.unlink(missing_ok=True)
    if not todos:
        logger.error("Sin resultados")
        return 1

    escritos = volcar(todos, args.salida, args.comunidad, args.idioma)
    materias = {mc.materia_efectiva for mc in todos}
    print(f"\n{len(pdfs)} PDF -> {len(materias)} materias, {len(todos)} bloques, "
          f"{len(escritos)} ficheros en {args.salida}")
    for mc in sorted(todos, key=lambda m: (m.materia_efectiva, m.ciclo)):
        print(f"  {mc.materia_efectiva:44s} {mc.ciclo:9s} "
              f"CE={len(mc.competencias):2d} crit={len(mc.criterios):3d} "
              f"sab={sum(len(b.items) for b in mc.saberes):3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
