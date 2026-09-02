"""Lo que cambia entre la ESO y Bachillerato en los decretos del BOPV.

POR QUÉ UN MÓDULO Y NO UN SEGUNDO EXTRACTOR
--------------------------------------------
Los dos decretos —77/2023 para la Educación Básica y 76/2023 para
Bachillerato— tienen **la misma estructura**: título de materia en mayúsculas
y dentro `KONPETENTZIA ESPEZIFIKOAK`, `EBALUAZIO-IRIZPIDEAK` y
`OINARRIZKO JAKINTZAK`. Lo que cambia es de qué anexo se lee, qué etapa se
escribe y qué cursos tiene cada materia.

Duplicar `extractor_bopv.py` habría significado arreglar dos veces cada
irregularidad del boletín, y de esas ya van seis. Así que el lector es uno y
aquí vive lo que lo distingue.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EtapaBOPV:
    """Lo que el extractor necesita saber de una etapa."""

    #: Lo que se escribe en el JSON y acaba en la columna `etapa`.
    nombre: str
    #: Numeral del anexo que trae el currículo por materia. En la ESO es el
    #: III y en Bachillerato el II: confundirlos daría el currículo de
    #: primaria, que en el decreto de Educación Básica es el II.
    anexo: str
    #: El que viene detrás, para saber dónde acaba.
    anexo_siguiente: str
    #: Sufijo de los cursos: «1º ESO», «1º Bachillerato».
    sufijo_curso: str
    #: Título del Anexo -> cursos en que se imparte.
    cursos: dict[str, list[str]] = field(default_factory=dict)
    #: Cursos de lo que no está en la tabla. Vacío significa «no se sabe, y
    #: por tanto no se carga»; con valor, significa que la norma lo dice de
    #: forma genérica y ese es el reparto.
    cursos_por_defecto: list[str] = field(default_factory=list)
    #: Por qué hay un valor por defecto, para que aparezca en el aviso.
    motivo_por_defecto: str = ""


def _bach(*n: int) -> list[str]:
    return [f"{i}º Bachillerato" for i in n]


#: Cursos de cada materia de Bachillerato, **transcritos de los artículos 11 a
#: 15** del Decreto 76/2023. La clave es el título tal como aparece en el
#: Anexo II, que es de donde lee el extractor.
#:
#: SE ESCRIBE A MANO, Y ES DELIBERADO
#: -----------------------------------
#: Se intentó leerlo del articulado con una expresión regular y salieron 13 de
#: las 42, con ruido: frases como «Latina II edo Gizarte Zientziei Aplikatutako
#: Matematika II» aparecían como si fueran una materia. Los apartados mezclan
#: listas `a) b) c)` con materias nombradas dentro de la prosa, y eso no se
#: analiza de forma fiable. Una tabla escrita leyendo la norma es auditable;
#: un analizador que acierta el 30 % produce exactamente el tipo de dato malo
#: que este proyecto persigue.
#:
#: EL NUMERAL ROMANO DEL ARTICULADO NO ESTÁ EN EL ANEXO
#: -----------------------------------------------------
#: El articulado distingue «Matematika I» (1.º) de «Matematika II» (2.º), pero
#: el Anexo II las junta bajo un solo título, «MATEMATIKA», con un currículo
#: común que a veces separa el segundo curso con «Bigarren maila». Por eso las
#: materias con I y II salen aquí con los dos cursos.
CURSOS_BACHILLERATO: dict[str, list[str]] = {
    # --- Artículo 11: comunes a todas las modalidades ---
    "HEZIKETA FISIKOA": _bach(1),
    "FILOSOFIA": _bach(1),
    "ESPAINIAKO HISTORIA": _bach(2),
    "FILOSOFIAREN HISTORIA": _bach(2),
    # El anexo da un currículo conjunto para las cuatro: Euskara I y II y
    # Gaztelania I y II. Mismo caso que en la ESO.
    "EUSKARA ETA LITERATURA ETA GAZTELANIA ETA LITERATURA": _bach(1, 2),
    "ATZERRIKO LEHEN HIZKUNTZA": _bach(1, 2),

    # --- Artículo 12: modalidad de Artes ---
    "MARRAZKETA ARTISTIKOA": _bach(1, 2),
    "ARTE PLASTIKOEI ETA DISEINUARI APLIKATUTAKO MARRAZKETA TEKNIKOA": _bach(1, 2),
    "IKUS-ENTZUNEZKO KULTURA": _bach(1),
    "PROIEKTU ARTISTIKOAK": _bach(1),
    "BOLUMENA": _bach(1),
    "DISEINUA": _bach(2),
    "ARTEAREN OINARRIAK": _bach(2),
    "ADIERAZPEN GRAFIKO-PLASTIKOAREN TEKNIKAK": _bach(2),
    "ANALISI MUSIKALA": _bach(1, 2),
    "ARTE ESZENIKOAK": _bach(1, 2),
    "KORU ETA AHOTS-TEKNIKA": _bach(1, 2),
    "MUSIKA-LENGOAIA ETA -PRAKTIKA": _bach(1),
    "MUSIKAREN ETA DANTZAREN HISTORIA": _bach(2),
    "LITERATURA DRAMATIKOA": _bach(2),

    # --- Artículo 13: modalidad de Ciencias y Tecnología ---
    "MATEMATIKA": _bach(1, 2),
    "BIOLOGIA, GEOLOGIA ETA INGURUMEN ZIENTZIAK": _bach(1),
    "MARRAZKETA TEKNIKOA": _bach(1, 2),
    "FISIKA ETA KIMIKA": _bach(1),
    "TEKNOLOGIA ETA INGENIARITZA": _bach(1, 2),
    "BIOLOGIA": _bach(2),
    "FISIKA": _bach(2),
    "GEOLOGIA ETA INGURUMEN-ZIENTZIAK": _bach(2),
    "KIMIKA": _bach(2),

    # --- Artículo 14: modalidad General ---
    "MATEMATIKA OROKORRA": _bach(1),
    "EKONOMIA, EKINTZAILETZA ETA ENPRESA JARDUERA": _bach(1),
    "ZIENTZIA OROKORRAK": _bach(2),
    "KULTURA ETA ARTE MUGIMENDUAK": _bach(2),

    # --- Artículo 15: Humanidades y Ciencias Sociales ---
    "LATINA": _bach(1, 2),
    "GIZARTE ZIENTZIEI APLIKATUTAKO MATEMATIKA": _bach(1, 2),
    "GREKOA": _bach(1, 2),
    "EKONOMIA": _bach(1),
    "MUNDU GARAIKIDEAREN HISTORIA": _bach(1),
    "LITERATURA UNIBERTSALA": _bach(1),
    "ENPRESA ETA NEGOZIO EREDUEN DISEINUA": _bach(2),
    "GEOGRAFIA": _bach(2),
    "ARTEAREN HISTORIA": _bach(2),

    # --- Artículo 17.2: la única optativa con curso fijado ---
    #
    # «nahitaez eskaini behar da atzerriko bigarren hizkuntza bat Batxilergoko
    # lehen eta bigarren mailetan, eta Jarduera Fisikoa, Aisialdia eta Osasuna
    # ikasgaia bigarren mailan».
    "JARDUERA FISIKOA, AISIA ETA OSASUNA": _bach(2),
}


#: Las **optativas no llevan curso en el decreto**, y eso no es un descuido:
#: el artículo 17.1 dice que los centros pueden ofrecer cualquiera de las que
#: lista el Anexo II, sin restringir el curso. El Anexo V, que sí reparte las
#: horas, las agrupa como «Hautazkoak» sin nombrarlas.
#:
#: Así que se cargan con los dos cursos. **No es una suposición de conveniencia
#: sino lo que dice la norma**, y la alternativa —dejarlas sin cursos— las
#: haría invisibles en la aplicación, que es peor y además sería falso: el
#: decreto no dice que no se puedan dar.
_MOTIVO_OPTATIVAS = (
    "es optativa y el artículo 17.1 permite ofrecerla en cualquiera de los dos "
    "cursos"
)


ESO = EtapaBOPV(
    nombre="ESO",
    anexo="III",
    anexo_siguiente="IV",
    sufijo_curso="ESO",
    # La tabla de la ESO vive en `extractor_bopv` desde antes que este módulo;
    # se enlaza al importar para no moverla y romper sus tests.
    cursos={},
    cursos_por_defecto=[],
)

BACHILLERATO = EtapaBOPV(
    nombre="Bachillerato",
    anexo="II",
    anexo_siguiente="III",
    sufijo_curso="Bachillerato",
    cursos=CURSOS_BACHILLERATO,
    cursos_por_defecto=_bach(1, 2),
    motivo_por_defecto=_MOTIVO_OPTATIVAS,
)

ETAPAS = {"eso": ESO, "bachillerato": BACHILLERATO}
