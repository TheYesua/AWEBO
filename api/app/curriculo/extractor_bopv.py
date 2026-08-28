"""Extractor del currículo vasco (Decreto 77/2023), desde el PDF del Anexo III.

DE DÓNDE SALE EL FICHERO
-------------------------
De ``curriculo/fuentes/pais-vasco/``, descargado con
``docs/scripts/descargar-pais-vasco.cmd``. La fuente es **Berrigasteiz**, el
portal del Berritzegune del Gobierno Vasco, y no el BOPV, por dos razones:

* su copia lleva **la corrección de errores del 31/07/2023 ya incorporada**
  (`_ZUZENDUTA`), mientras que en el boletín es un documento aparte;
* está **solo en euskera**. El BOPV publica en columnas paralelas
  euskera/castellano y habría que separarlas; aquí ya vienen separadas.
  Comprobado: 377 páginas, ninguna con cabecera castellana.

POR QUÉ DEL DECRETO ENTERO Y NO DE LOS PDF POR MATERIA
-------------------------------------------------------
Berrigasteiz publica **también** un PDF por materia, como la XTEC y la Xunta, y
la tentación era usarlos. No se hace, y el motivo es lo que costó Galicia: allí
siete materias salían en dos PDF distintos y el JSON de una pisaba al de la
otra, en silencio.

Con un único documento ese problema no existe: cada materia aparece una vez y
solo una, porque el Anexo III es una lista. Los 30 PDF sueltos se usan para
**contrastar** —``comprobar_contra_los_pdf_sueltos``—, que es donde de verdad
valen: si el extractor saca 30 materias y hay 30 ficheros, cuadra.

EL VOCABULARIO NO CAMBIA, Y ESO ES LA BUENA NOTICIA
-----------------------------------------------------
====================== ============================== ======================
LOMLOE estándar        País Vasco (euskera)           Se guarda como
====================== ============================== ======================
Competencia específica **Konpetentzia espezifikoa**   `CompetenciaEspecifica`
Criterio de evaluación **Ebaluazio-irizpidea**        `Criterio`
Saber básico           **Oinarrizko jakintza**        `BloqueSaberes.items`
Materia                Ikasgaia / jakintzagaia        —
====================== ============================== ======================

Es traducción literal, al revés que Galicia —donde «obxectivo» ocupaba el lugar
de la competencia específica y hubo que **invertir** la relación
criterio→competencia—. Aquí los criterios cuelgan de su competencia con código
`N.M`, igual que en el BOE y en el BOJA, así que no hay nada que invertir.

LO QUE SÍ HA COSTADO
---------------------
1. **`III ERANSKINA` va sin punto** tras la cifra, mientras que `II.` y `IV.`
   lo llevan. Buscarlo con la forma regular no lo encuentra, y el anexo que
   interesa es justo ese.
2. **El enunciado de una competencia y su explicación no se distinguen por el
   texto ni por la fuente**: los dos son Arial 11 sin negrita. Lo que sí los
   separa es la **sangría** —enunciado en `x≈54`, explicación en `x≈48`—, que
   es el mismo análisis posicional que hizo falta con la XTEC.
3. **Los criterios y los saberes van en tablas de dos columnas**, una por
   ciclo, en 69 de las 226 páginas del anexo. La primera versión los leyó como
   texto corrido y el resultado fue verde y falso: las dos columnas mezcladas,
   Matemáticas con 249 saberes y seis materias con cero criterios. Es la misma
   lección que dio Galicia, con los papeles cambiados: allí la máquina de
   estados solo miraba tablas y se perdía lo de fuera.
4. **Los cursos salen de la cabecera de esas tablas** —«Lehen eta bigarren
   mailak»— cuando la materia se imparte en varios. Las que no la traen se
   resuelven con la tabla del artículo 13; ver `CURSOS_DEL_ARTICULADO`.
5. **El boletín marca los bloques de saberes de cinco formas distintas** —ver
   `RX_BLOQUE` y `RX_BLOQUE_MULTZOA`—, incluida una con número en vez de letra
   y sin espacio tras el punto. Las cinco son del mismo decreto y algunas de
   páginas contiguas.
6. **El código del criterio lleva punto final unas veces y otras no**: `1.1.`
   en Teknologia y `1.1` en Heziketa Fisikoa.
7. **Las tablas de saberes van a dos niveles**: la primera columna es un
   subapartado numerado y la segunda los saberes que cuelgan de él. Leídas de
   corrido, el título se pegaba al primer saber —157 casos en 12 materias— y
   eso llegó al documento del docente. Ver `_subapartado`.

EL ASTERISCO DE LOS SABERES: BUSCADO Y NO ENCONTRADO
-----------------------------------------------------
Muchos saberes llevan un `*`. Se buscó su leyenda el 27/08 en el articulado,
en los seis anexos y fuera del decreto, y **no existe**. Los dos asteriscos que
sí están explicados son otros: el del artículo 13 marca las optativas de oferta
obligatoria, y el `**` del Anexo VI, casillas de horario sin mínimo.

Lo que sí se sabe, por si algún día sirve:

* Va **al final del saber en todas las materias salvo en Lengua**, donde va al
  principio. Son dos maquetaciones del mismo signo, no dos signos.
* Está en el **26 %** de los saberes.

Esa proporción encaja mejor con «añadido propio del País Vasco» que con
«mínimo del Estado», pero es una conjetura y **por eso no se usa**. El
asterisco se retira del texto sin atribuirle significado, que es lo honesto:
elegir una de las tres lecturas posibles sería inventarla.

Si algún día aparece la leyenda, reextraer cuesta un minuto — el PDF no
cambia.
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


logger = logging.getLogger("curriculo.extractor_bopv")


# ---------------------------------------------------------------------------
# Reconocimiento
# ---------------------------------------------------------------------------

#: «III ERANSKINA», **sin punto tras la cifra**. Los anexos II y IV sí lo
#: llevan, así que una expresión que lo exija encuentra todos menos el único
#: que hace falta. El punto va opcional a propósito, para que siga valiendo si
#: alguna reedición lo normaliza.
RX_ERANSKINA = re.compile(r"^\s*([IVX]+)\.?\s*ERANSKINA?\s*$", re.I)

#: Encabezados de sección dentro de cada materia. El del criterio va con guion
#: y sin él —«EBALUAZIO-IRIZPIDEAK» en casi todas, «EBALUAZIO IRIZPIDEAK» en
#: Biologia eta Geologia—, y el de competencias aparece en singular en las
#: materias que solo tienen una.
RX_SEC_COMPETENCIAS = re.compile(r"^KONPETENTZIA\s+ESPEZIFIKOAK?$", re.I)
RX_SEC_CRITERIOS = re.compile(r"^EBALUAZIO[\s\-]IRIZPIDEAK$", re.I)
RX_SEC_SABERES = re.compile(r"^OINARRIZKO\s+JAKINTZAK$", re.I)

#: «1. Hainbat iturritatik datorren informazio…» y «1.Adierazpen kulturalak…»:
#: el espacio tras el punto **también es opcional**. Sin contemplarlo,
#: Adierazpide Artistikoaren Hastapenak salía con tres competencias en vez de
#: cinco y sus criterios 1.1 y 1.2 apuntaban a una que no existía.
#:
#: El `(?!\d)` es imprescindible: sin él «1.1 Planteatutako…» se leería como la
#: competencia 1 con descripción «1 Planteatutako…».
RX_COMPETENCIA = re.compile(r"^(\d{1,2})\.\s*(?!\d)(.+)$", re.DOTALL)

#: «Konpetentzia espezifiko hau irteera-profilaren deskriptore hauekin lotzen
#: da: HKK3, STEM2…» — cierra la competencia y da sus descriptores. Es el único
#: marcador inequívoco de dónde acaba una y empieza la siguiente.
RX_DESCRIPTORES = re.compile(r"deskriptore\s+hauekin\s+lotzen\s+da\s*:", re.I)

#: «1. konpetentzia espezifikoa» — dentro de los criterios, dice a qué
#: competencia pertenecen los que vienen debajo.
RX_CRIT_CABECERA = re.compile(r"^(\d{1,2})\.\s*konpetentzia\s+espezifikoa$", re.I)

#: «1.1. Planteatutako problemak…» y «1.1 Osasunaren kontzeptu…». El punto
#: tras el segundo número **va opcional porque el boletín no es constante**:
#: Teknologia lo pone y Heziketa Fisikoa no. Exigirlo dejaba seis materias con
#: cero criterios, y sin error: simplemente no casaba ninguna línea.
RX_CRITERIO = re.compile(r"^(\d{1,2})\.(\d{1,2})\.?\s+(.+)$", re.DOTALL)

#: Bloque de saberes, en las **cuatro** formas que usa el decreto:
#:
#:   A. Problemak ebazteko prozesua              (Teknologia)
#:   A. HIZKUNTZAK ETA BEREN HIZTUNAK.           (Lengua, en mayúsculas)
#:   D multzoa. Aurkaritza-egoerak               (Heziketa Fisikoa)
#:   1. multzoa.Zientzia eta informazio zientifikoa   (Kultura Zientifikoa)
#:
#: La cuarta lleva **número en vez de letra y no deja espacio tras el punto**.
#: Cada una se descubrió por una materia que salía con cero saberes y sin dar
#: ningún error, que es como se presentan siempre estos fallos.
#:
#: La letra o el número son del decreto, así que el código del bloque es
#: oficial —como en Galicia lo era el número—; los saberes de dentro no llevan
#: código propio.
RX_BLOQUE = re.compile(r"^([A-Z])\.\s+(.+?)\.?\s*$")
#: `multzoa` y `multzoak`: la quinta forma es la misma en plural, y aparece en
#: una sola materia.
RX_BLOQUE_MULTZOA = re.compile(r"^([A-Z0-9])\.?\s*multzoak?\.\s*(.+?)\.?\s*$", re.I)

#: Viñetas con las que el decreto abre algunos saberes. No aportan nada al
#: docente y estorban al emparejar lo que cita el modelo.
RX_VINETA = re.compile(r"^[–—\-•▪]\s*")

#: «DBHko 4. mailako oinarrizko jakintzak» — Biologia eta Geologia y Fisika eta
#: Kimika separan así sus saberes, fuera de tabla.
RX_SABERES_DE_CURSO = re.compile(
    r"^DBHko\s+(\d)\.\s*mailako\s+oinarrizko\s+jakintzak$", re.I
)

#: Cabecera de ciclo de las tablas: «Lehen eta bigarren mailak»,
#: «Hirugarren maila»… Es de donde salen los cursos de las materias que se
#: imparten en varios, que son la mayoría de las obligatorias.
#: El orden importa: «lehenengo» empieza por «lehen», así que se prueba antes
#: el largo para no partirlo.
_ORDINALES_EU = (
    ("lehenengo", 1), ("lehen", 1), ("bigarren", 2),
    ("hirugarren", 3), ("laugarren", 4),
)

#: Los cursos en romanos, tal como los escribe Atzerriko Bigarren Hizkuntza.
_ROMANOS = {"I": 1, "II": 2, "III": 3, "IV": 4}

#: La cabecera tiene que **nombrar el curso** para que esto sea una cabecera de
#: ciclo y no una frase cualquiera que empiece por un ordinal.
RX_TIENE_MAILA = re.compile(r"\bmaila", re.I)


#: «Laugarren maila A matematika» — el itinerario de 4.º, que en el País Vasco
#: va dentro de la propia cabecera de la columna.
#: El separador entre «maila» y la letra **es a veces un espacio y a veces un
#: punto**: «Laugarren maila A matematika» en la tabla de criterios y
#: «Laugarren maila. A matematika» en la de saberes, en la misma materia.
#: Exigir solo el espacio dejaba los 114 saberes de cuarto en un tramo sin
#: itinerario, y A y B con cero.
RX_ITINERARIO = re.compile(r"\bmaila\.?\s+([AB])\.?\s+matematika\b", re.I)


def ciclo_de_cabecera(t: str) -> tuple[list[str], str] | None:
    """Cursos e itinerario de una cabecera de columna, o `None` si no lo es.

    Reconoce las tres formas que usa el decreto, y las dos últimas aparecieron
    tarde, cada una por una materia que salía mal **sin dar ningún error**:

    * enumeración — «Lehen eta bigarren mailak», «Laugarren maila»;
    * **rango** — «Lehen mailatik hirugarrenera», de primero a tercero. Solo
      Musika lo usa, y mientras no se reconoció su columna de 1.º a 3.º se
      acumulaba en el tramo de 4.º: la materia entera salía como de cuarto;
    * **itinerario** — «Laugarren maila A matematika». Son las Matemáticas A y
      B de 4.º, y sin distinguirlas las dos columnas caían en el mismo tramo y
      quedaban fundidas en una materia con el doble de criterios.
    """
    t = _limpiar(t)
    itinerario = ""
    m = RX_ITINERARIO.search(t)
    if m:
        itinerario = m.group(1).upper()
    if len(t) > 60 or not RX_TIENE_MAILA.search(t):
        return None

    bajo = t.lower()

    # Los cursos van a veces en **números romanos**: «I. eta II. mailak». Solo
    # lo hace Atzerriko Bigarren Hizkuntza, y mientras no se reconoció sus dos
    # ciclos caían en el mismo tramo: 32 criterios con 17 códigos distintos,
    # cada uno repetido, y ningún error.
    romanos = re.findall(r"\b(IV|III|II|I)\.", t)
    if romanos:
        nums = sorted({_ROMANOS[r] for r in romanos})
        return [f"{n}º ESO" for n in nums], itinerario

    encontrados: list[int] = []
    # Se recorre la frase palabra a palabra para conservar el orden en que
    # aparecen, que es lo que distingue «de primero a tercero» de «tercero a
    # primero» —esta última no existe, pero el rango se construye del primero
    # al último y conviene no depender de que estén ordenados—.
    for token in re.split(r"\s+", bajo):
        for palabra, n in _ORDINALES_EU:
            if token.startswith(palabra):
                encontrados.append(n)
                break
    if not encontrados:
        return None

    if "mailatik" in bajo and len(encontrados) >= 2:
        ini, fin = encontrados[0], encontrados[-1]
        nums = range(min(ini, fin), max(ini, fin) + 1)
    else:
        nums = sorted(set(encontrados))
    return [f"{n}º ESO" for n in nums], itinerario


def cursos_de_ciclo(t: str) -> list[str] | None:
    """Solo los cursos, para quien no necesita el itinerario."""
    r = ciclo_de_cabecera(t)
    return r[0] if r else None

#: Cabecera y pie del boletín, repetidos en cada página. Se filtran por texto
#: y no por posición porque el PDF de Berrigasteiz recorta los márgenes de
#: forma distinta al del BOPV.
RX_RUIDO = (
    re.compile(r"^\d+\.\s*zk\.$"),
    re.compile(r"^EUSKAL HERRIKO AGINTARITZAREN ALDIZKARIA$", re.I),
    re.compile(r"^\d{4}ko\s+\w+(\s+\w+)?\s+\d{1,2},?\s*\w*$", re.I),
    re.compile(r"^\d{4}/\d+\s*\(\d+/\d+\)$"),
)

#: Sangría que separa el enunciado de una competencia de su explicación. El
#: enunciado va en x≈53.9 y la explicación en x≈48.2; el umbral se pone en
#: medio con margen de sobra. **No se puede usar la fuente**: las dos son
#: Arial 11 sin negrita, comprobado span a span.
X_SANGRADO = 51.0


# ---------------------------------------------------------------------------
# Los cursos, que no están en el Anexo III
# ---------------------------------------------------------------------------

#: Cursos de cada materia, **transcritos de la tabla del artículo 13** del
#: propio decreto (apartados 3 y 5). No es una tabla de excepciones como la de
#: Cataluña ni una lista sacada de una web como la de Galicia: es normativa, y
#: está en el mismo documento del que se extrae todo lo demás.
#:
#: La clave es el título tal como aparece en el **Anexo III**, y ahí está la
#: única dificultad: el articulado y el anexo **llaman distinto a la misma
#: materia** en cinco casos, y no por erratas sino por sinonimia del euskera.
#:
#: ==================================== ==============================
#: Artículo 13                          Anexo III
#: ==================================== ==============================
#: Gorputz Hezkuntza                    HEZIKETA FISIKOA
#: Matematika Lantegia                  MATEMATIKA TAILERRA
#: Ongizate Fisikoa eta Emozionala      OSASUN FISIKOA ETA EMOZIONALA
#: Pentsamendu kritiko … hastapenak     PENTSAMENDU … GARAPENA
#: Balio Zibiko eta Etikoak             BALIO ZIBIKO ETA ETIKOETAKO HEZIKETA
#: ==================================== ==============================
#:
#: El emparejamiento se comprobó contra los nombres de los PDF por materia de
#: Berrigasteiz, que llevan los cursos dentro (`DBHA123_ongizate…` → 1.º a 3.º,
#: `DBH8_bio_geo_3_4` → 3.º y 4.º). Coinciden en los siete casos en que el
#: nombre del fichero los declara, y eso es lo que convierte la lectura del
#: artículo en algo comprobado y no en una interpretación mía.
CURSOS_DEL_ARTICULADO: dict[str, list[str]] = {
    # --- Comunes a todos los alumnos ---
    "EUSKARA ETA LITERATURA ETA GAZTELANIA ETA LITERATURA": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "ATZERRIKO LEHEN HIZKUNTZA": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "MATEMATIKA": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "GEOGRAFIA ETA HISTORIA": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "HEZIKETA FISIKOA": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "NATURA ZIENTZIAK": ["1º ESO", "2º ESO"],
    "BALIO ZIBIKO ETA ETIKOETAKO HEZIKETA": ["1º ESO"],
    "TEKNOLOGIA ETA DIGITALIZAZIOA": ["2º ESO", "3º ESO"],
    "BIOLOGIA ETA GEOLOGIA": ["3º ESO", "4º ESO"],
    "FISIKA ETA KIMIKA": ["3º ESO", "4º ESO"],

    # Artículo 13.3, última fila: «Musika eta/edo Hezkuntza Plastikoa eta
    # Ikus-entzunezkoa», obligatoria de 1.º a 3.º. Musika sale además como
    # materia de opción en 4.º (13.5); Plastika no.
    "MUSIKA": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "HEZKUNTZA PLASTIKOA, IKUSIZKOA ETA IKUS-ENTZUNEZKOA": ["1º ESO", "2º ESO", "3º ESO"],

    # --- Optativas de 1.º a 3.º (artículo 13.3) ---
    "OSASUN FISIKOA ETA EMOZIONALA": ["1º ESO", "2º ESO", "3º ESO"],
    "ATZERRIKO BIGARREN HIZKUNTZA": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "TEKNOLOGIAKO ETA DIGITALIZAZIOKO HASTAPENAK": ["1º ESO"],
    "PENTSAMENDU AUTONOMOAREN ETA KRITIKOAREN GARAPENA": ["2º ESO", "3º ESO"],
    "KULTURA KLASIKOA": ["3º ESO"],
    "KULTURA ZIENTIFIKOA, DBHKO 3. MAILA": ["3º ESO"],
    "ADIERAZPIDE ARTISTIKOAREN HASTAPENAK": ["3º ESO"],

    # --- Cuarto: materias de opción y optativas (artículo 13.5) ---
    "LATINA": ["4º ESO"],
    "DIGITALIZAZIOA": ["4º ESO"],
    "ADIERAZPEN ARTISTIKOA": ["4º ESO"],
    "TEKNOLOGIA": ["4º ESO"],
    "PRESTAKUNTZA ETA ORIENTAZIO PERTSONALA ETA PROFESIONALA": ["4º ESO"],
    "EKONOMIA ETA EKINTZAILETZA": ["4º ESO"],
    "ARTE ESZENIKOAK": ["4º ESO"],
    "KULTURA ZIENTIFIKOA, DBHKO 4. MAILA": ["4º ESO"],
    "LANBIDE-JARDUERARI APLIKATUTAKO ZIENTZIAK": ["4º ESO"],
    "MATEMATIKA TAILERRA": ["4º ESO"],
    "GARAPEN PERTSONALARI ETA SOZIALARI APLIKATUTAKO FILOSOFIA": ["4º ESO"],
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def _clave(s: str) -> str:
    """Normaliza para comparar títulos: sin tildes, sin dobles espacios."""
    s = unicodedata.normalize("NFKD", s.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s)


def _limpiar(t: str) -> str:
    """Quita el guion blando y normaliza espacios.

    El PDF usa U+00AD para partir palabras al final de línea —«esperi\xadmentatuz»—.
    Si no se retira, las palabras quedan cortadas dentro del texto ya unido, y
    el docente ve «esperimentatuz» escrito con un carácter invisible en medio
    que rompe cualquier búsqueda.
    """
    return re.sub(r"\s+", " ", t.replace("\xad", "")).strip()


def _unir(fragmentos: list[str]) -> str:
    """Une líneas deshaciendo la partición de palabras.

    El PDF parte con un **guion normal** (U+002D) y no con el guion blando, así
    que juntar con espacios deja «esperi- mentatuz» dentro del texto: se ve mal
    en el documento del docente y rompe cualquier búsqueda.

    LO QUE ESTO PUEDE ESTROPEAR, dicho para que conste. Si una palabra
    compuesta se parte justo en su propio guion —«jakintza-gai»— se pierde ese
    guion y queda «jakintzagai». No hay forma de distinguir los dos casos
    mirando solo el texto, y se elige este lado porque el resultado sigue
    siendo una palabra legible, mientras que el otro deja basura visible en
    todas las líneas largas.
    """
    if not fragmentos:
        return ""
    salida = fragmentos[0]
    for f in fragmentos[1:]:
        if salida.endswith("-") and f[:1].islower():
            salida = salida[:-1] + f
        else:
            salida = f"{salida} {f}"
    return re.sub(r"\s+", " ", salida).strip()


def _es_ruido(t: str) -> bool:
    return any(rx.match(t) for rx in RX_RUIDO)


@dataclass
class _Linea:
    """Una línea de texto suelto, con su sangría."""
    texto: str
    x0: float

    @property
    def sangrada(self) -> bool:
        return self.x0 >= X_SANGRADO


@dataclass
class _Tabla:
    """Filas x columnas x **líneas** de la celda.

    Las líneas de dentro de una celda no se aplanan: en los saberes marcan
    dónde empieza cada uno, y unirlas dejaría el bloque entero como un solo
    saber de mil palabras."""
    filas: list[list[list[str]]]


def _paginas_del_anexo(doc: pymupdf.Document) -> tuple[int, int]:
    """Delimita el Anexo III por sus propios encabezados.

    Y no por números de página, que cambiarían con cualquier reedición.
    """
    inicio = fin = None
    for i, pagina in enumerate(doc):
        for linea in pagina.get_text().split("\n"):
            m = RX_ERANSKINA.match(_limpiar(linea))
            if not m:
                continue
            if m.group(1).upper() == "III" and inicio is None:
                inicio = i
            elif m.group(1).upper() == "IV" and inicio is not None and fin is None:
                fin = i
    if inicio is None:
        raise ValueError("No se encuentra «III ERANSKINA» en el documento")
    return inicio, fin if fin is not None else len(doc)


def elementos_del_anexo(doc: pymupdf.Document) -> list[_Linea | _Tabla]:
    """Tablas y texto suelto del Anexo III, **ordenados por su posición**.

    Es lo mismo que hizo falta en Galicia y por el motivo contrario. Allí la
    máquina de estados solo miraba tablas y se perdían las cabeceras de curso,
    que van fuera; aquí la primera versión solo miró texto y se perdieron los
    criterios y los saberes, que van dentro. En los dos casos la solución es la
    misma: no elegir entre una cosa y otra, sino recorrer las dos en el orden
    en que están sobre el papel.

    Sin esto el texto de una tabla de dos columnas sale intercalado —criterio
    del primer ciclo, criterio del segundo, criterio del primero…— y el
    resultado es verde y falso.
    """
    inicio, fin = _paginas_del_anexo(doc)
    logger.info("Anexo III: páginas %d a %d", inicio + 1, fin)

    salida: list[_Linea | _Tabla] = []
    for i in range(inicio, fin):
        pagina = doc[i]
        elementos: list[tuple[float, _Linea | _Tabla]] = []

        tablas = pagina.find_tables().tables
        zonas = [t.bbox for t in tablas]
        for t in tablas:
            filas = [[[_limpiar(x) for x in (c or "").split(chr(10))]
                      for c in fila] for fila in t.extract()]
            elementos.append((t.bbox[1], _Tabla(filas)))

        for bloque in pagina.get_text("dict")["blocks"]:
            for ln in bloque.get("lines", []):
                y = ln["bbox"][1]
                # Lo que cae dentro de una tabla ya se ha recogido como celda.
                if any(z[1] - 2 <= y <= z[3] + 2 for z in zonas):
                    continue
                t = _limpiar("".join(s["text"] for s in ln["spans"]))
                if t and not _es_ruido(t):
                    elementos.append((y, _Linea(t, ln["bbox"][0])))

        salida.extend(e for _, e in sorted(elementos, key=lambda p: p[0]))
    return salida


def _es_titulo_de_materia(t: str) -> bool:
    """Un título del Anexo III va en mayúsculas y en su propia línea.

    Hay que descartar los descriptores del perfil —«STEM4, KD1, KPSII5.»—, que
    también son mayúsculas sueltas y estuvieron a punto de colarse como
    materias. Se distinguen porque son siglas con dígitos separadas por comas.
    """
    if len(t) < 5 or t != t.upper():
        return False
    if not re.match(r"^[A-ZÁÉÍÓÚÜÑ]", t):
        return False
    if re.search(r"\d", t) and "MAILA" not in t.upper():
        return False       # descriptores: «STEM4, KD1, KPSII5.»
    if RX_SEC_COMPETENCIAS.match(t) or RX_SEC_CRITERIOS.match(t):
        return False
    if RX_SEC_SABERES.match(t) or RX_ERANSKINA.match(t):
        return False
    # En Lengua los bloques de saberes van EN MAYÚSCULAS —«A. HIZKUNTZAK ETA
    # BEREN HIZTUNAK.»—, así que sin esto se cuelan como materias: la primera
    # versión inventó cuatro y dejó a Lengua sin ningún saber.
    if RX_BLOQUE.match(t) or RX_BLOQUE_MULTZOA.match(t):
        return False
    if cursos_de_ciclo(t):
        return False
    return "DERRIGORREZKO BIGARREN HEZKUNTZAKO JAKINTZAGAIAK" not in t


# ---------------------------------------------------------------------------
# Montaje
# ---------------------------------------------------------------------------


#: Clave de un tramo: los cursos y el itinerario. La tupla vacía y la cadena
#: vacía significan «el boletín no lo declara», que es el caso de las materias
#: de un solo curso y de todas las que no son Matemáticas.
_Clave = tuple[tuple[str, ...], str]

SIN_CICLO: _Clave = ((), "")


@dataclass
class _Tramo:
    """Lo que una materia tiene para un ciclo e itinerario concretos."""
    clave: _Clave
    criterios: list[Criterio] = field(default_factory=list)
    saberes: list[BloqueSaberes] = field(default_factory=list)


@dataclass
class _Materia:
    titulo: str
    #: Las competencias específicas son **comunes a todos los ciclos**: el
    #: decreto las enuncia una vez, antes de partir en columnas.
    competencias: list[CompetenciaEspecifica] = field(default_factory=list)
    tramos: dict[_Clave, _Tramo] = field(default_factory=dict)

    def tramo(self, clave: _Clave) -> _Tramo:
        return self.tramos.setdefault(clave, _Tramo(clave))


class _Parser:
    """Máquina de estados sobre los elementos del anexo, en orden de lectura.

    Los acumuladores van **por tramo** y no en variables sueltas porque en una
    tabla de dos columnas las celdas llegan alternadas —primer ciclo, segundo
    ciclo, primer ciclo…—. Con un único acumulador, un saber del segundo ciclo
    cerraría el del primero y las dos columnas acabarían mezcladas, que es
    exactamente lo que hacía la primera versión.
    """

    def __init__(self) -> None:
        self.materias: list[_Materia] = []
        self.act: _Materia | None = None
        self.estado = "fuera"
        #: Ciclo vigente para el texto suelto. Las tablas traen el suyo.
        self.clave: _Clave = SIN_CICLO
        # competencia en curso (comunes a la materia, nunca en tabla)
        self.cod_ce: str | None = None
        self.buf_ce: list[str] = []
        # por tramo
        self.comp: dict[tuple, str] = {}
        self.cod_cr: dict[tuple, str] = {}
        self.buf_cr: dict[tuple, list[str]] = {}
        self.bloque: dict[tuple, BloqueSaberes | None] = {}
        #: Bloque de primer nivel de cada tramo. Hace falta aparte porque
        #: `self.bloque` pasa a apuntar al subapartado en cuanto se abre uno, y
        #: el siguiente tiene que volver a colgar del mismo padre.
        self._padres: dict[tuple, BloqueSaberes | None] = {}
        self.buf_sb: dict[tuple, list[str]] = {}

    # -- cierres ---------------------------------------------------------
    def _cerrar_ce(self) -> None:
        if self.act is not None and self.cod_ce and self.buf_ce:
            self.act.competencias.append(CompetenciaEspecifica(
                codigo=self.cod_ce, descripcion=_unir(self.buf_ce)))
        self.cod_ce, self.buf_ce = None, []

    def _cerrar_cr(self, cursos: _Clave) -> None:
        cod, buf = self.cod_cr.get(cursos), self.buf_cr.get(cursos)
        if self.act is not None and cod and buf:
            self.act.tramo(cursos).criterios.append(Criterio(
                codigo=cod, competencia=self.comp.get(cursos, ""),
                descripcion=_unir(buf)))
        self.cod_cr[cursos], self.buf_cr[cursos] = "", []

    def _cerrar_sb(self, cursos: _Clave) -> None:
        b, buf = self.bloque.get(cursos), self.buf_sb.get(cursos)
        if b is not None and buf:
            b.items.append(_unir(buf).rstrip("*").strip())
        self.buf_sb[cursos] = []

    def _cerrar_todo(self) -> None:
        self._cerrar_ce()
        for c in list(self.cod_cr):
            self._cerrar_cr(c)
        for c in list(self.bloque):
            self._cerrar_sb(c)

    # -- entrada ---------------------------------------------------------
    def procesar(self, elementos: list) -> list[_Materia]:
        for e in elementos:
            if isinstance(e, _Tabla):
                self._tabla(e)
            else:
                self._linea(e.texto, e.sangrada, self.clave)
        self._cerrar_todo()
        return self.materias

    def _tabla(self, tabla: _Tabla) -> None:
        if not tabla.filas:
            return
        cabecera = [ciclo_de_cabecera(" ".join(c)) for c in tabla.filas[0]]

        # Las columnas solo son paralelas si **todas** declaran su ciclo. Una
        # cabecera como `['Lehen eta bigarren mailak', '']` no parte la tabla
        # en dos: dice que toda ella es de primero y segundo, y la segunda
        # columna es la continuación de la fila. Tratarla como paralela
        # duplicaba cada saber en dos tramos —Matemáticas salía con 251 en
        # cada uno—, y sin ningún error, porque los dos JSON eran válidos.
        paralelas = len(cabecera) > 1 and all(cabecera)
        if paralelas:
            por_columna = [((tuple(c[0]), c[1]) if c else self.clave)
                           for c in cabecera]
            filas = tabla.filas[1:]
        else:
            por_columna = None
            filas = tabla.filas
            if cabecera and cabecera[0]:
                self.clave = (tuple(cabecera[0][0]), cabecera[0][1])
                filas = tabla.filas[1:]

        for fila in filas:
            # Tabla de saberes a dos niveles: la primera columna es un
            # **subapartado numerado** —«1. Zenbaketa»— y la segunda los
            # saberes que cuelgan de él. Se reconoce porque las dos columnas
            # traen contenido en la misma fila y la tabla no está partida por
            # ciclos.
            #
            # Sin esto el título del subapartado se pegaba al primer saber y el
            # docente leía «3. Eragiketen zentzua Eragiketa aritmetikoen
            # propietateak…» en su documento. Eran 157 saberes en 12 materias, y
            # no dio ningún error: el JSON era válido y el recuento cuadraba.
            if (self.estado == "saberes" and not paralelas and len(fila) >= 2
                    and any(l.strip() for l in fila[0])
                    and any(l.strip() for c in fila[1:] for l in c)):
                self._subapartado(fila[0], self.clave)
                celdas = list(enumerate(fila))[1:]
            else:
                celdas = list(enumerate(fila))

            for i, celda in celdas:
                if not any(l.strip() for l in celda):
                    continue
                clave = por_columna[i] if por_columna and i < len(por_columna) \
                    else self.clave
                # Una celda que abarca las dos columnas —«1. konpetentzia
                # espezifikoa»— se reconoce porque las demás vienen vacías: se
                # aplica a todos los ciclos de la tabla, no solo al primero.
                destinos = [clave]
                if paralelas and i == 0 and not any(
                        any(c.strip() for c in fila[j])
                        for j in range(1, len(fila))):
                    destinos = list(dict.fromkeys(por_columna))
                for d in destinos:
                    for linea in celda:
                        if linea.strip() and not _es_ruido(linea):
                            self._linea(linea, True, d)

    def _subapartado(self, celda: list[str], clave: _Clave) -> None:
        """Abre un bloque hijo a partir del subapartado numerado de la columna.

        Se crea un `BloqueSaberes` propio en vez de descartar el título o de
        pegarlo al primer saber. El código sale entero del decreto —la letra
        del bloque y el número del subapartado, `A.1`— así que sigue siendo
        citable, y el docente ve «Zentzu numerikoa · Zenbaketa», que es lo que
        dice la norma.

        Descartarlo habría sido más simple y habría perdido un nivel de la
        organización del currículo.
        """
        titulo = _unir([l for l in celda if l.strip()])
        if not titulo:
            return
        self._cerrar_sb(clave)

        m = re.match(r"^(\d{1,2})\.\s*(.+?)\.?\s*$", titulo)
        padre = self.bloque.get(clave)
        # `_padres` guarda el bloque de primer nivel de cada tramo, porque
        # `self.bloque` pasa a apuntar al hijo y el siguiente subapartado
        # necesita volver a colgar del mismo padre.
        raiz = self._padres.get(clave) or padre
        if raiz is None or not m:
            # Sin bloque padre no hay a qué colgarlo: se trata como un saber
            # más, que es lo que era antes de este arreglo.
            self.buf_sb.setdefault(clave, []).append(titulo)
            return

        self._padres[clave] = raiz
        hijo = BloqueSaberes(
            codigo=f"{raiz.codigo}.{m.group(1)}",
            titulo=f"{raiz.titulo} · {_limpiar(m.group(2))}",
        )
        self.act.tramo(clave).saberes.append(hijo)
        self.bloque[clave] = hijo

    # -- el reconocedor, común a texto y a celda -------------------------
    def _linea(self, t: str, sangrada: bool, cursos: _Clave) -> None:  # noqa: C901
        if _es_titulo_de_materia(t):
            self._cerrar_todo()
            self.act = _Materia(titulo=t)
            self.materias.append(self.act)
            self.estado, self.clave = "intro", SIN_CICLO
            self.comp, self.cod_cr, self.buf_cr = {}, {}, {}
            self.bloque, self.buf_sb, self._padres = {}, {}, {}
            return

        if self.act is None:
            return

        # El nombre de la materia se repite bajo cada encabezado de sección.
        if _clave(t) == _clave(self.act.titulo):
            return

        ciclo = ciclo_de_cabecera(t)
        if ciclo:
            self.clave = (tuple(ciclo[0]), ciclo[1])
            return

        if RX_SEC_COMPETENCIAS.match(t):
            self._cerrar_ce(); self.estado = "competencias"; return
        if RX_SEC_CRITERIOS.match(t):
            self._cerrar_todo(); self.estado = "criterios"
            self.clave = SIN_CICLO
            return
        if RX_SEC_SABERES.match(t):
            self._cerrar_todo(); self.estado = "saberes"
            self.clave, self.bloque, self._padres = SIN_CICLO, {}, {}
            return

        if self.estado == "competencias":
            self._competencia(t, sangrada)
        elif self.estado == "criterios":
            self._criterio(t, cursos)
        elif self.estado == "saberes":
            self._saber(t, cursos)

    def _competencia(self, t: str, sangrada: bool) -> None:
        if RX_DESCRIPTORES.search(t):
            self._cerrar_ce()
            return
        m = RX_COMPETENCIA.match(t)
        if m and sangrada:
            self._cerrar_ce()
            self.cod_ce, self.buf_ce = m.group(1), [m.group(2)]
        elif self.cod_ce and sangrada:
            self.buf_ce.append(t)
        # Lo no sangrado es la explicación pedagógica, tres o cuatro párrafos
        # por competencia: no se guarda. No aporta al docente y multiplicaría
        # el contexto que ve el modelo.

    def _criterio(self, t: str, cursos: _Clave) -> None:
        m = RX_CRIT_CABECERA.match(t)
        if m:
            self._cerrar_cr(cursos)
            self.comp[cursos] = m.group(1)
            return
        m = RX_CRITERIO.match(t)
        if m:
            self._cerrar_cr(cursos)
            self.cod_cr[cursos] = f"{m.group(1)}.{m.group(2)}"
            # El código manda sobre la cabecera: lo que se cita en clase es el
            # código, y si discreparan sería un fallo del boletín.
            self.comp[cursos] = m.group(1)
            self.buf_cr[cursos] = [m.group(3)]
        elif self.cod_cr.get(cursos):
            self.buf_cr[cursos].append(t)

    def _saber(self, t: str, cursos: _Clave) -> None:
        m = RX_SABERES_DE_CURSO.match(t)
        if m:
            self._cerrar_sb(cursos)
            self.clave = ((f"{m.group(1)}º ESO",), cursos[1])
            self.bloque[self.clave] = None
            return

        m = RX_BLOQUE_MULTZOA.match(t) or RX_BLOQUE.match(t)
        if m and len(m.group(1)) == 1:
            self._cerrar_sb(cursos)
            b = BloqueSaberes(codigo=m.group(1), titulo=_limpiar(m.group(2)))
            self.act.tramo(cursos).saberes.append(b)
            self.bloque[cursos] = b
            self._padres[cursos] = b
            return

        if self.bloque.get(cursos) is None:
            return
        buf = self.buf_sb.setdefault(cursos, [])
        # Un saber nuevo empieza por viñeta, o bien en mayúscula cuando el
        # anterior ha cerrado con punto o con el asterisco. La mayoría no
        # llevan viñeta, así que eso es lo único que los separa.
        con_vineta = bool(RX_VINETA.match(t))
        if buf and (con_vineta or (
                re.match(r"^[A-ZÁÉÍÓÚÜÑ«\d]", t) and buf[-1].endswith(("*", ".")))):
            self._cerrar_sb(cursos)
            buf = self.buf_sb[cursos]
        buf.append(RX_VINETA.sub("", t) if con_vineta else t)


def _parsear(elementos: list) -> list[_Materia]:
    return _Parser().procesar(elementos)


def _a_materia_ciclo(m: _Materia) -> list[MateriaCiclo]:
    """Un `MateriaCiclo` por tramo, o uno solo si el boletín no los separa.

    Las materias que se imparten en varios cursos traen sus criterios y sus
    saberes **en columnas, una por ciclo**, y ahí los cursos salen del propio
    anexo. Las de un solo curso no tienen columnas, y para esas manda la tabla
    del artículo 13.

    Las competencias específicas se repiten en todos los tramos porque el
    decreto las enuncia una sola vez, antes de partir en columnas. El `seed`
    las reconoce como la misma fila y las cuenta como actualizadas, no como
    nuevas — igual que pasa en Galicia.
    """
    del_articulado = CURSOS_DEL_ARTICULADO.get(m.titulo)
    if del_articulado is None:
        logger.error(
            "«%s» no está en CURSOS_DEL_ARTICULADO. Se cargaría sin cursos, "
            "o sea invisible en la aplicación, así que no se guarda.", m.titulo,
        )
        return []

    con_ciclo = {c: t for c, t in m.tramos.items() if c != SIN_CICLO}
    sueltos = m.tramos.get(SIN_CICLO)

    salida: list[MateriaCiclo] = []
    if con_ciclo:
        for (cursos, itinerario), tramo in sorted(con_ciclo.items()):
            fuera = [c for c in cursos if c not in del_articulado]
            if fuera:
                logger.warning(
                    "%s: el anexo da %s y el artículo 13 solo lista %s. Se "
                    "guarda lo del anexo, que es el currículo.",
                    m.titulo, list(cursos), del_articulado,
                )
            salida.append(MateriaCiclo(
                materia_oficial=m.titulo,
                materia_corta=_bonito(m.titulo),
                ciclo=" y ".join(cursos) + (f" · {itinerario}" if itinerario else ""),
                cursos_aplicables=list(cursos),
                itinerario=itinerario or None,
                competencias=list(m.competencias),
                criterios=list(tramo.criterios),
                saberes=list(tramo.saberes),
            ))
        # Lo que quedó fuera de columna —una tabla sin cabecera de ciclo, o
        # texto suelto— se reparte a todos los tramos: es común a la materia.
        if sueltos and (sueltos.criterios or sueltos.saberes):
            for mc in salida:
                mc.criterios.extend(sueltos.criterios)
                mc.saberes.extend(sueltos.saberes)
        return salida

    tramo = sueltos or _Tramo(SIN_CICLO)
    return [MateriaCiclo(
        materia_oficial=m.titulo,
        materia_corta=_bonito(m.titulo),
        ciclo="Único",
        cursos_aplicables=del_articulado,
        competencias=m.competencias,
        criterios=tramo.criterios,
        saberes=tramo.saberes,
    )]


def _bonito(titulo: str) -> str:
    """«GEOGRAFIA ETA HISTORIA» -> «Geografia eta Historia».

    Las palabras de enlace del euskera van en minúscula, como las escribe el
    propio articulado cuando no está gritando en mayúsculas.
    """
    menores = {"eta", "edo", "eta/edo"}
    #: Siglas que no son palabras: «DBHko 3. maila» sale en dos títulos y
    #: capitalizarlo sin más daba «Dbhko», que no es como se escribe.
    siglas = {"dbhko": "DBHko", "dbh": "DBH"}
    salida = []
    for i, p in enumerate(titulo.lower().split()):
        if p in siglas:
            salida.append(siglas[p])
        elif i and p in menores:
            salida.append(p)
        else:
            salida.append(p[:1].upper() + p[1:])
    return " ".join(salida)


def extraer(pdf: Path) -> list[MateriaCiclo]:
    doc = pymupdf.open(pdf)
    try:
        materias = _parsear(elementos_del_anexo(doc))
    finally:
        doc.close()

    # Un bloque de primer nivel cuyos saberes cuelgan todos de subapartados se
    # queda sin items propios. Cargarlo dejaría 43 filas de catálogo con título
    # y sin contenido: aparecerían en el desplegable del docente y no ofrecerían
    # nada que citar.
    for m in materias:
        for tramo in m.tramos.values():
            tramo.saberes = [b for b in tramo.saberes if b.items]

    resultado: list[MateriaCiclo] = []
    for m in materias:
        criterios = sum(len(t.criterios) for t in m.tramos.values())
        if not m.competencias and not criterios:
            logger.warning("«%s» sale sin competencias ni criterios: se "
                           "descarta (¿un título mal reconocido?)", m.titulo)
            continue
        resultado.extend(_a_materia_ciclo(m))
    return resultado


def comprobar_contra_los_pdf_sueltos(
    resultado: list[MateriaCiclo], carpeta: Path
) -> list[str]:
    """Contrasta el recuento con los PDF por materia de Berrigasteiz.

    No es decorativo: en Galicia una cifra de contraste mal construida estuvo a
    punto de mandar a buscar un fallo inexistente, y la lección fue que el
    contraste hay que construirlo sobre algo comparable. Aquí lo es, porque
    Berrigasteiz publica exactamente una materia por fichero.

    Se descartan dos ficheros que **no son currículo** y que el rastreo del
    script recoge por el nombre: uno es material de aula y el otro es el anexo
    de otro decreto, el de Bachillerato.
    """
    fuera = ("nire_begiak", "eranskina")
    sueltos = [
        p for p in carpeta.glob("DBH*.pdf")
        if not any(f in p.name.lower() for f in fuera)
    ]
    materias = {mc.materia_oficial for mc in resultado}
    avisos = []
    if len(sueltos) != len(materias):
        avisos.append(
            f"{len(materias)} materias extraídas y {len(sueltos)} PDF por "
            f"materia: deberían coincidir"
        )
    return avisos


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
    retirar_huerfanos(salida, escritos)
    return escritos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf", type=Path, required=True,
                   help="Decreto completo en euskera (…_ZUZENDUTA.pdf)")
    p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--comunidad", default="pais-vasco")
    p.add_argument("--idioma", default="eu")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s | %(message)s")

    if not args.pdf.is_file():
        logger.error("No existe %s", args.pdf)
        return 2

    todos = extraer(args.pdf)
    if not todos:
        logger.error("Sin resultados")
        return 1

    for aviso in comprobar_contra_los_pdf_sueltos(todos, args.pdf.parent):
        logger.warning("CONTRASTE: %s", aviso)

    escritos = volcar(todos, args.salida, args.comunidad, args.idioma)
    materias = {mc.materia_oficial for mc in todos}
    bloques = sum(len(mc.saberes) for mc in todos)
    print(f"\n{len(materias)} materias, {bloques} bloques, {len(escritos)} "
          f"ficheros en {args.salida}")
    for mc in sorted(todos, key=lambda m: (m.materia_efectiva, m.ciclo)):
        print(f"  {mc.materia_efectiva:52s} {mc.ciclo:9s} "
              f"CE={len(mc.competencias):2d} crit={len(mc.criterios):3d} "
              f"sab={sum(len(b.items) for b in mc.saberes):3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
