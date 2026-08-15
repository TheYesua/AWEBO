"""Extractor del currículo LOMLOE a partir del boletín oficial que lo publica.

El formato del boletín vive **entero** en el `Perfil`: de dónde salen los
párrafos (`lector`), cómo se llaman las secciones y en qué idioma
(`marcador_*`) y cómo se reconoce un marcador de curso (`palabra_curso`,
`patrones_ciclo`). De ahí para dentro el extractor solo ve párrafos con
etiqueta, y la forma de una competencia, un criterio y un saber la fija la
LOMLOE, no el editor.

Esto no era así hasta el 14/08/2026: los dos perfiles que existían eran los dos
del BOE, así que todo lo que compartían se quedó fuera del `Perfil` sin que
nadie decidiera que debía quedarse fuera. Ver el docstring de `Perfil`.

Hoy soporta dos fuentes oficiales, configurables como "perfiles":

* ``rd_217`` — Real Decreto 217/2022 (BOE-A-2022-4975), enseñanzas mínimas
  estatales. Estructura más sintética: criterios y saberes agrupados por
  ciclos amplios ("Cursos de primero a tercero" / "Curso de cuarto").
  Cubre 1.º a 3.º ESO para Matemáticas; no incluye Matemáticas 4.º.

* ``orden_efp_754`` — Orden EFP/754/2022 (BOE-A-2022-13172), desarrollo
  curricular en el ámbito de Ceuta y Melilla. Estructura más detallada:
  saberes organizados por curso individual ("Primer curso", "Segundo
  curso", ...) y Matemáticas 4.º está disponible en dos itinerarios
  (A y B), tratados como materias independientes.

Ambos perfiles producen el mismo formato de salida JSON, lo que permite
intercambiar la fuente sin tocar el resto del sistema.

Uso:

    docker compose exec api python -m app.curriculo.extractor \\
        --xml /tmp/orden_754.xml \\
        --perfil orden_efp_754 \\
        --salida /tmp/curriculo_salida
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from html import unescape

from lxml import etree


#: Espacio de nombres de Akoma Ntoso 3.0.
_NS_AKN = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

logger = logging.getLogger("curriculo.extractor")


#: Un lector convierte el fichero de entrada en una secuencia de
#: ``(clase, texto)``. Es el único punto que sabe qué formato tiene el
#: boletín; de ahí para dentro, el extractor solo ve párrafos con etiqueta.
Lector = Callable[[Path], Iterator[tuple[str, str]]]


# ---------------------------------------------------------------------------
# Perfiles de extracción
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Perfil:
    """Configuración específica del formato de un boletín concreto.

    HASTA DÓNDE LLEGA ESTA ABSTRACCIÓN, Y HASTA DÓNDE NO
    -----------------------------------------------------
    Se diseñó con dos muestras del **mismo editor**: el RD 217 y la Orden
    EFP/754 son los dos del BOE. Eso significa que todo lo que los dos
    comparten quedó fuera del `Perfil` sin que nadie se diera cuenta de que era
    una decisión — porque no había con qué contrastarlo.

    Las tres cosas que estaban fuera y son del BOE, no del currículo:

    * **De dónde salen los párrafos.** El BOE publica ``<texto>`` con ``<p
      class="centro_negrita">``: la maquetación ES la estructura. Otros
      boletines publican Akoma Ntoso, donde la jerarquía es semántica y las
      clases CSS no existen. Por eso ``lector`` es un parámetro.
    * **En qué idioma están los marcadores.** «Competencias específicas» solo
      vale en castellano. Un decreto catalán dice «Competències específiques»,
      y el extractor no encontraría ni una sola sección — sin dar ningún error,
      devolviendo cero materias.
    * **De dónde se sacan los cursos de cada materia.** Los artículos de la
      parte dispositiva son una convención del BOE.

    Lo que sí es común y se queda fuera del `Perfil`: la forma de una
    competencia específica, de un criterio y de un saber básico. Eso lo fija la
    LOMLOE y lo repiten todos los decretos, que para eso son desarrollo de la
    misma ley.
    """

    nombre: str

    # Clase CSS que envuelve la cabecera de cada materia.
    clase_cabecera_materia: str

    # Si es True, la cabecera se compara en mayúsculas con el nombre oficial.
    cabecera_mayusculas: bool

    # Materias dentro del alcance de la aplicación (claves) -> etiqueta corta en la app (valores).
    materias_objetivo: dict[str, str]

    # Cursos por defecto si la materia no contiene marcadores de ciclo.
    cursos_por_defecto: dict[str, list[str]]

    #: Artículos de la parte dispositiva que reparten materias por curso, en
    #: el orden (tres primeros cursos, cuarto curso, artículo dedicado a
    #: Valores Cívicos o ``None`` si no lo hay). Los usa ``derivar_cursos``.
    #: El RD 217 los numera 8, 9 y 10; la Orden EFP/754, 9 y 10.
    articulos_cursos: tuple[int, int, int | None] = (8, 9, 10)

    #: Cómo se convierte el fichero de entrada en una secuencia de
    #: ``(clase, texto)``. El nombre `clase` es herencia del BOE; para un
    #: formato sin clases CSS puede ser cualquier etiqueta que el lector
    #: considere significativa, o cadena vacía.
    #:
    #: ``None`` significa «el del BOE», que es lo que usan los dos perfiles de
    #: hoy. Se resuelve en `leer()` y no aquí porque los perfiles se construyen
    #: arriba del todo del módulo, antes de que la función exista: fijarlo como
    #: defecto en `__post_init__` da `NameError` al importar.
    lector: "Lector | None" = None

    #: Los tres encabezados de sección, **en el idioma del boletín**, tal y
    #: como los deja `_norm`: en minúsculas, sin punto final y **con tildes**.
    #: `_norm` no quita los acentos, así que escribirlos sin ellos aquí no
    #: casaría con nada — y el extractor devolvería cero materias sin dar
    #: ningún error.
    marcador_competencias: str = "competencias específicas"
    marcador_criterios: str = "criterios de evaluación"
    marcador_saberes: str = "saberes básicos"

    #: Palabra que tiene que aparecer para que merezca la pena probar los
    #: patrones de ciclo. Es un atajo de rendimiento, pero también de idioma:
    #: en catalán es «curs» y sin cambiarla no casaría ningún marcador.
    palabra_curso: str = "curso"

    #: Patrones que reconocen un marcador de ciclo, con la función que traduce
    #: la coincidencia a lista de cursos. ``None`` = los del BOE, en castellano.
    #:
    #: Va aquí y no como constante del módulo porque `palabra_curso` sola era
    #: un arreglo falso: cambiarla a «curs» hace que el atajo deje pasar el
    #: texto catalán, pero después lo miden regex que dicen «primer curso» y no
    #: casa ninguna. El resultado no es un error: es una materia con los cursos
    #: por defecto, que es peor, porque parece un dato.
    patrones_ciclo: "list[tuple[re.Pattern[str], Callable]] | None" = None

    def leer(self, ruta: Path) -> Iterator[tuple[str, str]]:
        """Los párrafos del documento, con el lector que corresponda."""
        return (self.lector or leer_parrafos_boe)(ruta)

    @property
    def ciclos(self) -> "list[tuple[re.Pattern[str], Callable]]":
        """Los patrones de ciclo de este boletín. Mismo motivo que `leer`."""
        return self.patrones_ciclo if self.patrones_ciclo is not None else RX_CICLOS


#: Las 18 materias del Anexo II del RD 217/2022, con la etiqueta corta que usa
#: la aplicación.
#:
#: Es el Anexo II **entero**. El RD trae además, en el Anexo V, dos ámbitos de
#: ciclos formativos de grado básico (Ciencias Aplicadas y Comunicación y
#: Ciencias Sociales) que se extraen igual de bien pero **no son ESO**, y
#: ``MateriaCiclo.to_dict()`` escribe ``"etapa": "ESO"`` sin preguntar. Meterlos
#: aquí guardaría un dato falso en la base de datos, así que quedan fuera hasta
#: que el modelo distinga etapas.
#:
#: "Lengua" e "Inglés" conservan su etiqueta histórica porque ya hay
#: situaciones de aprendizaje guardadas que referencian esas cadenas. El resto
#: usa su nombre oficial.
_MATERIAS_RD_217: dict[str, str] = {
    # --- las que ya estaban, con su etiqueta de siempre ---
    # Dos materias distintas del BOE, no dos nombres de la misma: ver el
    # comentario equivalente en ``_MATERIAS_ORDEN_754``.
    "Tecnología y Digitalización": "Tecnología y Digitalización",  # 1.º-3.º
    "Tecnología": "Tecnología",                                     # 4.º, de opción
    "Lengua Castellana y Literatura": "Lengua",
    "Matemáticas": "Matemáticas",
    "Lengua Extranjera": "Inglés",
    # --- ampliación a todo el Anexo II ---
    "Biología y Geología": "Biología y Geología",
    "Digitalización": "Digitalización",
    "Economía y Emprendimiento": "Economía y Emprendimiento",
    "Educación Física": "Educación Física",
    "Educación Plástica, Visual y Audiovisual": "Educación Plástica, Visual y Audiovisual",
    "Educación en Valores Cívicos y Éticos": "Educación en Valores Cívicos y Éticos",
    "Expresión Artística": "Expresión Artística",
    "Física y Química": "Física y Química",
    "Formación y Orientación Personal y Profesional": (
        "Formación y Orientación Personal y Profesional"
    ),
    "Geografía e Historia": "Geografía e Historia",
    "Latín": "Latín",
    "Música": "Música",
    "Segunda Lengua Extranjera": "Segunda Lengua Extranjera",
}


#: Cursos de las materias cuyo currículo **no** se divide en ciclos. Cuando el
#: BOE parte una materia en "Cursos de primero a tercero" / "Cuarto curso", el
#: propio marcador dice los cursos y esta tabla no interviene; las que van en
#: un bloque "Único" no dicen nada y sin esto heredarían 1.º-4.º, ofreciendo
#: Latín en 1.º de ESO.
#:
#: No está escrita de memoria: sale de ``derivar_cursos()``, que lee los
#: artículos 8, 9 y 10 del propio XML. ``test_extractor.py`` vuelve a
#: derivarla y comprueba que sigue coincidiendo, así que si esta tabla y el
#: BOE dejan de estar de acuerdo, lo dice un test y no un docente.
_CURSOS_RD_217: dict[str, list[str]] = {
    "Digitalización": ["4º ESO"],
    "Economía y Emprendimiento": ["4º ESO"],
    "Educación Plástica, Visual y Audiovisual": ["1º ESO", "2º ESO", "3º ESO"],
    "Educación en Valores Cívicos y Éticos": ["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
    "Expresión Artística": ["4º ESO"],
    "Formación y Orientación Personal y Profesional": ["4º ESO"],
    "Latín": ["4º ESO"],
    "Segunda Lengua Extranjera": ["4º ESO"],
    "Tecnología": ["4º ESO"],
    "Tecnología y Digitalización": ["1º ESO", "2º ESO", "3º ESO"],
}


PERFIL_RD_217 = Perfil(
    nombre="rd_217",
    clase_cabecera_materia="centro_negrita",
    cabecera_mayusculas=False,
    materias_objetivo=_MATERIAS_RD_217,
    cursos_por_defecto=_CURSOS_RD_217,
)


#: Las 21 materias de ESO de la Orden EFP/754: las 18 del Anexo II del RD más
#: tres optativas propias de la oferta de Ceuta y Melilla (Cultura Clásica,
#: Introducción a la Filosofía y Medios y Recursos Digitales).
#:
#: Quedan fuera, igual que en el RD, los dos ámbitos de ciclos formativos de
#: grado básico: se extraen bien pero no son ESO.
#:
#: "Lengua", "Inglés" y "Matemáticas" conservan su etiqueta histórica porque ya
#: hay situaciones de aprendizaje guardadas que referencian esas cadenas.
_MATERIAS_ORDEN_754: dict[str, str] = {
    # --- las que ya estaban ---
    # Son dos materias distintas del BOE, con competencias específicas
    # distintas (7 frente a 6) y textos distintos. Compartieron la etiqueta
    # "Tecnología" hasta el 7/8/2026, y como el seed identifica las
    # competencias por (código, materia), la CE1 de una sobrescribía la
    # descripción de la otra y los cursos se fusionaban en 2.º-4.º.
    "TECNOLOGÍA Y DIGITALIZACIÓN": "Tecnología y Digitalización",  # 2.º y 3.º
    "TECNOLOGÍA": "Tecnología",                                     # 4.º, de opción
    "LENGUA CASTELLANA Y LITERATURA": "Lengua",
    "MATEMÁTICAS": "Matemáticas",
    "LENGUA EXTRANJERA": "Inglés",
    # --- ampliación al resto de la etapa ---
    "BIOLOGÍA Y GEOLOGÍA": "Biología y Geología",
    "CULTURA CLÁSICA": "Cultura Clásica",
    "DIGITALIZACIÓN": "Digitalización",
    "ECONOMÍA Y EMPRENDIMIENTO": "Economía y Emprendimiento",
    "EDUCACIÓN FÍSICA": "Educación Física",
    "EDUCACIÓN PLÁSTICA, VISUAL Y AUDIOVISUAL": "Educación Plástica, Visual y Audiovisual",
    "EDUCACIÓN EN VALORES CÍVICOS Y ÉTICOS": "Educación en Valores Cívicos y Éticos",
    "EXPRESIÓN ARTÍSTICA": "Expresión Artística",
    "FÍSICA Y QUÍMICA": "Física y Química",
    "FORMACIÓN Y ORIENTACIÓN PERSONAL Y PROFESIONAL": (
        "Formación y Orientación Personal y Profesional"
    ),
    "GEOGRAFÍA E HISTORIA": "Geografía e Historia",
    "INTRODUCCIÓN A LA FILOSOFÍA": "Introducción a la Filosofía",
    "LATÍN": "Latín",
    "MEDIOS Y RECURSOS DIGITALES": "Medios y Recursos Digitales",
    "MÚSICA": "Música",
    "SEGUNDA LENGUA EXTRANJERA": "Segunda Lengua Extranjera",
}


#: Cursos de las materias cuyo currículo no se divide por cursos en la Orden.
#: Derivada de sus artículos 9 y 10 por ``derivar_cursos``, y atada a ellos
#: por ``test_extractor.py``.
#:
#: Cultura Clásica, Introducción a la Filosofía y Medios y Recursos Digitales
#: no salen aquí a propósito: son optativas que autoriza la Dirección
#: Provincial y la norma no les fija curso, así que se quedan con el 1.º-4.º
#: por defecto del extractor.
_CURSOS_ORDEN_754: dict[str, list[str]] = {
    "DIGITALIZACIÓN": ["4º ESO"],
    "ECONOMÍA Y EMPRENDIMIENTO": ["4º ESO"],
    "EDUCACIÓN EN VALORES CÍVICOS Y ÉTICOS": ["2º ESO"],
    "EXPRESIÓN ARTÍSTICA": ["4º ESO"],
    "FORMACIÓN Y ORIENTACIÓN PERSONAL Y PROFESIONAL": ["4º ESO"],
    "LATÍN": ["4º ESO"],
    "SEGUNDA LENGUA EXTRANJERA": ["4º ESO"],
    "TECNOLOGÍA": ["4º ESO"],
}


PERFIL_ORDEN_EFP_754 = Perfil(
    nombre="orden_efp_754",
    clase_cabecera_materia="centro_redonda",
    cabecera_mayusculas=True,
    materias_objetivo=_MATERIAS_ORDEN_754,
    cursos_por_defecto=_CURSOS_ORDEN_754,
    articulos_cursos=(9, 10, None),
)


PERFILES = {
    PERFIL_RD_217.nombre: PERFIL_RD_217,
    PERFIL_ORDEN_EFP_754.nombre: PERFIL_ORDEN_EFP_754,
}


# Ordinales que aparecen en los marcadores de ciclo.
_ORDINALES = {
    "primero": 1, "segundo": 2, "tercero": 3, "cuarto": 4,
    "primer": 1, "segund": 2, "tercer": 3, "cuart": 4,
}


# ---------------------------------------------------------------------------
# Patrones de reconocimiento
# ---------------------------------------------------------------------------

# En la sección "Competencias específicas." cada CE empieza con
# "<N>. Texto..." (parrafo_2). Ej: "1. Buscar y seleccionar la información..."
RX_CE_INICIO = re.compile(r"^(\d+)\.\s+(.+)$", re.DOTALL)

# En la sección "Criterios de evaluación":  "Competencia específica N."
RX_CE_HEADER_CRIT = re.compile(r"^Competencia específica\s+(\d+)\.?\s*$")

# Línea de criterio: "1.1 Texto..." (con o sin punto final tras el código).
RX_CRITERIO = re.compile(r"^\s*(\d+)\.(\d+)\.?\s+(.+)$", re.DOTALL)

# Línea de descriptores del Perfil de salida.
#
# Los espacios van como ``\s+`` y no como espacios literales por el mismo
# motivo que ``_norm_cabecera``: el BOE mete espacios duros donde uno espera
# espacios. Con la versión literal, la competencia específica 2 de Biología y
# Geología —"descriptores del\xa0Perfil de salida:"— se quedaba sin ninguno,
# en las dos normas, y sin ningún síntoma más que una lista vacía.
RX_DESCRIPTORES = re.compile(
    r"descriptores\s+del\s+Perfil\s+de\s+salida\s*:\s*([^.]+)",
    re.IGNORECASE,
)

# Bloque de saberes: "A. Título del bloque."  (letra mayúscula + punto + texto)
RX_BLOQUE_SABER = re.compile(r"^([A-Z])\.\s+(.+?)\.?\s*$")

# Sub-encabezado numérico dentro de un bloque de saberes (Orden EFP/754):
# "1. Conteo." / "2. Cantidad." -> ignorar como item (es un agrupador).
RX_SUBENCAB_SABER = re.compile(r"^\d+\.\s+[A-ZÁÉÍÓÚÑa-záéíóúñ][^.]{0,40}\.?\s*$")

# Marcadores de ciclo: catálogo de patrones reconocidos.
# Cada entrada es (regex, fn que devuelve lista de cursos a partir de groups).
def _curso_uno(n: int) -> list[str]:
    return [f"{n}º ESO"]


def _curso_rango(ini: int, fin: int) -> list[str]:
    return [f"{i}º ESO" for i in range(ini, fin + 1)]


RX_CICLOS: list[tuple[re.Pattern[str], callable]] = [  # type: ignore[type-arg]
    # "Cursos de primero a tercero"
    (
        re.compile(r"^cursos?\s+de\s+(\w+)\s+a\s+(\w+)$"),
        lambda m: _curso_rango(_ORDINALES[m.group(1)], _ORDINALES[m.group(2)])
        if m.group(1) in _ORDINALES and m.group(2) in _ORDINALES else None,
    ),
    # "Cursos primero y segundo"
    (
        re.compile(r"^cursos?\s+(\w+)\s+y\s+(\w+)$"),
        lambda m: [f"{_ORDINALES[m.group(1)]}º ESO", f"{_ORDINALES[m.group(2)]}º ESO"]
        if m.group(1) in _ORDINALES and m.group(2) in _ORDINALES else None,
    ),
    # "Cuarto curso: Matemáticas A"  -> [4] (itinerario se extrae aparte)
    (
        re.compile(r"^(\w+)\s+curso\s*:\s*(.+)$"),
        lambda m: _curso_uno(_ORDINALES[m.group(1)]) if m.group(1) in _ORDINALES else None,
    ),
    # "Curso cuarto: Matemáticas B"
    (
        re.compile(r"^curso\s+(\w+)\s*:\s*(.+)$"),
        lambda m: _curso_uno(_ORDINALES[m.group(1)]) if m.group(1) in _ORDINALES else None,
    ),
    # "Primer curso" / "Cuarto curso"
    (
        re.compile(r"^(\w+)\s+curso$"),
        lambda m: _curso_uno(_ORDINALES[m.group(1)]) if m.group(1) in _ORDINALES else None,
    ),
    # "Curso de cuarto" / "Curso cuarto" / "Curso primero"
    (
        re.compile(r"^cursos?\s+(?:de\s+)?(\w+)$"),
        lambda m: _curso_uno(_ORDINALES[m.group(1)]) if m.group(1) in _ORDINALES else None,
    ),
]


# Itinerario A/B de Matemáticas 4.º (solo aparece en la Orden EFP/754).
RX_ITINERARIO_MATES = re.compile(
    r"matem[áa]ticas\s+([ab])\b",
    re.IGNORECASE,
)

# Catálogo de descriptores válidos (perfil de salida del Anexo I).
DESCRIPTORES_VALIDOS = {
    "CCL1", "CCL2", "CCL3", "CCL4", "CCL5",
    "CP1", "CP2", "CP3",
    "STEM1", "STEM2", "STEM3", "STEM4", "STEM5",
    "CD1", "CD2", "CD3", "CD4", "CD5",
    "CPSAA1", "CPSAA2", "CPSAA3", "CPSAA4", "CPSAA5",
    "CC1", "CC2", "CC3", "CC4",
    "CE1", "CE2", "CE3",
    "CCEC1", "CCEC2", "CCEC3", "CCEC4",
}


# ---------------------------------------------------------------------------
# Modelo intermedio
# ---------------------------------------------------------------------------


@dataclass
class CompetenciaEspecifica:
    codigo: str
    descripcion: str = ""
    descriptores: list[str] = field(default_factory=list)


@dataclass
class Criterio:
    codigo: str
    competencia: str
    descripcion: str


@dataclass
class BloqueSaberes:
    codigo: str
    titulo: str
    items: list[str] = field(default_factory=list)

    #: Código oficial de cada item, cuando el boletín se lo da (`BYG.1.A.8`).
    #: Va en paralelo a `items`, y vacío significa «este boletín no numera los
    #: saberes». El BOE y el DOGC no lo hacen; el BOJA sí. Sin este campo, el
    #: cargador les pone un contador propio —`bloque.1`, `bloque.2`— que no
    #: existe en ninguna norma y por tanto no se puede citar ni comprobar.
    codigos_items: list[str] = field(default_factory=list)


@dataclass
class MateriaCiclo:
    materia_oficial: str   # Nombre oficial tal cual aparece en el BOE
    materia_corta: str     # Etiqueta usada en la app (ej. "Tecnología")
    ciclo: str             # Texto descriptivo del ciclo o "Único"
    cursos_aplicables: list[str]
    itinerario: str | None = None  # "A" o "B" para Matemáticas 4.º, None resto

    competencias: list[CompetenciaEspecifica] = field(default_factory=list)
    criterios: list[Criterio] = field(default_factory=list)
    saberes: list[BloqueSaberes] = field(default_factory=list)

    @property
    def materia_efectiva(self) -> str:
        """Nombre de la materia para la app, incluyendo itinerario si lo hay."""
        if self.itinerario:
            return f"{self.materia_corta} {self.itinerario}"
        return self.materia_corta

    def to_dict(self) -> dict:
        return {
            "materia_oficial": self.materia_oficial,
            "materia": self.materia_efectiva,
            "etapa": "ESO",
            "ciclo": self.ciclo,
            "itinerario": self.itinerario,
            "cursos_aplicables": self.cursos_aplicables,
            "competencias_especificas": [
                {
                    "codigo": c.codigo,
                    "descripcion": c.descripcion,
                    "descriptores": c.descriptores,
                }
                for c in self.competencias
            ],
            "criterios_evaluacion": [
                {
                    "codigo": cr.codigo,
                    "competencia": cr.competencia,
                    "descripcion": cr.descripcion,
                }
                for cr in self.criterios
            ],
            "saberes_basicos": [
                {
                    "codigo": b.codigo,
                    "bloque": f"{b.codigo}. {b.titulo}",
                    "titulo": b.titulo,
                    "items": b.items,
                }
                for b in self.saberes
            ],
        }


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _texto(p: etree._Element) -> str:
    return " ".join(p.itertext()).strip()


def _norm(t: str) -> str:
    """Forma canónica para *comparar* un párrafo con un marcador conocido.

    Normaliza los espacios raros por lo mismo que ``_norm_cabecera``: se usa
    para igualdades exactas ("competencias específicas", "saberes básicos", el
    título de un artículo) y un U+00A0 en medio las rompería sin dar ningún
    error, dejando sin leer todo el bloque que venía detrás.

    Solo se usa para comparar, nunca para guardar: lo que acaba en el JSON es
    siempre el texto original del BOE.
    """
    return _norm_cabecera(t).rstrip(".").strip().lower()


#: Espacios que el BOE usa como separador dentro de un nombre pero que no son
#: el U+0020 corriente: espacio duro, espacio duro fino y espacio fino.
_ESPACIOS_RAROS = re.compile(r"[   ]")


def _norm_cabecera(t: str) -> str:
    """Deja una cabecera de materia comparable con las claves del perfil.

    El BOE mete espacios duros (U+00A0) dentro de cuatro nombres de materia
    del RD 217/2022: "Economía y\\xa0Emprendimiento", "Física y\\xa0Química",
    "Educación Plástica, Visual y\\xa0Audiovisual" y "Educación en Valores
    Cívicos y\\xa0Éticos". Sin normalizar, ``texto in materias_objetivo``
    compara U+00A0 contra U+0020 y **nunca** casa, por mucho que la clave
    esté bien escrita. El síntoma no es un error sino una materia que
    simplemente no aparece en la salida.

    Solo se aplica a las cabeceras. El cuerpo (criterios, saberes) conserva
    sus espacios duros, que ahí sí son tipografía intencionada del BOE
    ("5 %", "art. 4") y no queremos reescribir el texto oficial.
    """
    return re.sub(r"\s+", " ", _ESPACIOS_RAROS.sub(" ", t)).strip()


def _parsear_ciclo(
    t: str,
    palabra_curso: str = "curso",
    patrones: "list[tuple[re.Pattern[str], Callable]] | None" = None,
) -> tuple[str, list[str], str | None] | None:
    """Reconoce un marcador de ciclo y devuelve ``(nombre, cursos, itinerario)``.

    El itinerario es "A" o "B" solo si el marcador menciona "Matemáticas A/B"
    (caso de la Orden EFP/754 para 4.º curso). En el resto de casos es None.
    """
    norm = _norm(t)
    # Atajo: si la palabra del perfil no aparece, no puede ser un marcador de
    # ciclo. Cubre todas las variantes ("Primer curso", "Cursos de primero a
    # tercero", "Cuarto curso: Matemáticas A", etc.).
    #
    # Es rendimiento **y** idioma: el literal "curso" estaba escrito aquí, y en
    # un decreto catalán («primer curs») descartaría todos los marcadores antes
    # de mirarlos. No daría error: daría materias sin cursos.
    if palabra_curso not in norm:
        return None

    for regex, fn in (patrones if patrones is not None else RX_CICLOS):
        m = regex.match(norm)
        if m is None:
            continue
        cursos = fn(m)
        if cursos is None:
            continue
        # Detección del itinerario A/B si aparece en el marcador
        itinerario: str | None = None
        if len(m.groups()) >= 2:
            posible_itin = m.group(2)
            mi = RX_ITINERARIO_MATES.search(posible_itin or "")
            if mi:
                itinerario = mi.group(1).upper()
        return t.strip().rstrip("."), cursos, itinerario

    return None


def _extraer_descriptores(texto: str) -> list[str]:
    match = RX_DESCRIPTORES.search(texto)
    if not match:
        return []
    fragmento = match.group(1)
    codigos = re.findall(r"\b[A-Z]+\d+\b", fragmento)
    return [c for c in codigos if c in DESCRIPTORES_VALIDOS]


def _limpiar_item_saber(texto: str) -> str:
    """Quita el guion inicial (tipo '−', '–', '-', '—') y espacios."""
    return re.sub(r"^[\u2212\u2013\u2014\-]\s*", "", texto).strip()


# ---------------------------------------------------------------------------
# Iterador de párrafos
# ---------------------------------------------------------------------------


def leer_parrafos_boe(xml_path: Path) -> Iterator[tuple[str, str]]:
    """Lector del XML del BOE: ``<texto>`` con ``<p class="...">``.

    Deja de ser privado porque ahora es **un** lector, no **el** lector: es el
    valor por defecto de `Perfil.lector`, y otro boletín traerá el suyo.
    """
    tree = etree.parse(str(xml_path))
    texto_node = tree.getroot().find("texto")
    if texto_node is None:
        raise RuntimeError("El XML no contiene un nodo <texto>.")
    for p in texto_node.iter("p"):
        clase = p.get("class") or ""
        texto = _texto(p)
        if texto:
            yield clase, texto


#: Etiquetas que usa `leer_parrafos_akn_eadop` en lugar de las clases CSS del
#: BOE. No hay clases: el papel del párrafo lo da su sitio en el árbol.
CLASE_AKN_TITULO = "akn_heading"
CLASE_AKN_TEXTO = "akn_p"


def leer_parrafos_akn_eadop(xml_path: Path) -> Iterator[tuple[str, str]]:
    """Lector del Akoma Ntoso que publica el Portal Jurídic de Catalunya.

    LO QUE ESTE FORMATO **NO** ES
    ------------------------------
    Akoma Ntoso es un estándar legislativo con jerarquía semántica: artículos,
    apartados y listas son elementos con identidad. Al leer la documentación yo
    di por hecho que el DOGC lo usaría así, y **es falso**. Lo que publica el
    EADOP es:

    * un `<body>` plano de `<hcontainer>` sin `eId` ni numeración — el número
      de artículo no está en ninguna parte, solo su posición y su título;
    * y el texto **dentro del atributo `@period`**, escapado como HTML.

    `period` es, en el esquema de Akoma Ntoso, la vigencia temporal de un
    elemento. Meter ahí el cuerpo del documento es un abuso del formato, pero
    es lo que hay, y es exactamente el tipo de cosa que no se puede adivinar
    desde la especificación: había que abrir el fichero.

    Consecuencia práctica: **este lector se parece más al del BOE que a un
    lector de Akoma Ntoso de verdad**. Saca párrafos de un HTML, solo que el
    HTML viene dentro de un atributo.

    LO QUE TAMPOCO TRAE
    -------------------
    El currículo. Los anexos son enlaces a PDF; el Anexo 3 —las materias de la
    ESO— es `ANNEX3Matriessecundriaobligatriadefcat.pdf`. De este XML sale el
    articulado, que es de donde se deriva qué materia se imparte en qué curso.
    """
    tree = etree.parse(str(xml_path))
    body = tree.getroot().find(f"{{{_NS_AKN}}}act/{{{_NS_AKN}}}body")
    if body is None:
        raise RuntimeError("El XML no tiene <act><body>: ¿es Akoma Ntoso?")

    for contenedor in body.iter(f"{{{_NS_AKN}}}hcontainer"):
        cabecera = contenedor.find(f"{{{_NS_AKN}}}heading")
        if cabecera is not None:
            titulo = _norm_cabecera(" ".join(cabecera.itertext()))
            if titulo:
                yield CLASE_AKN_TITULO, titulo

        cuerpo = contenedor.find(f"{{{_NS_AKN}}}content")
        if cuerpo is None:
            continue
        for parrafo in _parrafos_de_html(cuerpo.get("period") or ""):
            yield CLASE_AKN_TEXTO, parrafo


def _parrafos_de_html(crudo: str) -> Iterator[str]:
    """Trocea el HTML escapado del `@period` en párrafos de texto plano.

    Se corta por `</p>` y por `<br>` **a la vez**: el EADOP usa los dos para lo
    mismo, y los items de una enumeración («a) Aranès i Literatura a l'Aran»)
    van separados por `<br />` dentro de un solo `<p>`. Cortando solo por
    párrafo, las trece materias de un artículo llegarían pegadas en una línea y
    `RX_ITEM_LETRA` no reconocería ninguna.
    """
    texto = unescape(crudo)
    for trozo in re.split(r"(?i)</p\s*>|<br\s*/?>", texto):
        limpio = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", trozo)).strip()
        if limpio:
            yield limpio


# ---------------------------------------------------------------------------
# Máquina de estados
# ---------------------------------------------------------------------------


_S_FUERA = "fuera"
_S_DESC_CE = "desc_ce"
_S_CRITERIOS = "criterios"
_S_SABERES = "saberes"


class _Parser:
    def __init__(self, perfil: Perfil) -> None:
        self.perfil = perfil
        self.resultados: list[MateriaCiclo] = []
        self.materia_oficial: str | None = None
        self.actual: MateriaCiclo | None = None
        self.estado: str = _S_FUERA
        self.ce_actual: CompetenciaEspecifica | None = None
        self.bloque_actual: BloqueSaberes | None = None
        #: cabecera normalizada -> clave literal de ``materias_objetivo``.
        #: Guardamos la clave original porque ``cursos_por_defecto`` y
        #: ``materias_objetivo`` se indexan por ella.
        self._indice_cabeceras: dict[str, str] = {
            _norm_cabecera(clave): clave for clave in perfil.materias_objetivo
        }

    # ---- helpers ---------------------------------------------------------

    def _cerrar_ce_actual(self) -> None:
        if self.ce_actual is not None and self.actual is not None:
            self.actual.competencias.append(self.ce_actual)
        self.ce_actual = None

    def _cerrar_bloque_actual(self) -> None:
        if self.bloque_actual is not None and self.actual is not None:
            # Si ya existe un bloque con el mismo código (caso típico:
            # los "sentidos" de Matemáticas que aparecen tres veces,
            # uno por curso del ciclo 1.º-3.º), fusionamos los items en
            # lugar de duplicar el bloque.
            existente = next(
                (b for b in self.actual.saberes if b.codigo == self.bloque_actual.codigo),
                None,
            )
            if existente is not None:
                existente.items.extend(self.bloque_actual.items)
            else:
                self.actual.saberes.append(self.bloque_actual)
        self.bloque_actual = None

    def _cerrar_ciclo_actual(self) -> None:
        if self.actual is not None:
            self._cerrar_ce_actual()
            self._cerrar_bloque_actual()
            self.resultados.append(self.actual)
        self.actual = None
        self.estado = _S_FUERA
        self.ce_actual = None
        self.bloque_actual = None

    def _abrir_materia(self, oficial: str) -> None:
        self._cerrar_ciclo_actual()
        self.materia_oficial = oficial
        self.actual = MateriaCiclo(
            materia_oficial=oficial,
            materia_corta=self.perfil.materias_objetivo[oficial],
            ciclo="Único",
            cursos_aplicables=list(
                self.perfil.cursos_por_defecto.get(
                    oficial, ["1º ESO", "2º ESO", "3º ESO", "4º ESO"]
                )
            ),
        )

    def _cambiar_ciclo(
        self,
        ciclo: str,
        cursos: list[str],
        itinerario: str | None,
    ) -> None:
        if self.materia_oficial is None or self.actual is None:
            return

        self._cerrar_ce_actual()
        self._cerrar_bloque_actual()

        competencias_heredadas = list(self.actual.competencias)

        # Descarta el ciclo "Único" si solo era contenedor de descripciones de CE
        if (
            self.actual.ciclo == "Único"
            and not self.actual.criterios
            and not self.actual.saberes
        ):
            pass
        else:
            self.resultados.append(self.actual)

        self.actual = MateriaCiclo(
            materia_oficial=self.materia_oficial,
            materia_corta=self.perfil.materias_objetivo[self.materia_oficial],
            ciclo=ciclo,
            cursos_aplicables=list(cursos),
            itinerario=itinerario,
            competencias=competencias_heredadas,
        )
        self.estado = _S_FUERA
        self.ce_actual = None
        self.bloque_actual = None

    # ---- detección de cabecera de materia --------------------------------

    def _es_cabecera_materia(self, clase: str, texto: str) -> str | None:
        """Si el párrafo es cabecera de una materia objetivo, devuelve la clave
        en ``perfil.materias_objetivo``; en caso contrario None."""
        if clase != self.perfil.clase_cabecera_materia:
            return None
        return self._indice_cabeceras.get(_norm_cabecera(texto))

    def _es_cabecera_otra_materia(self, clase: str, texto: str) -> bool:
        """True si el párrafo es cabecera de una materia DISTINTA a las del
        scope. Sirve para cerrar la materia actual."""
        if clase != self.perfil.clase_cabecera_materia:
            return False
        # Heurística por perfil
        if self.perfil.cabecera_mayusculas:
            # Cabeceras de materia en mayúsculas, generalmente > 4 letras y
            # sin minúsculas. Evita falsos positivos como sub-secciones.
            if texto.isupper() and len(texto) > 4:
                # Excluir secciones genéricas que también van en mayúsculas
                excluidas = {
                    "CRITERIOS DE EVALUACIÓN", "SABERES BÁSICOS",
                    "COMPETENCIAS ESPECÍFICAS",
                }
                return texto not in excluidas
            return False
        else:
            # Perfil RD: cualquier centro_negrita con texto largo es candidata.
            return len(texto) > 4 and texto[0].isupper()

    # ---- procesamiento ---------------------------------------------------

    def procesar(self, clase: str, texto: str) -> None:  # noqa: C901
        # 1) Cabecera de materia (del scope)
        oficial = self._es_cabecera_materia(clase, texto)
        if oficial is not None:
            self._abrir_materia(oficial)
            return

        # 2) Cabecera de OTRA materia (fuera del scope) → cierra la actual
        if self.materia_oficial is not None and self._es_cabecera_otra_materia(clase, texto):
            self._cerrar_ciclo_actual()
            self.materia_oficial = None
            return

        if self.materia_oficial is None or self.actual is None:
            return

        # 2.5) Fin del contenido curricular de la materia. Después aparecen
        # comentarios metodológicos que incluyen sub-marcadores con la
        # palabra "curso" y nos descolocarían el parser.
        if _norm(texto).startswith("orientaciones metodológicas"):
            self._cerrar_ciclo_actual()
            self.materia_oficial = None
            return

        # 3) Marcador de ciclo
        ciclo_info = _parsear_ciclo(
            texto, self.perfil.palabra_curso, self.perfil.ciclos
        )
        if ciclo_info is not None:
            nombre, cursos, itin = ciclo_info
            # Caso especial: en la Orden EFP/754, los saberes de Matemáticas
            # 1.º-3.º se subdividen por curso individual ("Primer curso",
            # "Segundo curso", "Tercer curso") mientras los criterios son
            # comunes al ciclo. Si estamos en SABERES y el nuevo "ciclo"
            # propuesto está totalmente incluido en el ciclo actual, lo
            # tratamos como sub-encabezado (ignorado) en lugar de cambio.
            actual_set = set(self.actual.cursos_aplicables)
            nuevo_set = set(cursos)
            if (
                self.estado == _S_SABERES
                and itin is None
                and nuevo_set.issubset(actual_set)
                and nuevo_set != actual_set
            ):
                # Subdivisión interna: la ignoramos como marcador de ciclo
                # pero seguimos en SABERES acumulando los siguientes bloques
                # al ciclo actual.
                return
            self._cambiar_ciclo(nombre, cursos, itin)
            return

        # 4) Marcadores de sección
        if _norm(texto) == self.perfil.marcador_competencias:
            self._cerrar_ce_actual()
            self.estado = _S_DESC_CE
            return
        if _norm(texto) == self.perfil.marcador_criterios:
            self._cerrar_ce_actual()
            self.estado = _S_CRITERIOS
            return
        if _norm(texto) == self.perfil.marcador_saberes:
            self._cerrar_bloque_actual()
            self.estado = _S_SABERES
            return

        # 5) Contenido según estado
        if self.estado == _S_DESC_CE:
            self._procesar_descripcion_ce(texto)
        elif self.estado == _S_CRITERIOS:
            self._procesar_criterio(texto)
        elif self.estado == _S_SABERES:
            self._procesar_saber(texto)

    def _procesar_descripcion_ce(self, texto: str) -> None:
        descriptores = _extraer_descriptores(texto)
        if descriptores and self.ce_actual is not None:
            self.ce_actual.descriptores = descriptores
            return

        m = RX_CE_INICIO.match(texto)
        if m:
            num = m.group(1)
            descripcion = m.group(2).strip()
            self._cerrar_ce_actual()
            self.ce_actual = CompetenciaEspecifica(
                codigo=f"CE{num}",
                descripcion=descripcion,
            )

    def _procesar_criterio(self, texto: str) -> None:
        # Cabeceras "Competencia específica N." son visuales: las ignoramos.
        if RX_CE_HEADER_CRIT.match(texto):
            return
        m = RX_CRITERIO.match(texto)
        if m and self.actual is not None:
            ce = m.group(1)
            self.actual.criterios.append(
                Criterio(
                    codigo=f"{ce}.{m.group(2)}",
                    competencia=f"CE{ce}",
                    descripcion=m.group(3).strip(),
                )
            )

    def _procesar_saber(self, texto: str) -> None:
        # Bloque "A. Sentido numérico."
        m = RX_BLOQUE_SABER.match(texto)
        if m:
            self._cerrar_bloque_actual()
            self.bloque_actual = BloqueSaberes(
                codigo=m.group(1),
                titulo=m.group(2).strip(),
            )
            return

        # Sub-encabezado numérico ("1. Conteo.") → ignorado, no es item.
        if RX_SUBENCAB_SABER.match(texto):
            return

        if self.bloque_actual is not None:
            item = _limpiar_item_saber(texto)
            if item:
                self.bloque_actual.items.append(item)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def extraer(xml_path: Path, perfil: Perfil) -> list[MateriaCiclo]:
    parser = _Parser(perfil)
    for clase, texto in perfil.leer(xml_path):
        parser.procesar(clase, texto)
    parser._cerrar_ciclo_actual()
    return parser.resultados


# ---------------------------------------------------------------------------
# Cursos en los que se imparte cada materia
# ---------------------------------------------------------------------------
#
# El dato NO está en la sección curricular de cada materia: allí solo aparece
# el ciclo cuando la materia divide su currículo ("Cursos de primero a
# tercero" / "Cuarto curso"). Las materias que no lo dividen —Latín,
# Digitalización, Economía y Emprendimiento...— no dicen nada, y el extractor
# les asignaba 1.º-4.º por defecto. Eso hace que el formulario ofrezca Latín
# en 1.º de ESO, que no existe.
#
# Dónde sí está: en la parte dispositiva del RD, artículos 8, 9 y 10.

RX_ARTICULO = re.compile(r"^Art[íi]culo\s+(\d+)\.\s*(.*)$")
RX_APARTADO = re.compile(r"^(\d+)\.\s")
RX_ITEM_LETRA = re.compile(r"^[a-z]\)\s+(.+)$")

#: "…, y Música en primer curso." La Orden EFP/754 mete varias materias en un
#: mismo item y dice el curso al final; el RD 217 no lo hace nunca.
RX_CURSO_EN_ITEM = re.compile(
    r"\ben\s+(primer|segundo|tercer|cuarto)\s+curso\b", re.IGNORECASE
)

_PRIMEROS_TRES = ["1º ESO", "2º ESO", "3º ESO"]
_TODA_LA_ETAPA = ["1º ESO", "2º ESO", "3º ESO", "4º ESO"]

#: Títulos que deben tener los artículos configurados en
#: ``Perfil.articulos_cursos``, en el mismo orden.
_TITULOS_ESPERADOS = (
    "organización de los tres primeros cursos",
    "organización del cuarto curso",
    "educación en valores cívicos y éticos",
)


def _fuentes_de_cursos(perfil: Perfil) -> dict[tuple[int, int | None], list[str]]:
    """``(artículo, apartado) -> cursos`` que otorga a las materias que lista.

    Apartado ``None`` significa "el cuerpo del artículo, que no tiene items".

    Los apartados 1 y 2 de cada artículo de organización son los que enumeran
    materias; el 3 en adelante habla de optativas y de horario libre, y ahí
    aparecen nombres de materia que **no** implican que se impartan en ese
    curso (el 8.4 del RD nombra Cultura Clásica y una segunda lengua
    extranjera sin fijarles curso). Por eso solo se leen el 1 y el 2.
    """
    tres, cuarto, valores = perfil.articulos_cursos
    fuentes: dict[tuple[int, int | None], list[str]] = {
        (tres, 1): _PRIMEROS_TRES,
        (tres, 2): _PRIMEROS_TRES,
        (cuarto, 1): ["4º ESO"],
        (cuarto, 2): ["4º ESO"],
    }
    if valores is not None:
        fuentes[(valores, None)] = _TODA_LA_ETAPA
    return fuentes


def derivar_cursos(xml_path: Path, perfil: Perfil) -> dict[str, list[str]]:
    """Devuelve ``materia oficial -> cursos`` leyendo la parte dispositiva.

    Qué artículos son lo dice ``perfil.articulos_cursos``: el RD 217 los
    numera 8, 9 y 10, y la Orden EFP/754, 9 y 10 (esta no dedica artículo a
    Valores Cívicos, lo mete como un item más del 9.2).

    **Emparejamiento.** Se buscan todas las materias que aparecen en el item,
    de la más larga a la más corta, tachando lo ya emparejado. El orden es
    necesario por un par: "Tecnología" es prefijo de "Tecnología y
    Digitalización", así que buscando la corta primero el item "Tecnología y
    Digitalización." se lo quedaría Tecnología —que es de 4.º— y Tecnología y
    Digitalización se quedaría sin ningún curso. Tachar lo emparejado evita
    lo contrario: que "Tecnología y Digitalización" deje suelta una
    "Tecnología" que se contaría dos veces.

    **Por qué "todas" y no "la primera".** El RD pone una materia por item,
    pero la Orden agrupa: "a) Biología y Geología, Educación Plástica, Visual
    y Audiovisual, y Música en primer curso." Quedarse con la primera perdería
    dos de cada tres. Y no se puede partir por comas, porque "Educación
    Plástica, Visual y Audiovisual" lleva una dentro.

    **Curso dentro del item.** Si el item termina en "en primer curso" y
    similares, ese curso manda sobre el del apartado. Es como la Orden reparte
    las materias no comunes de 1.º a 3.º.

    Una materia puede recibir cursos de varios sitios (Física y Química sale
    en el artículo de 1.º-3.º y en el de 4.º, luego se imparte en los cuatro).
    Se acumulan.

    Las materias que no aparecen en ninguno de estos artículos no salen en el
    resultado. No es un fallo: las optativas de centro (Cultura Clásica,
    Introducción a la Filosofía, Medios y Recursos Digitales) las autoriza la
    Dirección Provincial curso a curso, y la norma no les fija ninguno.
    """
    materias = list(perfil.materias_objetivo)
    acumulado: dict[str, set[str]] = {m: set() for m in materias}
    fuentes = _fuentes_de_cursos(perfil)
    ordinales = {"primer": "1º ESO", "segundo": "2º ESO",
                 "tercer": "3º ESO", "cuarto": "4º ESO"}

    # Se compara en mayúsculas porque el perfil de la Orden EFP/754 guarda los
    # nombres como aparecen en sus cabeceras ("LENGUA EXTRANJERA") mientras que
    # su parte dispositiva los escribe normal ("Lengua Extranjera"). Aquí
    # plegar el caso es seguro: no hay dos materias que solo se distingan por
    # mayúsculas. En las cabeceras no lo es, y por eso ``_norm_cabecera`` no
    # lo hace.
    en_mayusculas = {m.upper(): m for m in materias}
    por_longitud = sorted(en_mayusculas, key=len, reverse=True)

    def _asignar(texto: str, cursos: list[str]) -> None:
        restante = _norm_cabecera(texto).upper()
        for clave in por_longitud:
            if clave in restante:
                acumulado[en_mayusculas[clave]].update(cursos)
                restante = restante.replace(clave, " ")

    articulo: int | None = None
    apartado: int | None = None
    esperados = dict(zip(perfil.articulos_cursos, _TITULOS_ESPERADOS))

    for _clase, texto in perfil.leer(xml_path):
        cabecera = RX_ARTICULO.match(texto.strip())
        if cabecera is not None:
            articulo = int(cabecera.group(1))
            apartado = None
            esperado = esperados.get(articulo)
            if esperado is not None:
                real = _norm(cabecera.group(2))
                if real != esperado:
                    raise RuntimeError(
                        f"El artículo {articulo} se titula {real!r} y esperábamos "
                        f"{esperado!r}. El reparto de cursos por artículo ya no "
                        f"es válido para este XML."
                    )
            continue

        if articulo is None:
            continue

        num = RX_APARTADO.match(texto)
        if num is not None:
            apartado = int(num.group(1))
            continue

        item = RX_ITEM_LETRA.match(texto.strip())
        if item is not None:
            cursos = fuentes.get((articulo, apartado))
            if cursos:
                dentro = RX_CURSO_EN_ITEM.search(item.group(1))
                if dentro is not None:
                    cursos = [ordinales[dentro.group(1).lower()]]
                _asignar(item.group(1), cursos)
            continue

        # Artículos sin items: la materia va en el cuerpo del párrafo.
        cursos = fuentes.get((articulo, None))
        if cursos:
            _asignar(texto, cursos)

    orden = {c: i for i, c in enumerate(_TODA_LA_ETAPA)}
    derivados = {
        materia: sorted(cursos, key=lambda c: orden[c])
        for materia, cursos in acumulado.items()
        if cursos
    }

    # LA PARTE DISPOSITIVA ES UNA CONVENCIÓN DEL BOE, NO DEL CURRÍCULO
    # -----------------------------------------------------------------
    # `RX_ARTICULO` busca "Artículo N." y `_TITULOS_ESPERADOS` los compara con
    # tres títulos en castellano. En un boletín que reparta los cursos de otra
    # forma —o que los diga en otro idioma— aquí no casa nada y esta función
    # devuelve un diccionario vacío.
    #
    # Vacío **no es un error** para quien llama: significa "ninguna materia
    # tiene curso derivado", y entonces todas se quedan con
    # `cursos_por_defecto`. Es decir, el extractor terminaría bien, escribiría
    # sus JSON y el currículo saldría con los cursos equivocados sin que nada
    # lo dijera. Es exactamente la clase de fallo que este proyecto lleva
    # persiguiendo desde el 03/08 («Matemáticas · 4º ESO»).
    #
    # No se parametriza a ciegas: se avisa. Cuando haya un boletín real
    # delante se sabrá si esto necesita un mecanismo propio o si el suyo se
    # parece lo bastante al del BOE.
    if not derivados:
        logger.error(
            "Ningún artículo de %s dio cursos (se buscaban %s). Todas las "
            "materias se quedarán con cursos_por_defecto, que puede estar mal. "
            "Si este boletín no reparte los cursos en artículos dispositivos, "
            "hace falta un mecanismo propio para él.",
            perfil.nombre, perfil.articulos_cursos,
        )

    return derivados


# ---------------------------------------------------------------------------
# Volcado en disco
# ---------------------------------------------------------------------------


def _slugify(s: str) -> str:
    s = s.lower()
    reemplazos = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "ü": "u"}
    for k, v in reemplazos.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _nombre_fichero(mc: MateriaCiclo) -> str:
    """``matematicas__1_2_3.json``, ``matematicas_a__4.json``, etc."""
    base = _slugify(mc.materia_efectiva)
    digitos = []
    for c in mc.cursos_aplicables:
        m = re.match(r"(\d)", c)
        if m:
            digitos.append(m.group(1))
    suf = "_".join(digitos) if digitos else "unico"
    return f"{base}__{suf}.json"


def volcar(resultados: list[MateriaCiclo], salida: Path) -> list[Path]:
    """Escribe un JSON por bloque, **saltándose los que salen sin criterios**.

    Un bloque sin criterios de evaluación no es útil: la aplicación ofrecería
    la materia en el formulario y el docente se encontraría con que no puede
    seleccionar nada. Peor aún, no habría ningún síntoma hasta ese momento.

    Hoy solo ocurre con Segunda Lengua Extranjera, y no por un fallo del
    extractor: el BOE dice que sus enseñanzas van dirigidas "a la consecución
    de las mismas competencias específicas establecidas para la primera lengua
    extranjera" y no le publica currículo propio. Ofrecerla de verdad exige
    reutilizar el de Lengua Extranjera, que es otra tarea.

    El filtro se queda igualmente como red: si mañana una materia nueva deja
    de encajar con el perfil, saldrá por el log en vez de colarse vacía.
    """
    salida.mkdir(parents=True, exist_ok=True)
    rutas: list[Path] = []
    for mc in resultados:
        if not mc.criterios:
            logger.warning(
                "%s (%s) no tiene criterios de evaluación: no se vuelca.",
                mc.materia_oficial,
                mc.ciclo,
            )
            continue
        ruta = salida / _nombre_fichero(mc)
        ruta.write_text(
            json.dumps(mc.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rutas.append(ruta)
    return rutas


def resumen(resultados: list[MateriaCiclo]) -> str:
    lineas = []
    for mc in resultados:
        cursos = ", ".join(mc.cursos_aplicables)
        itin = f" [{mc.itinerario}]" if mc.itinerario else ""
        lineas.append(
            f"  {mc.materia_efectiva:18s}{itin:5s} ({mc.materia_oficial:34s})  "
            f"CE={len(mc.competencias):2d}  CR={len(mc.criterios):3d}  "
            f"BL={len(mc.saberes):2d}   [{cursos}]"
        )
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Extrae el currículo LOMLOE del XML del BOE a JSON."
    )
    p.add_argument("--xml", required=True, type=Path)
    p.add_argument("--salida", required=True, type=Path)
    p.add_argument(
        "--perfil",
        choices=sorted(PERFILES.keys()),
        default=PERFIL_ORDEN_EFP_754.nombre,
        help="Formato del documento de entrada (default: orden_efp_754).",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s | %(message)s",
    )

    if not args.xml.exists():
        logger.error("No existe el XML de entrada: %s", args.xml)
        return 2

    perfil = PERFILES[args.perfil]
    logger.info("Procesando XML %s con perfil %s", args.xml, perfil.nombre)
    resultados = extraer(args.xml, perfil)
    if not resultados:
        logger.warning("No se extrajo ninguna materia.")
        return 1

    print("\nResumen de extracción:")
    print(resumen(resultados))

    rutas = volcar(resultados, args.salida)
    print(f"\n✓ Generados {len(rutas)} fichero(s) JSON en {args.salida}:")
    for r in rutas:
        print(f"   - {r.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
