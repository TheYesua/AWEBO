"""Extractor del currículo gallego (Decreto 156/2022), desde los PDF de la Xunta.

DE DÓNDE SALEN LOS FICHEROS
----------------------------
De ``curriculo/fuentes/galicia/``: un PDF por materia, descargados de la Guía
LOMLOE de la Consellería con ``docs/scripts/descargar-galicia.cmd``. **No del
DOG**, que publica el Anexo II entero en un solo documento.

Es el mismo patrón que la XTEC en Cataluña, y ya van dos de dos: cuando una
comunidad tiene lengua propia, su consejería suele republicar el currículo por
materias en un formato mejor que el del boletín. Conviene buscarlo antes de
pelearse con el PDF oficial.

GALICIA USA OTRO VOCABULARIO, Y NO ES UNA TRADUCCIÓN
-----------------------------------------------------
====================== ================== ==========================
LOMLOE estándar        Galicia            Se guarda como
====================== ================== ==========================
Competencia específica **Obxectivo**      `CompetenciaEspecifica`
Criterio de evaluación Criterio de avaliación  `Criterio`
Saber básico           **Contido**        `BloqueSaberes.items`
====================== ================== ==========================

El decreto **no habla de competencias específicas** en el currículo de cada
materia: lo que ocupa ese lugar son los «obxectivos», con su propio código
`OBX1`. Se mapean a `CompetenciaEspecifica` porque es el mismo papel en el
modelo —lo que el criterio referencia— y no porque sean la misma palabra.

Y hay una diferencia estructural que sí obliga a trabajar: **los criterios se
agrupan por bloque y cada uno referencia su `OBX`**, al revés que en las otras
tres comunidades, donde los criterios cuelgan de la competencia. La relación
hay que invertirla al leer.

POR QUÉ ESTE FORMATO ES EL MÁS AMABLE DE LOS CUATRO
-----------------------------------------------------
* Todo va en **tablas con bordes**, así que se lee celda a celda sin análisis
  posicional. Igual que el BOJA y al revés que la XTEC.
* **Los cursos vienen dentro del PDF**, en la propia tabla («1.º curso»). Ni
  articulado ni web, que es lo que costó en Cataluña.
* Los bloques van **numerados por el decreto** (`Bloque 1`). Los contidos no
  llevan código propio, pero el del bloque sí es oficial, así que el código de
  un contido —`1.3`— tiene la mitad que importa sacada de la norma. Queda entre
  Andalucía, con el código entero oficial, y Cataluña, donde todo es nuestro.
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


logger = logging.getLogger("curriculo.extractor_dog")


# ---------------------------------------------------------------------------
# Reconocimiento
# ---------------------------------------------------------------------------

#: «OBX1. Interpretar e transmitir información…»
#:
#: El espacio tras «OBX» es opcional porque **el boletín no es constante**: en
#: Física e Química los cuatro primeros van pegados y el quinto y el sexto se
#: escriben «OBX 5.» y «OBX 6.». Sin contemplarlo, esa materia salía con cuatro
#: obxectivos y sus criterios citaban dos que no existían — el aviso de
#: `_montar` fue lo que lo destapó.
RX_OBXECTIVO = re.compile(r"^OBX\s*(\d+)\.\s*(.*)$")

#: «▪ CA1.1. Analizar e explicar…». La viñeta es opcional porque la celda a
#: veces la trae y a veces no, según cómo parta PyMuPDF la fila.
RX_CRITERIO = re.compile(r"^[▪\s]*CA(\d+)\.(\d+)\.?\s*(.*)$", re.S)

#: «Bloque 1. Proxecto científico»
RX_BLOQUE = re.compile(r"^Bloque\s+(\d+)\.?\s*(.*)$")

#: «1.º curso», y también «Primeiro curso», que encabeza la sección.
RX_CURSO_ORDINAL = re.compile(r"^([1-4])\.?[ºo]\s+curso\s*$", re.I)
RX_CURSO_LETRA = re.compile(r"^(Primeiro|Segundo|Terceiro|Cuarto)\s+curso\s*$", re.I)
_LETRA_A_NUM = {"primeiro": 1, "segundo": 2, "terceiro": 3, "cuarto": 4}

#: «Materia de Bioloxía e Xeoloxía»
RX_MATERIA = re.compile(r"^Materia de\s+(.+?)\s*$")

RX_MARCA_CRITERIOS = re.compile(r"^Criterios de avaliaci[óo]n\s*$", re.I)
RX_MARCA_CONTIDOS = re.compile(r"^Contidos\s*$", re.I)
RX_MARCA_OBXECTIVOS = re.compile(r"^1\.2\s+Obxectivos\s*$")

#: Pie de página: «Páxina 7 de 23».
RX_PIE = re.compile(r"^P[áa]xina\s+\d+\s+de\s+\d+\s*$")

_CURSO = {1: "1º ESO", 2: "2º ESO", 3: "3º ESO", 4: "4º ESO"}

#: Materias cuyo PDF **no dice el curso**, porque su currículo es el mismo para
#: varios. Los cursos salen de la tabla de la Guía LOMLOE de la Consellería:
#: https://www.edu.xunta.gal/portal/guialomloe/secundaria
#:
#: Mismo caso que «Robòtica i Programació» en Cataluña y misma decisión: una
#: excepción documentada con su fuente, en vez de inventar los cursos o dejar
#: la materia cargada e invisible. Se compara con `_clave`, que ignora tildes.
CURSOS_DE_LA_GUIA: dict[str, list[str]] = {
    "Cultura Clásica": ["3º ESO", "4º ESO"],
    "Oratoria": ["3º ESO", "4º ESO"],
    "Proxecto Competencial": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _clave(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)


def _juntar(texto: str) -> str:
    """Junta las líneas de una celda y deshace los guiones de división.

    El PDF parte palabras al final de renglón —«diferen-\\ntes»— y además usa
    un carácter de control (U+0002) donde va ese guion en algunos sitios. Sin
    deshacerlo, el texto guardado dice «diferen tes».
    """
    # U+0002 es el guion de división **ya aplicado** por el maquetador: donde
    # aparece, la palabra estaba partida por el renglón. Se quita uniendo, no
    # se cambia por un guion — «perse<U+0002>gue» es «persegue».
    texto = re.sub(r"(\w)\x02\s*(\w)", r"\1\2", texto)
    texto = texto.replace("", "")
    texto = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", texto)
    texto = re.sub(r"(\w)-\s+(\w)", r"\1\2", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


# ---------------------------------------------------------------------------
# Obxectivos (equivalen a las competencias específicas)
# ---------------------------------------------------------------------------


def extraer_obxectivos(doc: pymupdf.Document) -> list[CompetenciaEspecifica]:
    """Los `OBX` de la sección 1.2, que van en texto corrido y no en tabla.

    Cada uno es ``OBX1. <enunciado>`` seguido de varios párrafos con viñeta que
    lo explican. **Solo se guarda el enunciado**: lo de debajo es justificación
    pedagógica, no currículo, y metida en el prompt solo gastaría contexto.
    """
    lineas: list[str] = []
    dentro = False
    for pagina in doc:
        for linea in pagina.get_text().split("\n"):
            linea = linea.strip()
            if RX_MARCA_OBXECTIVOS.match(linea):
                dentro = True
                continue
            if not dentro or RX_PIE.match(linea):
                continue
            # La sección siguiente cierra la de obxectivos.
            if linea.startswith("1.3"):
                dentro = False
                break
            lineas.append(linea)

    obxectivos: list[CompetenciaEspecifica] = []
    actual: list[str] = []
    codigo = ""
    for linea in lineas:
        m = RX_OBXECTIVO.match(linea)
        if m:
            if codigo:
                obxectivos.append(
                    CompetenciaEspecifica(codigo=codigo, descripcion=_juntar(" ".join(actual)))
                )
            codigo, actual = m.group(1), [m.group(2)]
        elif codigo and not linea.startswith("▪") and linea:
            # Continuación del enunciado. Las viñetas son la explicación, y
            # ahí se deja de acumular.
            if not actual or not actual[-1].endswith("."):
                actual.append(linea)
        elif linea.startswith("▪"):
            # Cierra el enunciado en curso, pero no el obxectivo: el siguiente
            # `OBXn.` es quien lo cierra de verdad.
            if actual and not actual[-1].endswith("."):
                actual[-1] += "."
    if codigo:
        obxectivos.append(
            CompetenciaEspecifica(codigo=codigo, descripcion=_juntar(" ".join(actual)))
        )
    return obxectivos


# ---------------------------------------------------------------------------
# Criterios y contidos, que van en tablas
# ---------------------------------------------------------------------------


@dataclass
class _Tramo:
    """Lo que se acumula para un curso concreto."""

    criterios: list[Criterio] = field(default_factory=list)
    bloques: dict[str, BloqueSaberes] = field(default_factory=dict)


def _dentro(caja, cajas) -> bool:
    x0, y0, x1, y1 = caja
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(bx0 <= cx <= bx1 and by0 <= cy <= by1 for bx0, by0, bx1, by1 in cajas)


def _filas_en_orden(pagina) -> list[tuple[str, str]]:
    """Todo lo de la página —filas de tabla y texto suelto— en orden de lectura.

    NO BASTA CON RECORRER LAS TABLAS, y esto costó una tanda entera. La primera
    versión solo miraba tablas, y en varias materias **la cabecera de curso
    está fuera de una**: en Lingua Castelá solo se detectaban «1º curso» y «4º
    curso», así que los criterios de 2.º y 3.º se acumulaban en el curso
    anterior. La materia salía con 97 criterios en 1.º en vez de 23, y sin 2.º
    ni 3.º — y ningún error, porque los criterios existían y se guardaban.

    Se ordena por la coordenada vertical, que es lo único que dice de verdad
    qué viene antes: una máquina de estados sobre el documento necesita el
    orden del documento, no el de las tablas.
    """
    tablas = pagina.find_tables().tables
    cajas = [t.bbox for t in tablas]
    eventos: list[tuple[float, str, str]] = []

    for bloque in pagina.get_text("dict")["blocks"]:
        for linea in bloque.get("lines", []):
            if _dentro(linea["bbox"], cajas):
                continue
            texto = "".join(s["text"] for s in linea["spans"]).strip()
            if texto:
                eventos.append((linea["bbox"][1], texto, ""))

    for tabla in tablas:
        # Un desplazamiento minúsculo por fila conserva su orden dentro de la
        # tabla sin alterar el orden respecto al resto de la página.
        for i, fila in enumerate(tabla.extract()):
            if not fila:
                continue
            izq = (fila[0] or "").strip()
            der = (fila[1] or "").strip() if len(fila) > 1 else ""
            eventos.append((tabla.bbox[1] + i * 1e-3, izq, der))

    return [(izq, der) for _, izq, der in sorted(eventos, key=lambda e: e[0])]


def extraer_tramos(doc: pymupdf.Document, materia_portada: str
                   ) -> dict[tuple[str, int], _Tramo]:
    """Recorre las tablas en orden y reparte lo que encuentra por curso.

    Es una máquina de estados sobre las filas, y funciona porque **el orden de
    lectura es el orden del documento**: la fila «2.º curso» cambia el curso
    activo, «Bloque 3. …» el bloque activo, y «Contidos» dice que lo que viene
    ya no son criterios. Con tablas que tienen bordes de verdad no hace falta
    nada más.
    """
    # La clave lleva la materia porque **un PDF puede traer varias**:
    # `Matematicas.pdf` contiene Matemáticas, Matemáticas A y Matemáticas B, y
    # cada una arranca con su «Materia de …». Sin esto, los criterios de las
    # tres se sumaban bajo el título de la portada y Matemáticas de 4.º salía
    # con 73 criterios en vez de 37.
    tramos: dict[tuple[str, int], _Tramo] = {}
    materia = materia_portada
    curso = 0
    bloque_num = bloque_titulo = ""
    en_contidos = False

    for pagina in doc:
        for izq, der in _filas_en_orden(pagina):
            if not izq or RX_PIE.match(izq):
                continue

            if (m := RX_CURSO_ORDINAL.match(izq)):
                curso, en_contidos = int(m.group(1)), False
                continue
            if (m := RX_CURSO_LETRA.match(izq)):
                curso, en_contidos = _LETRA_A_NUM[m.group(1).lower()], False
                continue
            if (m := RX_BLOQUE.match(izq)):
                bloque_num, bloque_titulo = m.group(1), _juntar(m.group(2))
                en_contidos = False
                continue
            if RX_MARCA_CONTIDOS.match(izq):
                en_contidos = True
                continue
            if (m := RX_MATERIA.match(izq)):
                materia, en_contidos = _juntar(m.group(1)), False
                continue
            if RX_MARCA_CRITERIOS.match(izq):
                en_contidos = False
                continue

            # Solo interesan las filas que aportan algo. Comprobarlo ANTES de
            # crear el tramo evita el fallo que costó media tanda: cualquier
            # línea suelta anterior al primer «N.º curso» —la portada, el
            # índice— creaba un tramo vacío bajo la clave -1, y `extraer` daba
            # la materia por «sin curso» y la descartaba entera. Bioloxía e
            # Xeoloxía tenía sus tres cursos bien leídos y aun así no se
            # guardaba.
            es_criterio = None if en_contidos else RX_CRITERIO.match(izq)
            if not en_contidos and not es_criterio:
                continue

            if curso == 0:
                # El PDF aún no ha dicho el curso: pasa en las materias cuyo
                # currículo es común a varios. `extraer` les pone los suyos.
                curso = -1
            tramo = tramos.setdefault((materia, curso), _Tramo())

            if en_contidos:
                _leer_contidos(izq, bloque_num, bloque_titulo, tramo)
            else:
                m = es_criterio
                tramo.criterios.append(Criterio(
                    codigo=f"{m.group(1)}.{m.group(2)}",
                    # El OBX que el propio decreto asocia al criterio. Aquí
                    # está la inversión: en las otras comunidades el
                    # criterio cuelga de la competencia; en Galicia es el
                    # criterio quien la nombra.
                    competencia=der.replace("OBX", "").strip() or "",
                    descripcion=_juntar(m.group(3)),
                ))
    return tramos


def _leer_contidos(celda: str, num: str, titulo: str, tramo: _Tramo) -> None:
    """Parte la celda de contidos en items.

    Todos los contidos de un bloque vienen en **una sola celda**, con dos
    niveles de viñeta: `▪` para un agrupador que termina en dos puntos, y `–`
    para cada item de dentro. Un `▪` que no termina en `:` es ya un contido.
    """
    bloque = tramo.bloques.setdefault(
        num, BloqueSaberes(codigo=num, titulo=titulo or f"Bloque {num}")
    )
    agrupador = ""
    # Se parte por las dos viñetas conservando cuál era, porque el nivel lo
    # marca el carácter y no la posición: aquí no hay que medir sangrados.
    for trozo in re.split(r"(?=[▪–])", celda):
        trozo = trozo.strip()
        if len(trozo) < 2:
            continue
        marca, texto = trozo[0], _juntar(trozo[1:])
        if not texto:
            continue
        if marca == "▪" and texto.endswith(":"):
            agrupador = texto.rstrip(":").strip()
            continue
        completo = f"{agrupador}: {texto}" if agrupador and marca == "–" else texto
        bloque.items.append(completo)
        bloque.codigos_items.append(f"{num}.{len(bloque.items)}")


# ---------------------------------------------------------------------------
# Montaje
# ---------------------------------------------------------------------------


#: Lo que trae la portada antes del nombre de la materia.
_PORTADA = ("CURRÍCULO", "Educación secundaria", "obrigatoria")


def titulo_de_portada(doc: pymupdf.Document) -> str:
    """El nombre de la materia, de la portada.

    La portada es «CURRÍCULO / Educación secundaria / obrigatoria / <Materia>»,
    y el nombre puede ocupar **más de una línea**: los ámbitos de
    diversificación salen como «Ámbito Científico e» + «Tecnolóxico». La
    primera versión cogía la línea de índice 2 y devolvía «obrigatoria» como
    nombre de materia para los dos ámbitos, que así se cargaban con un título
    que no existe.
    """
    lineas = [l.strip() for l in doc[0].get_text().split("\n") if l.strip()]
    resto = [l for l in lineas if l not in _PORTADA]
    return _juntar(" ".join(resto)) if resto else ""


def extraer(pdf: Path) -> list[MateriaCiclo]:
    """Un `MateriaCiclo` por cada (materia, curso) del PDF.

    **Puede devolver varias materias**: `Matematicas.pdf` trae Matemáticas,
    Matemáticas A y Matemáticas B, cada una con su «Materia de …».
    """
    doc = pymupdf.open(pdf)
    try:
        portada = titulo_de_portada(doc)
        obxectivos = extraer_obxectivos(doc)
        tramos = extraer_tramos(doc, portada)
    finally:
        doc.close()

    if not portada:
        logger.error("%s: no se reconoce la materia", pdf.name)
        return []
    if not obxectivos:
        logger.error("%s: sin obxectivos", portada)

    # Un tramo sin curso y **vacío** no significa que el PDF calle el curso:
    # significa que hubo alguna fila suelta antes del primero y no aportaba
    # nada. Descartarlo aquí evita dar por «sin curso» una materia bien leída.
    for clave in [k for k, v in tramos.items() if not (v.criterios or v.bloques)]:
        del tramos[clave]

    resultados: list[MateriaCiclo] = []
    for (materia, curso), tramo in sorted(tramos.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if curso in _CURSO:
            resultados.append(_montar(materia, [_CURSO[curso]], obxectivos, tramo))
            continue
        cursos = CURSOS_DE_LA_GUIA.get(materia) or _por_clave().get(_clave(materia))
        if not cursos:
            logger.error(
                "%s (%s): el PDF no dice el curso y no está en "
                "CURSOS_DE_LA_GUIA. Se cargaría invisible, así que no se "
                "guarda.", materia, pdf.name,
            )
            continue
        resultados.append(_montar(materia, cursos, obxectivos, tramo))
    return resultados


def _por_clave() -> dict[str, list[str]]:
    return {_clave(k): v for k, v in CURSOS_DE_LA_GUIA.items()}


def _montar(materia, cursos, obxectivos, tramo) -> MateriaCiclo:
    codigos = {o.codigo for o in obxectivos}
    huerfanos = sorted({c.competencia for c in tramo.criterios} - codigos - {""})
    if huerfanos:
        logger.warning(
            "%s %s: criterios que citan OBX inexistentes: %s",
            materia, cursos, ", ".join(huerfanos),
        )
    return MateriaCiclo(
        materia_oficial=materia,
        materia_corta=materia,
        ciclo=" e ".join(cursos),
        cursos_aplicables=list(cursos),
        competencias=list(obxectivos),
        criterios=list(tramo.criterios),
        saberes=[b for _, b in sorted(tramo.bloques.items(), key=lambda kv: int(kv[0]))],
    )


def _quitar_repetidas(todos: list[MateriaCiclo]) -> list[MateriaCiclo]:
    """Una sola entrada por (materia, cursos), quedándose con la más completa.

    POR QUÉ HAY REPETIDAS, Y POR QUÉ NO SE PUEDEN DEJAR. La Guía LOMLOE publica
    dos vistas del mismo currículo: el «completo» de una materia y el de esa
    materia **en un curso concreto**. Siete pares acaban en la misma
    ``(materia, cursos)`` —Bioloxía de 4.º, Matemáticas A, Música de 4.º…— y
    como el nombre del JSON se compone de esos dos datos, **el segundo pisaba
    al primero en silencio**: salían 67 bloques y 60 ficheros, y nadie lo veía
    porque el recuento que se imprimía era el de bloques.

    Los criterios coinciden en los siete pares, así que la duplicidad es real y
    no un fallo de lectura. Lo que cambia son los contidos: Matemáticas A saca
    179 desde su PDF propio y 81 desde el completo. Se conserva **el que más
    trae**, porque el otro está perdiendo contenido, y se dice cuál se
    descarta: si algún día la diferencia fuera al revés, conviene enterarse.
    """
    mejor: dict[tuple[str, tuple[str, ...]], MateriaCiclo] = {}
    for mc in todos:
        clave = (mc.materia_efectiva, tuple(mc.cursos_aplicables))
        actual = mejor.get(clave)
        if actual is None:
            mejor[clave] = mc
            continue
        n_nuevo = sum(len(b.items) for b in mc.saberes)
        n_actual = sum(len(b.items) for b in actual.saberes)
        if n_nuevo > n_actual:
            mejor[clave] = mc
        logger.info(
            "%s %s aparece en dos PDF (%d y %d contidos): se conserva el de %d",
            clave[0], list(clave[1]), n_actual, n_nuevo, max(n_actual, n_nuevo),
        )
    return list(mejor.values())


def volcar(resultados: list[MateriaCiclo], salida: Path, comunidad: str,
           idioma: str) -> list[Path]:
    """Un JSON por (materia, cursos), con la comunidad y el idioma dentro."""
    salida.mkdir(parents=True, exist_ok=True)
    escritos = []
    for mc in resultados:
        d = mc.to_dict()
        d["comunidad"] = comunidad
        d["idioma"] = idioma
        d["saberes_basicos"] = [
            {
                "codigo": b.codigo,
                "bloque": f"Bloque {b.codigo}. {b.titulo}",
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
    retirar_huerfanos(salida, escritos)
    return escritos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdfs", type=Path, required=True,
                   help="Carpeta con los PDF por materia (curriculo/fuentes/galicia)")
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--comunidad", default="galicia")
    p.add_argument("--idioma", default="gl")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s | %(message)s")

    pdfs = sorted(args.pdfs.glob("*.pdf"))
    if not pdfs:
        logger.error("No hay PDF en %s", args.pdfs)
        return 2

    todos: list[MateriaCiclo] = []
    for pdf in pdfs:
        res = extraer(pdf)
        if not res:
            logger.warning("Sin resultados: %s", pdf.name)
        todos.extend(res)

    todos = _quitar_repetidas(todos)

    escritos = volcar(todos, args.salida, args.comunidad, args.idioma)
    materias = {mc.materia_efectiva for mc in todos}
    print(f"\n{len(pdfs)} PDF -> {len(materias)} materias, {len(todos)} bloques, "
          f"{len(escritos)} ficheros en {args.salida}")
    for mc in sorted(todos, key=lambda m: (m.materia_efectiva, m.ciclo)):
        print(f"  {mc.materia_efectiva:46s} {mc.ciclo:22s} "
              f"OBX={len(mc.competencias):2d} crit={len(mc.criterios):3d} "
              f"cont={sum(len(b.items) for b in mc.saberes):3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
