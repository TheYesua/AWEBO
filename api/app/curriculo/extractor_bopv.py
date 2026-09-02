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

from .bopv_etapas import ESO, ETAPAS, EtapaBOPV
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
#:
#: Y el numeral puede venir **precedido de la referencia al decreto**:
#: «MAIATZAREN 30EKO 76/2023 DEKRETUAREN II. ERANSKINA». El de Bachillerato lo
#: hace siempre y el de la ESO solo en algunos anexos, así que el prefijo es
#: opcional. Sin él, el extractor de Bachillerato no encontraba su anexo y
#: fallaba en el primer intento — ruidosamente, que es lo bueno de que esto
#: lance en vez de devolver una lista vacía.
RX_ERANSKINA = re.compile(
    r"^\s*(?:.*\bDEKRETUAREN\s+)?([IVX]+)\.?\s*ERANSKINA?\s*$", re.I)

#: Encabezados de sección dentro de cada materia. El del criterio va con guion
#: y sin él —«EBALUAZIO-IRIZPIDEAK» en casi todas, «EBALUAZIO IRIZPIDEAK» en
#: Biologia eta Geologia—, y el de competencias aparece en singular en las
#: materias que solo tienen una.
RX_SEC_COMPETENCIAS = re.compile(r"^KONPETENTZIA\s+ESPEZIFIKOAK?\.?$", re.I)
RX_SEC_CRITERIOS = re.compile(r"^EBALUAZIO[\s\-]IRIZPIDEAK\.?$", re.I)
RX_SEC_SABERES = re.compile(r"^OINARRIZKO\s+JAKINTZAK\.?$", re.I)

#: «1. Hainbat iturritatik datorren informazio…» y «1.Adierazpen kulturalak…»:
#: el espacio tras el punto **también es opcional**. Sin contemplarlo,
#: Adierazpide Artistikoaren Hastapenak salía con tres competencias en vez de
#: cinco y sus criterios 1.1 y 1.2 apuntaban a una que no existía.
#:
#: El `(?!\d)` es imprescindible: sin él «1.1 Planteatutako…» se leería como la
#: competencia 1 con descripción «1 Planteatutako…».
RX_COMPETENCIA = re.compile(r"^(\d{1,2})\.\s*(?!\d)(.+)$", re.DOTALL)
#: Epígrafe de saberes con el contenido detrás, en la misma línea:
#: «1. ANTROPOLOGIARI SARRERA ETA IKERKETA METODOAK: Zer da antropologia…».
#: Es la forma de Gizarte-antropologia, y no se puede tratar como bloque
#: porque el título y el contenido no están separados: el epígrafe se queda
#: dentro del saber, que es como lo cita el decreto.
RX_EPIGRAFE = re.compile(r"^\d{1,2}\.\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ0-9 ,\-]{5,}:\s")
#: La misma sin exigir el punto, para las competencias que el boletín maquetó
#: mal. **No se usa sola**: solo vale si el número continúa la serie. Ver
#: `_competencia_mal_maquetada`.
RX_COMPETENCIA_LAXA = re.compile(r"^(\d{1,2})\.?\s+(?!\d)(.+)$", re.DOTALL)

#: «Konpetentzia espezifiko hau irteera-profilaren deskriptore hauekin lotzen
#: da: HKK3, STEM2…» — cierra la competencia y da sus descriptores. Es el único
#: marcador inequívoco de dónde acaba una y empieza la siguiente.
RX_DESCRIPTORES = re.compile(r"deskriptore\s+hauekin\s+lotzen\s+da\s*:", re.I)

#: «1. konpetentzia espezifikoa» — dentro de los criterios, dice a qué
#: competencia pertenecen los que vienen debajo.
RX_CRIT_CABECERA = re.compile(r"^(\d{1,2})\.\s*konpetentzia\s+espezifikoa$", re.I)

#: El código del criterio, en las **tres** puntuaciones que usa el boletín:
#:
#:   1.1. Planteatutako problemak…    (Teknologia, ESO)
#:   1.1 Osasunaren kontzeptu…        (Heziketa Fisikoa, ESO)
#:   1.1- Psikologiaren oinarrizko…   (Psikologia, Bachillerato)
#:
#: Exigir el punto dejaba seis materias de la ESO con cero criterios; exigir el
#: espacio después dejaba a Psikologia con cero. Ninguna de las dos veces hubo
#: error: simplemente no casaba ninguna línea, y la materia salía a medias.
RX_CRITERIO = re.compile(r"^(\d{1,2})\.(\d{1,2})[.\-]?\s+(.+)$", re.DOTALL)

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


def ciclo_de_cabecera(t: str, etapa=ESO) -> tuple[list[str], str] | None:
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
        return [f"{n}º {etapa.sufijo_curso}" for n in nums], itinerario

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
    return [f"{n}º {etapa.sufijo_curso}" for n in nums], itinerario


def cursos_de_ciclo(t: str, etapa=ESO) -> list[str] | None:
    """Solo los cursos, para quien no necesita el itinerario."""
    r = ciclo_de_cabecera(t, etapa)
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

# La tabla vive aquí desde antes que `bopv_etapas`, y se enlaza en vez de
# moverse: sus tests la importan de este módulo, y cambiarles el sitio no
# arreglaría nada.
ESO.cursos.update(CURSOS_DEL_ARTICULADO)


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


def _abre_saber(t: str, anterior: str) -> bool:
    """¿La línea `t` empieza un saber nuevo, viniendo detrás de `anterior`?

    El boletín no separa los saberes con nada: van uno detrás de otro dentro
    de la celda o del párrafo. Lo único que los distingue es que **el anterior
    ha cerrado** —punto final, o el asterisco que el decreto usa como marca— y
    este **empieza como una frase**, en mayúscula, comilla o número. Una línea
    que empieza en minúscula es la continuación de la de arriba, porque el PDF
    parte los párrafos por ancho de caja y no por sentido.

    Vive fuera de `_saber` porque el rescate de huérfanos necesita la misma
    regla: mientras no la tuvo, las materias rescatadas salían con **una línea
    física del PDF por saber**, cortados a media palabra —«logiaren praktikak,
    datu bilketa…»—. Eran 36 saberes rotos en dos materias de Bachillerato, y
    lo peor es que como texto seguían pareciendo válidos.
    """
    if RX_EPIGRAFE.match(t):
        # Un epígrafe numerado en mayúsculas abre aunque el anterior no haya
        # cerrado: en Gizarte-antropologia el bloque 2 termina «…balioa eta
        # zaintza» sin punto, y sin esto el 3 se le pegaba detrás.
        return True
    return bool(RX_VINETA.match(t)) or bool(
        re.match(r"^[A-ZÁÉÍÓÚÜÑ«\d]", t) and anterior.endswith(("*", ".")))


def _agrupar_saberes(lineas: list[str]) -> list[str]:
    """Une las líneas sueltas en saberes, con la regla de `_abre_saber`."""
    grupos: list[list[str]] = []
    for linea in lineas:
        if grupos and not _abre_saber(linea, grupos[-1][-1]):
            grupos[-1].append(linea)
        else:
            grupos.append([RX_VINETA.sub("", linea)])
    return [_unir(g).rstrip("*").strip() for g in grupos]


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


def _paginas_del_anexo(doc: pymupdf.Document, etapa=ESO) -> tuple[int, int]:
    """Delimita el anexo del currículo por sus propios encabezados.

    Y no por números de página, que cambiarían con cualquier reedición.

    **Cuál es el anexo depende de la etapa**: en la ESO es el III y en
    Bachillerato el II. No es un detalle: en el decreto de Educación Básica el
    Anexo II es el currículo de **primaria**, así que equivocarse aquí no da
    error, da el currículo de otra etapa.
    """
    inicio = fin = None
    for i, pagina in enumerate(doc):
        for linea in pagina.get_text().split("\n"):
            m = RX_ERANSKINA.match(_limpiar(linea))
            if not m:
                continue
            numeral = m.group(1).upper()
            if numeral == etapa.anexo and inicio is None:
                inicio = i
            elif (numeral == etapa.anexo_siguiente
                    and inicio is not None and fin is None):
                fin = i
    if inicio is None:
        raise ValueError(
            f"No se encuentra «{etapa.anexo} ERANSKINA» en el documento"
        )
    return inicio, fin if fin is not None else len(doc)


def elementos_del_anexo(doc: pymupdf.Document, etapa=ESO) -> list[_Linea | _Tabla]:
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
    inicio, fin = _paginas_del_anexo(doc, etapa)
    logger.info("Anexo %s: páginas %d a %d", etapa.anexo, inicio + 1, fin)

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
    # La cabecera del anexo va en mayúsculas y en su propia línea, igual que
    # una materia: «DERRIGORREZKO BIGARREN HEZKUNTZAKO JAKINTZAGAIAK» en la
    # ESO y «BATXILERGOKO JAKINTZAGAIAK» en Bachillerato. Sin excluirla se
    # pegaba al título de la primera materia de cada anexo.
    return not t.endswith("KO JAKINTZAGAIAK")


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

    def __init__(self, etapa: EtapaBOPV = ESO,
                 titulos: set[str] | None = None,
                 partidos: dict[str, str] | None = None) -> None:
        self.etapa = etapa
        #: Títulos que sí abren materia. `None` desactiva la comprobación, que
        #: es lo que quieren los tests de piezas sueltas.
        self.titulos = titulos
        #: Última línea de un título partido -> título completo.
        self.partidos = partidos or {}
        self.materias: list[_Materia] = []
        self.act: _Materia | None = None
        self.estado = "fuera"
        #: Ciclo vigente para el texto suelto. Las tablas traen el suyo.
        self.clave: _Clave = SIN_CICLO
        # competencia en curso (comunes a la materia, nunca en tabla)
        self.cod_ce: str | None = None
        self.buf_ce: list[str] = []
        #: Número de la última competencia abierta en esta materia. Es lo que
        #: permite reconocer la siguiente cuando el boletín la maqueta mal;
        #: se reinicia con cada materia porque la serie empieza de nuevo.
        self._ultima_ce = 0
        # por tramo
        self.comp: dict[tuple, str] = {}
        #: Última cabecera «N. Konpetentzia espezifikoa» de cada tramo. Aparte
        #: de `comp` porque el código del criterio la sobrescribe, y hace falta
        #: conservarla para detectar cuándo el boletín se copió. Ver
        #: `_corregir_numeracion`.
        self.cabecera: dict[tuple, str] = {}
        self.cod_cr: dict[tuple, str] = {}
        self.buf_cr: dict[tuple, list[str]] = {}
        self.bloque: dict[tuple, BloqueSaberes | None] = {}
        #: Bloque de primer nivel de cada tramo. Hace falta aparte porque
        #: `self.bloque` pasa a apuntar al subapartado en cuanto se abre uno, y
        #: el siguiente tiene que volver a colgar del mismo padre.
        self._padres: dict[tuple, BloqueSaberes | None] = {}
        self.buf_sb: dict[tuple, list[str]] = {}
        #: Líneas de saber que llegaron sin bloque abierto.
        self.huerfanos: dict[tuple, list[str]] = {}

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

    def _rescatar_saberes_huerfanos(self) -> None:
        """Recoge en un bloque las líneas que llegaron sin bloque abierto.

        **Solo cuando el tramo no tiene ningún bloque.** Si lo tiene, esas
        líneas son texto anterior al primero —una introducción a los saberes—
        y se descartan, que es lo que se hacía siempre.

        POR QUÉ HACE FALTA
        -------------------
        Seis optativas de Bachillerato marcan sus bloques de formas que no se
        reconocen: «Ikerketa-proiektuak edo kasuen ebazpena» sin marca alguna
        en Anatomia Aplikatua, o «1. ANTROPOLOGIARI SARRERA…:» con el
        contenido en la misma línea en Gizarte-Antropologia. Son textos
        redactados por equipos distintos y cada uno hace lo suyo, así que
        perseguir cada forma sería inacabable.

        Descartarlas dejaba esas seis materias con **cero saberes**. Recogerlas
        pierde el matiz de en qué bloque va cada una —que el decreto no marca
        de forma legible— pero **no pierde el texto**, que es lo que el docente
        cita.
        """
        if self.act is None:
            return
        for clave, lineas in self.huerfanos.items():
            tramo = self.act.tramos.get(clave)
            if not lineas or (tramo and tramo.saberes):
                continue
            # Y **solo si el tramo tiene criterios**. Sin ellos no es una
            # entrada de catálogo sino un artefacto: en Heziketa Fisikoa de la
            # ESO hay líneas como «Lehen mailako jakintzak:» dentro de los
            # saberes que abren un tramo de un solo curso, y sus criterios
            # están en el tramo del ciclo entero. Rescatar ahí creaba cuatro
            # materias nuevas con cero criterios que antes no existían — una
            # regresión que solo se vio comparando los recuentos de la ESO
            # antes y después de tocar Bachillerato.
            if not (tramo and tramo.criterios):
                continue
            tramo = self.act.tramo(clave)
            # Se agrupan como en cualquier otro bloque: lo que llega aquí son
            # líneas del PDF, no saberes. Ver `_abre_saber`.
            items = _agrupar_saberes(lineas)
            tramo.saberes.append(BloqueSaberes(
                codigo="1", titulo=_bonito(self.act.titulo), items=items))
            logger.info("«%s»: sin bloques reconocibles, sus %d saberes se "
                        "recogen en uno solo", self.act.titulo, len(items))
        self.huerfanos = {}

    def _cerrar_todo(self) -> None:
        self._cerrar_ce()
        for c in list(self.cod_cr):
            self._cerrar_cr(c)
        for c in list(self.bloque):
            self._cerrar_sb(c)
        self._rescatar_saberes_huerfanos()

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
        cabecera = [ciclo_de_cabecera(" ".join(c), self.etapa)
                    for c in tabla.filas[0]]

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
        # `self.titulos` viene de una pasada previa: son los títulos que
        # llevan `KONPETENTZIA ESPEZIFIKOAK` detrás, que es lo único que
        # distingue una materia de un bloque de saberes en mayúsculas. Ver
        # `titulos_de_materia`.
        completo = self.partidos.get(t, t)
        if _es_titulo_de_materia(t) and (self.titulos is None
                                         or completo in self.titulos):
            self._cerrar_todo()
            self.act = _Materia(titulo=completo)
            self.materias.append(self.act)
            self.estado, self.clave = "intro", SIN_CICLO
            self._ultima_ce = 0
            self.comp, self.cod_cr, self.buf_cr = {}, {}, {}
            self.cabecera = {}
            self.bloque, self.buf_sb, self._padres = {}, {}, {}
            return

        if self.act is None:
            return

        # El nombre de la materia se repite bajo cada encabezado de sección.
        if _clave(t) == _clave(self.act.titulo):
            return

        ciclo = ciclo_de_cabecera(t, self.etapa)
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
            self._abrir_ce(m.group(1), m.group(2))
        elif (laxa := self._competencia_mal_maquetada(t)) is not None:
            self._abrir_ce(*laxa)
        elif self.cod_ce and sangrada:
            self.buf_ce.append(t)
        # Lo no sangrado es la explicación pedagógica, tres o cuatro párrafos
        # por competencia: no se guarda. No aporta al docente y multiplicaría
        # el contexto que ve el modelo.

    def _abrir_ce(self, codigo: str, texto: str) -> None:
        self._cerrar_ce()
        self.cod_ce, self.buf_ce = codigo, [texto]
        self._ultima_ce = int(codigo)

    def _competencia_mal_maquetada(self, t: str) -> tuple[str, str] | None:
        """Una competencia que el boletín escribió mal, reconocida por su sitio
        en la serie.

        DOS FALLOS DEL DECRETO 76/2023, Y NINGUNO SE VE CON LA GEOMETRÍA
        ----------------------------------------------------------------
        * **Diseinua, competencia 3**: sangrada a x=48.1, que es la sangría de
          la explicación pedagógica. Enunciado y explicación llevan la misma
          fuente —Arial 11 sin negrita, comprobado span a span—, así que la
          sangría era el único rasgo que los distinguía, y aquí miente.
        * **Marrazketa Artistikoa, competencia 6**: escrita «6 Ekoizpen…», sin
          el punto. `RX_COMPETENCIA` lo exige y por eso no la veía.

        En los dos casos se perdía la competencia y sus criterios quedaban
        huérfanos: `3.1`, `3.2`, `6.1` y `6.2` apuntando a algo que la
        aplicación no tenía. El docente los habría visto sin enunciado.

        POR QUÉ LA SERIE Y NO UN UMBRAL MÁS FLOJO
        ------------------------------------------
        Bajar `X_SANGRADO` a 48 habría convertido cada párrafo de explicación
        que empieza por un número en una competencia. La numeración correlativa
        es una condición mucho más estrecha: solo se acepta el número que
        **falta justo ahora**, así que una línea suelta que empiece por «3.»
        cuando ya se leyó la 3 no entra. En todo el Anexo II esto rescata dos
        líneas, que son exactamente las dos que faltaban.
        """
        m = RX_COMPETENCIA_LAXA.match(t)
        if not m or int(m.group(1)) != self._ultima_ce + 1:
            return None
        # Un enunciado empieza en mayúscula. Descarta continuaciones de
        # párrafo, que es de lo único que hay que defenderse aquí.
        if not m.group(2)[:1].isupper():
            return None
        return m.group(1), m.group(2)

    def _criterio(self, t: str, cursos: _Clave) -> None:
        m = RX_CRIT_CABECERA.match(t)
        if m:
            self._cerrar_cr(cursos)
            self.comp[cursos] = self.cabecera[cursos] = m.group(1)
            return
        m = RX_CRITERIO.match(t)
        if m:
            self._cerrar_cr(cursos)
            ce, orden = m.group(1), m.group(2)
            ce = self._corregir_numeracion(ce, orden, cursos)
            self.cod_cr[cursos] = f"{ce}.{orden}"
            # El código manda sobre la cabecera: lo que se cita en clase es el
            # código, y si discreparan sería un fallo del boletín. La excepción
            # está en `_corregir_numeracion`.
            self.comp[cursos] = ce
            self.buf_cr[cursos] = [m.group(3)]
        elif self.cod_cr.get(cursos):
            self.buf_cr[cursos].append(t)

    def _corregir_numeracion(self, ce: str, orden: str, cursos: _Clave) -> str:
        """Devuelve el número de competencia bueno cuando el boletín se copió.

        EL FALLO, QUE ES DEL DECRETO Y NO DEL LECTOR
        ---------------------------------------------
        El 76/2023 arrastra bloques enteros de criterios sin cambiarles el
        primer dígito. En Filosofiaren Historia, bajo «3. Konpetentzia
        espezifikoa», los criterios van numerados `2.1`, `2.2` y luego `3.3`.
        En Euskal Herriko Historia pasa lo mismo bajo las cabeceras 2 y 8.

        Cargarlos tal cual no da error: el segundo `2.1` **pisa al primero** en
        el upsert y desaparece un criterio con su texto. Así se perdían cinco,
        y se vio porque el seed dijo `cr_nuevos=1138` donde los JSON tenían
        1144. Seis números que no cuadran es todo el aviso que hubo.

        POR QUÉ SE CORRIGE Y NO SE RESPETA LA FUENTE
        ---------------------------------------------
        Porque la corrección **está dentro del propio documento**: la cabecera
        dice explícitamente de qué competencia son, y el `3.3` que viene detrás
        confirma que el bloque es el tercero. No se inventa un código, se
        prefiere una de las dos cosas que el decreto dice, y se prefiere la que
        no se contradice a sí misma.

        DÓNDE NO SE TOCA
        -----------------
        Cuando la cabecera **coincide** con el código no hay nada que deducir:
        en Euskara eta Literatura hay dos `8.3` distintos bajo la cabecera 8, y
        ahí el código bueno del segundo sería `8.4`, que el decreto no dice en
        ninguna parte. Ese se deja repetido —es lo que publica el boletín— y el
        cargador se encarga de no perderlo. Queda anotado como cabo abierto.
        """
        cabecera = self.cabecera.get(cursos)
        if not cabecera or cabecera == ce or self.act is None:
            return ce
        emitidos = {c.codigo for c in self.act.tramo(cursos).criterios}
        if f"{ce}.{orden}" not in emitidos:
            return ce
        if f"{cabecera}.{orden}" in emitidos:
            # Corregirlo lo haría chocar con otro: se deja como está, que al
            # menos es lo que dice el boletín.
            logger.warning("«%s»: el criterio %s.%s está repetido y corregirlo "
                           "chocaría con %s.%s", self.act.titulo, ce, orden,
                           cabecera, orden)
            return ce
        logger.warning("«%s»: criterio %s.%s bajo la cabecera de la "
                       "competencia %s y ya emitido; se carga como %s.%s",
                       self.act.titulo, ce, orden, cabecera, cabecera, orden)
        return cabecera

    def _saber(self, t: str, cursos: _Clave) -> None:
        m = RX_SABERES_DE_CURSO.match(t)
        if m:
            self._cerrar_sb(cursos)
            self.clave = ((f"{m.group(1)}º {self.etapa.sufijo_curso}",), cursos[1])
            self.bloque[self.clave] = None
            return

        # LA SEXTA FORMA: MAYÚSCULAS Y SIN NADA DELANTE
        # ----------------------------------------------
        # En «Kultura Zientifikoa» de Bachillerato los bloques son
        # «ZER JATEN DUGU?», «ZAHARTZEA», «INGENIARITZA GENETIKOA»… sin letra
        # ni número. No se distinguen de un título de materia por el texto
        # —«ZAHARTZEA» es una palabra suelta igual que «BOLUMENA», que sí lo
        # es—, así que lo que los separa es **dónde aparecen**: dentro de
        # `OINARRIZKO JAKINTZAK` una línea en mayúsculas no puede abrir una
        # materia nueva, porque las materias empiezan por su título y no por
        # sus saberes.
        #
        # Como el reconocedor de materias corre antes que este método, la
        # comprobación de verdad está en `_linea`; aquí solo se les da número
        # de orden, que es el único código que tienen.
        if _es_titulo_de_materia(t):
            self._cerrar_sb(cursos)
            tramo = self.act.tramo(cursos)
            b = BloqueSaberes(codigo=str(len(tramo.saberes) + 1),
                              titulo=_limpiar(t))
            tramo.saberes.append(b)
            self.bloque[cursos] = b
            self._padres[cursos] = b
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
            # Sin bloque abierto, la línea se guarda aparte en vez de tirarse:
            # ver `_rescatar_saberes_huerfanos`, que decide al final qué hacer
            # con ella. Aquí no se puede saber: puede ser texto anterior al
            # primer bloque —que sí hay que descartar— o el único contenido de
            # una materia que no marca bloques de forma reconocible.
            if len(t) >= 25:
                self.huerfanos.setdefault(cursos, []).append(t)
            return
        buf = self.buf_sb.setdefault(cursos, [])
        # Un saber nuevo empieza por viñeta, o bien en mayúscula cuando el
        # anterior ha cerrado con punto o con el asterisco. La mayoría no
        # llevan viñeta, así que eso es lo único que los separa.
        con_vineta = bool(RX_VINETA.match(t))
        if buf and _abre_saber(t, buf[-1]):
            self._cerrar_sb(cursos)
            buf = self.buf_sb[cursos]
        buf.append(RX_VINETA.sub("", t) if con_vineta else t)


def _parsear(elementos: list, etapa: EtapaBOPV = ESO,
             titulos: set[str] | None = None,
             partidos: dict[str, str] | None = None) -> list[_Materia]:
    return _Parser(etapa, titulos, partidos).procesar(elementos)


def _a_materia_ciclo(m: _Materia, etapa: EtapaBOPV = ESO) -> list[MateriaCiclo]:
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
    del_articulado = etapa.cursos.get(m.titulo)
    if del_articulado is None and etapa.cursos_por_defecto:
        # LAS OPTATIVAS DE BACHILLERATO NO LLEVAN CURSO, Y NO ES UN DESCUIDO
        # ------------------------------------------------------------------
        # El artículo 17.1 dice que los centros pueden ofrecer cualquiera de
        # las que lista el Anexo II, sin restringir el curso, y el Anexo V las
        # agrupa como «Hautazkoak» sin nombrarlas. Así que el reparto por
        # defecto **sale de la norma** y no de la comodidad.
        #
        # Se registra igual, porque una materia que cae aquí por error —un
        # título mal leído que no casa con la tabla— entraría en los dos
        # cursos en silencio, y eso hay que poder verlo.
        del_articulado = list(etapa.cursos_por_defecto)
        logger.info("«%s»: %s -> %s", m.titulo, etapa.motivo_por_defecto,
                    del_articulado)
    if del_articulado is None:
        logger.error(
            "«%s» no está en la tabla de cursos de %s. Se cargaría sin cursos, "
            "o sea invisible en la aplicación, así que no se guarda.",
            m.titulo, etapa.nombre,
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
                etapa=etapa.nombre,
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
        etapa=etapa.nombre,
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


def titulos_de_materia(elementos: list) -> tuple[set[str], dict[str, str]]:
    """Qué líneas en mayúsculas abren materia, en una pasada previa.

    EL PROBLEMA QUE RESUELVE
    -------------------------
    En «Kultura Zientifikoa» de Bachillerato los bloques de saberes van en
    MAYÚSCULAS y sin letra ni número: `ZER JATEN DUGU?`, `ZAHARTZEA`,
    `INGENIARITZA GENETIKOA`… Y **no se distinguen de un título de materia por
    el texto**: «ZAHARTZEA» es una palabra suelta igual que «BOLUMENA», que sí
    es una materia.

    El primer intento fue mirar el estado —dentro de los saberes, mayúsculas es
    un bloque— y estaba mal: el título de la materia siguiente llega
    precisamente cuando el estado son los saberes de la anterior, así que el
    extractor se quedó con **dos materias de 65** y todo el anexo dentro.

    LO QUE SÍ LAS DISTINGUE
    ------------------------
    Una materia va seguida de `KONPETENTZIA ESPEZIFIKOAK`; un bloque de
    saberes, no. Es estructural y no depende de ninguna tabla, así que sigue
    valiendo para una materia que se nos haya escapado de `etapa.cursos`.

    Se hace en una pasada aparte porque el reconocedor es secuencial y esto es
    mirar hacia adelante.
    """
    #: Líneas candidatas **consecutivas**: un título partido no tiene nada en
    #: medio. En cuanto llega otra cosa, el grupo se cierra y se guarda.
    grupo: list[str] = []
    #: El último grupo cerrado, que es el que se confirma al llegar las
    #: competencias — entre el título y ellas va la introducción de la materia,
    #: que son varios párrafos.
    candidatos: list[str] = []
    titulos: set[str] = set()
    #: última línea -> título completo, para el reconocedor.
    partidos: dict[str, str] = {}
    for e in elementos:
        lineas = ([e.texto] if isinstance(e, _Linea)
                  else [l for f in e.filas for c in f for l in c])
        for t in lineas:
            if not t or _es_ruido(t):
                continue
            # El grupo se cierra con cualquier línea que no lo continúe, y se
            # guarda como el último candidato visto.
            if grupo and not _es_titulo_de_materia(t):
                candidatos, grupo = grupo, []

            if RX_SEC_COMPETENCIAS.match(t):
                # Los candidatos acumulados son el título de la materia a la
                # que pertenecen estas competencias. Normalmente hay uno.
                #
                # **Si hay varios, es un título partido en dos líneas**, y hay
                # que juntarlos: en Bachillerato pasa con «EGUNGO MUNDUAREN
                # GATAZKAK ETA ERREALITATEAK, ETA KOMUNIKABIDEEKIN ETA / SARE
                # SOZIALEKIN DUTEN ERLAZIOA». Quedarse con el último dejaba la
                # materia llamándose «SARE SOZIALEKIN DUTEN ERLAZIOA», que es
                # el mismo fallo que en Galicia cargó los ámbitos como
                # «obrigatoria».
                if candidatos:
                    if len(candidatos) > 1:
                        logger.info("Título en %d líneas: «%s»",
                                    len(candidatos), " ".join(candidatos))
                    titulos.add(" ".join(candidatos))
                    partidos[candidatos[-1]] = " ".join(candidatos)
                candidatos = []
            elif RX_SEC_CRITERIOS.match(t) or RX_SEC_SABERES.match(t):
                candidatos = []
            elif _es_titulo_de_materia(t):
                grupo.append(t)
            else:
                # UN TÍTULO PARTIDO OCUPA LÍNEAS SEGUIDAS
                # ----------------------------------------
                # Sin este reinicio, los seis bloques en mayúsculas de
                # «Kultura Zientifikoa» se acumulaban con la materia que viene
                # después y salía un título de siete líneas:
                # «ZER JATEN DUGU? ZAHARTZEA … LABORATEGIKO TEKNIKAK».
                #
                # Entre esos bloques hay saberes, y entre las dos líneas de un
                # título de verdad no hay nada. Eso es lo que los separa.
                pass
    return titulos, partidos


def extraer(pdf: Path, etapa: EtapaBOPV = ESO) -> list[MateriaCiclo]:
    doc = pymupdf.open(pdf)
    try:
        elementos = elementos_del_anexo(doc, etapa)
        titulos, partidos = titulos_de_materia(elementos)
        materias = _parsear(elementos, etapa, titulos, partidos)
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
        resultado.extend(_a_materia_ciclo(m, etapa))
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
    # Todo PDF menos el decreto completo y los que no son currículo. **No se
    # filtra por prefijo del nombre**: en la ESO son «DBH8_natur_zientziak_e»
    # y en Bachillerato «1.1.batxi_matematika_orokorrak_e», y buscar «DBH*»
    # daba cero en Bachillerato — el contraste decía «65 y 0» y parecía un
    # fallo de extracción cuando lo era del contraste.
    fuera = ("nire_begiak", "eranskina", "_art_", "sarrera", "dekretua")
    sueltos = [
        p for p in carpeta.glob("*.pdf")
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
    p.add_argument("--etapa", choices=sorted(ETAPAS), default="eso",
                   help="Decide de qué anexo se lee y qué cursos se asignan")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s | %(message)s")

    if not args.pdf.is_file():
        logger.error("No existe %s", args.pdf)
        return 2

    etapa = ETAPAS[args.etapa]
    todos = extraer(args.pdf, etapa)
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
