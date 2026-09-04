"""Lo que cambia entre la ESO y Bachillerato en los PDF por materia de la XTEC.

POR QUÉ UN MÓDULO Y NO UN SEGUNDO EXTRACTOR
--------------------------------------------
Mismo motivo que en `bopv_etapas`: los dos decretos catalanes —el 175/2022 de
la ESO y el 171/2022 de Bachillerato— se publican **con la misma maquetación**.
Título de materia en grande, `Competències específiques`, `Criteris
d'avaluació` en una tabla con una columna por tramo de cursos, y `Sabers` con
dos o tres niveles de sangrado.

Lo que cambia son cuatro cosas, y todas caben en una tabla:

1. **La cabecera de las columnas.** En la ESO es «1r, 2n i 3r» / «4t»; en
   Bachillerato, «1r curs» / «2n curs».
2. **El pie de página** que hay que descartar: cita un decreto u otro.
3. **Los cursos de las materias que no traen tabla.** En la ESO salen del
   articulado en Akoma Ntoso; en Bachillerato, de una tabla escrita a mano
   (abajo se explica por qué).
4. **Los saberes de Bachillerato vienen partidos por curso** dentro del mismo
   epígrafe. Esto no pasa en la ESO y es lo que más habría dolido no ver: ver
   `RX_CURSO_SABERES`.

Duplicar `extractor_xtec.py` habría significado arreglar dos veces cada una de
las rarezas que ya lleva dentro —el reparto por fronteras, los dos y tres
niveles de sangrado, las viñetas del área privada de Unicode—, y de esas ya van
varias.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Los cursos de Bachillerato, que el PDF casi nunca dice
# ---------------------------------------------------------------------------

def _bach(*n: int) -> list[str]:
    return [f"{i}º Bachillerato" for i in n]


_1R = _bach(1)
_2N = _bach(2)
_AMBOS = _bach(1, 2)


#: Curso de cada materia de Bachillerato de Cataluña.
#:
#: DE DÓNDE SALE, Y POR QUÉ NO DEL PDF
#: ------------------------------------
#: De **17 de los 79 PDF** el curso se lee dentro: son los que traen la tabla
#: de dos columnas «1r curs» / «2n curs», y para esos el extractor ni mira esta
#: tabla. Los otros **62 no dicen en ningún sitio a qué curso pertenecen**: el
#: PDF de «Biologia» y el de «Biologia, Geologia i Ciències Ambientals» son
#: tipográficamente idénticos y solo el reparto oficial distingue que el
#: primero es de 2.º y el segundo de 1.º.
#:
#: Así que sale del documento del Departament que reparte las materias por
#: curso para el curso escolar en vigor:
#:
#:   «Concreció i desenvolupament del currículum del batxillerat» (DOIGC),
#:   apartados 1.2, 1.3.1, 1.3.2, 1.3.3 y 1.3.4, versión del curso 2026-2027.
#:   https://documents.espai.educacio.gencat.cat/IPCNormativa/DOIGC/CUR_Batxillerat.pdf
#:
#: **Y no del articulado del Decret 171/2022 original**, que es lo que se hizo
#: primero y estaba mal: el **Decret 103/2026, de 7 de juliol** modificó el
#: 171/2022 y el reparto de 1.º de ciencias cambió a partir de este curso
#: —Biologia i Geologia se unifica con Ciències Ambientals, y Física con
#: Química—. El articulado que sigue publicado como «text aprovat pel Govern»
#: es el de 2022 y da el reparto anterior. Se detectó porque la XTEC publica
#: PDF de materias («Biologia, Geologia i Ciències Ambientals», «Física i
#: Química») que ese articulado no lista.
#:
#: SE ESCRIBE A MANO Y ES DELIBERADO
#: ----------------------------------
#: Igual que en el País Vasco. El DOIGC es un PDF con tablas de texto libre
#: donde la misma materia aparece con y sin numeral romano según la fila
#: («Llatí I», «Llengua i Cultura Llatines II»), y donde hay filas que no son
#: materias («Una altra matèria de qualsevol modalitat»). Un analizador que
#: acierte el 80 % produce exactamente el tipo de dato malo que este proyecto
#: persigue; una tabla transcrita se puede auditar línea a línea.
#:
#: LA CLAVE ES EL TÍTULO DEL PDF, NO EL DEL DOIGC
#: -----------------------------------------------
#: El DOIGC numera con romanos las materias que duran dos cursos («Dibuix
#: Tècnic I i II») y las de segundo («Biologia II»). El PDF de currículo no:
#: se titula «Biologia» a secas. Aquí se escribe **como lo titula el PDF**,
#: que es contra lo que se compara, y el numeral se recupera del curso.
CURSOS_BACHILLERATO: dict[str, list[str]] = {
    # --- Matèries comunes (DOIGC 1.2) ---
    # Llengua Catalana/Castellana i Literatura y Llengua Estrangera traen tabla
    # de dos columnas y no hacen falta aquí; se dejan por completitud del
    # inventario y porque cuestan una línea.
    "Llengua Castellana i Literatura": _AMBOS,
    "Llengua Catalana i Literatura": _AMBOS,
    "Llengua Estrangera": _AMBOS,
    "Educació Física": _1R,
    "Filosofia": _1R,
    "Història de la Filosofia": _2N,
    "Història": _2N,

    # --- Modalitat d'arts · via música i arts escèniques (DOIGC 1.3.1, 1.3.2) ---
    "Cultura Audiovisual": _1R,
    "Llenguatge i Pràctica Musical": _1R,
    "Anàlisi Musical": _AMBOS,
    "Arts Escèniques": _AMBOS,
    "Cor i Tècnica Vocal": _AMBOS,
    "Història de la Música i de la Dansa": _2N,
    "Literatura Dramàtica": _2N,

    # --- Modalitat d'arts · via arts plàstiques, imatge i disseny ---
    "Dibuix Artístic": _AMBOS,
    "Dibuix Tècnic Aplicat a les Arts Plàstiques i el Disseny": _AMBOS,
    "Projectes Artístics": _1R,
    "Volum": _1R,
    "Disseny": _2N,
    "Fonaments Artístics": _2N,
    "Tècniques d’Expressió Graficoplàstica": _2N,

    # --- Modalitat de ciències i tecnologia ---
    #
    # AQUÍ ESTÁ EL CAMBIO DEL DECRET 103/2026. En 1.º ya no hay «Biologia»,
    # «Física», «Química» ni «Geologia i Ciències Ambientals» por separado:
    # hay «Biologia, Geologia i Ciències Ambientals» y «Física i Química». Las
    # cuatro sueltas son **solo de 2.º** («Biologia II» en el DOIGC).
    "Matemàtiques": _AMBOS,
    "Biologia, Geologia i Ciències Ambientals": _1R,
    "Física i Química": _1R,
    "Dibuix Tècnic": _AMBOS,
    "Tecnologia i Enginyeria": _AMBOS,
    "Biologia": _2N,
    "Física": _2N,
    "Geologia i Ciències Ambientals": _2N,
    "Química": _2N,

    # --- Modalitat general ---
    "Matemàtiques Generals": _1R,
    "Economia, Emprenedoria i Activitat Empresarial": _1R,
    "Ciències Generals": _2N,
    "Moviments Culturals i Artístics": _2N,

    # --- Modalitat d'humanitats i ciències socials ---
    "Llatí": _AMBOS,
    "Grec": _AMBOS,
    "Matemàtiques Aplicades a les Ciències Socials": _AMBOS,
    "Economia": _1R,
    "Història del Món Contemporani": _1R,
    "Literatura Universal": _1R,
    "Funcionament de l’Empresa i Disseny de Models de Negoci": _2N,
    "Geografia": _2N,
    "Història de l’Art": _2N,
    "Literatura Castellana": _2N,
    "Literatura Catalana": _2N,

    # --- Optatives anuals de 1r (DOIGC 1.3.3) ---
    "Biomedicina": _1R,
    "Formació i Orientació Personal i Professional": _1R,
    "Funcionament de l’Empresa": _1R,
    "Món Clàssic": _1R,
    "Programació": _1R,
    "Psicologia": _1R,
    "Creació Fotogràfica i Cinema": _1R,
    "Llenguatges Artístics Contemporanis": _1R,
    "Projecte de Comissariat d’Exposicions": _1R,
    "Ampliació de Biologia": _1R,
    "Ampliació de Física": _1R,
    "Ampliació de Geologia i Ciències Ambientals": _1R,
    "Ampliació de Química": _1R,

    # --- Optatives trimestrals de 1r ---
    "Ciutadania, Política i Dret": _1R,
    "Comunicació Audiovisual": _1R,
    "Creació Literària": _1R,
    "Matemàtica Aplicada": _1R,
    "Problemàtiques Socials": _1R,
    "Reptes Científics Actuals (Biologia i Geologia)": _1R,
    "Reptes Científics Actuals (Física i Química)": _1R,
    "Robòtica": _1R,
    "Disseny 2D i 3D": _1R,
    "Música i Comunicació": _1R,
    "Publicitat": _1R,
    "Taller de Creació Escènica": _1R,

    # --- Optatives de 2n (DOIGC 1.3.4) ---
    #
    # Un solo PDF para las tres optativas trimestrales de ODS —«Entorn
    # Sostenible», «Població i Prosperitat» y «Pau, Justícia i
    # Corresponsabilitat»—, que el currículo trata como tres **bloques** de una
    # misma materia y no como tres materias. Se carga como una.
    "Objectius de Desenvolupament Sostenible (ODS)": _2N,

    # Estas dos son de los dos cursos y lo dicen ellas mismas:
    #
    # «Estada a l'Empresa és una matèria optativa del currículum de batxillerat
    #  que es pot cursar a primer o a segon curs» (su propio PDF).
    #
    # Segona Llengua Estrangera es «I» en 1.º y «II» en 2.º —DOIGC 1.3.3 y
    # 1.3.4— con un currículo único de diez competencias sin partir por curso,
    # igual que la Llengua Estrangera común.
    "Estada a l’Empresa": _AMBOS,
    "Segona Llengua Estrangera": _AMBOS,
}


#: Materias cuyo PDF sigue colgado del portal pero es la **edición anterior**
#: de otra que también está: mismo currículo palabra por palabra salvo el
#: nombre, que el Decret 103/2026 cambió.
#:
#: No se descartan en el guion de descarga sino aquí, y a propósito: bajarlas
#: cuesta nada y así queda constancia en disco de que el portal las sirve. Lo
#: que no puede pasar es que se carguen las dos, porque `volcar` escribe por
#: nombre de materia y la que se procesara la última pisaría a la otra —y el
#: orden alfabético de los ficheros haría ganar justo a la vieja—.
#:
#: Se comprobó con un diff: los dos PDF de latín difieren en 276 caracteres, y
#: todos son la sustitución del nombre de la materia dentro del texto.
EDICIONES_ANTERIORES: dict[str, str] = {
    "Llengua i Cultura Llatines": "Llatí",
}


# ---------------------------------------------------------------------------
# La etapa
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EtapaXTEC:
    """Lo que el extractor de la XTEC necesita saber de una etapa."""

    #: Lo que se escribe en el JSON y acaba en la columna `etapa`.
    nombre: str
    #: Sufijo de los cursos: «1º ESO», «1º Bachillerato».
    sufijo_curso: str
    #: Pie de página que se repite en todas las páginas y no es contenido.
    #: Cita el decreto, así que **cambia con la etapa**: si se deja el de la
    #: ESO, la línea «Decret 171/2022…» no se descarta y compite por ser el
    #: título de la materia.
    rx_pie: re.Pattern[str]
    #: Cabecera de columna de la tabla de criterios.
    rx_cabecera_cursos: re.Pattern[str]
    #: Ordinal de la cabecera -> número de curso.
    ordinales: dict[str, int]
    #: Ordinal largo de la cabecera que parte los saberes por curso —«Primer i
    #: segon curs»— y su número. Vacío significa que la etapa no la usa.
    ordinales_saberes: dict[str, int] = field(default_factory=dict)
    #: Título de materia -> cursos, para los PDF sin tabla de dos columnas.
    cursos: dict[str, list[str]] = field(default_factory=dict)
    #: Título -> título vigente, para las ediciones anteriores que el portal
    #: sigue sirviendo.
    ediciones_anteriores: dict[str, str] = field(default_factory=dict)
    #: Si el título lleva coletillas de curso entre paréntesis que hay que
    #: quitar. En la ESO sí —«(matèria optativa de quart d'ESO)»—; en
    #: Bachillerato **no**, y quitarlas fundiría «Reptes Científics Actuals
    #: (Biologia i Geologia)» y «Reptes Científics Actuals (Física i Química)»
    #: en una sola materia.
    limpiar_coletilla_de_curso: bool = True

    def cursos_de_cabecera(self, texto: str) -> list[str]:
        """«1r, 2n i 3r» -> ``["1º ESO", "2º ESO", "3º ESO"]``.

        «Cursos de 1r a 3r» es un **rango**, no una lista de dos: sin
        expandirlo, la columna se quedaba con 1.º y 3.º y 2.º desaparecía.
        """
        patron = "|".join(re.escape(o) for o in self.ordinales)
        nums = [self.ordinales[o] for o in re.findall(patron, texto)]
        if len(nums) == 2 and re.search(r"\ba\b", texto):
            nums = list(range(nums[0], nums[1] + 1))
        return [f"{n}º {self.sufijo_curso}" for n in nums]

    @property
    def rx_curso_saberes(self) -> re.Pattern[str] | None:
        """Cabecera que parte los saberes por curso dentro del epígrafe.

        Se construye de `ordinales_saberes` para que cada etapa solo reconozca
        los suyos: si Bachillerato aceptara «Tercer curs» daría un tramo que
        en Bachillerato no existe.

        LA PALABRA «CURS» ES OPCIONAL Y EL PREFIJO TAMBIÉN, y las dos cosas
        las puso un PDF distinto. En la ESO conviven cinco fórmulas para decir
        lo mismo:

            Primer i segon curs            (cinco materias)
            Primer i segon                 (Ciències Socials)
            De primer a tercer curs        (Matemàtiques)
            Cursos de primer a tercer      (Música)
            Matèria optativa de quart curs (Música, el otro tramo)

        Cada una que no se reconozca deja una materia con los saberes de los
        dos cursos mezclados, y sin dar ningún error.
        """
        if not self.ordinales_saberes:
            return None
        uno = "|".join(re.escape(o) for o in self.ordinales_saberes)
        return re.compile(
            rf"^(?:cursos\s+de\s+|mat[èe]ria\s+optativa\s+de\s+|de\s+)?(?:{uno})"
            rf"(?:\s*,\s*(?:{uno})|\s+(?:i|a)\s+(?:{uno}))*(?:\s+curs)?$",
            re.I,
        )

    def curso_de_saberes(self, texto: str) -> list[str] | None:
        """«Primer i segon curs» -> ``["1º ESO", "2º ESO"]``.

        Nada si la línea no es una de esas cabeceras.
        """
        rx = self.rx_curso_saberes
        if rx is None or not rx.match(texto):
            return None
        uno = "|".join(re.escape(o) for o in self.ordinales_saberes)
        nums = [self.ordinales_saberes[o]
                for o in re.findall(uno, texto.lower())]
        if not nums:
            return None
        # «De primer a tercer curs» es un rango, no una lista de dos.
        if re.search(r"\ba\b", texto.lower()) and len(nums) == 2:
            nums = list(range(nums[0], nums[1] + 1))
        return [f"{n}º {self.sufijo_curso}" for n in nums]


ESO = EtapaXTEC(
    nombre="ESO",
    sufijo_curso="ESO",
    rx_pie=re.compile(r"^Decret 175/2022|^\d+/\d+$"),
    # NO TODAS LAS COLUMNAS SE TITULAN «1r i 2n». Dos PDF de los 24 usan otra
    # fórmula, y con la versión anterior de este patrón —que solo aceptaba
    # ordinales sueltos— sus dos columnas **se fundían en un solo tramo**:
    #
    #   Música                        «Cursos de 1r a 3r» / «Optativa de 4t»
    #   Educació Plàstica / Expressió «(1r a 3r)» / «(4t)», debajo del nombre
    #                                 de la materia, que es lo que encabeza
    #                                 cada columna
    #
    # El resultado no era perder criterios sino mezclarlos: las tres materias
    # salían con los criterios de los dos cursos juntos y con el código
    # repetido —dos «1.1» distintos—, y al cargar, el segundo pisaba al
    # primero. Cincuenta criterios catalanes perdidos desde el 14/08.
    rx_cabecera_cursos=re.compile(
        r"^\(?(?:Cursos de\s+|Optativa de\s+)?(?:1r|2n|3r|4t)"
        r"(?:\s*,\s*(?:1r|2n|3r|4t)|\s+(?:i|a)\s+(?:1r|2n|3r|4t))*\)?$"
    ),
    ordinales={"1r": 1, "2n": 2, "3r": 3, "4t": 4},
    # LOS SABERES DE LA ESO TAMBIÉN VIENEN PARTIDOS POR CURSO, y esto se
    # descubrió mientras se hacía Bachillerato: seis de los 24 PDF ponen
    # «Primer i segon curs» y «Tercer i quart curs» dentro del epígrafe, y
    # hasta ahora cada tramo se cargaba con **los dos juegos**. Es decir, en
    # 1.º de ESO aparecían los saberes de 4.º, y al revés, en Aranès, Llengua
    # Castellana, Llengua Catalana, Llengua Estrangera, Educació Física,
    # Biologia i Geologia, Física i Química, Matemàtiques y Ciències Socials.
    ordinales_saberes={"primer": 1, "segon": 2, "tercer": 3, "quart": 4},
    # La tabla de la ESO no vive aquí: sale del articulado en Akoma Ntoso, con
    # `cursos_del_articulado`. Ver `extractor_xtec`.
    cursos={},
    limpiar_coletilla_de_curso=True,
)


BACHILLERATO = EtapaXTEC(
    nombre="Bachillerato",
    sufijo_curso="Bachillerato",
    rx_pie=re.compile(r"^Decret 171/2022|^\d+/\d+$"),
    # «1r curs» y «2n curs», cada una en su línea. La de la ESO no las casa
    # —no contempla la palabra «curs»— y sin esto las 17 materias con tabla se
    # quedaban con **los criterios de los dos cursos revueltos en un solo
    # tramo**, que es peor que quedarse sin ellos.
    rx_cabecera_cursos=re.compile(r"^(1r|2n)\s+curs$"),
    ordinales={"1r": 1, "2n": 2},
    # Dentro del epígrafe «Sabers», las materias de dos cursos ponen «Primer
    # curs» y «Segon curs» en negrita, al mismo sangrado que los títulos de
    # bloque. Sin reconocerlas, los dos juegos de saberes se mezclan y **se
    # cargan enteros en los dos cursos**: 1.º recibiría los de 2.º. Y no daría
    # ningún error, solo un currículo falso.
    ordinales_saberes={"primer": 1, "segon": 2},
    cursos=CURSOS_BACHILLERATO,
    ediciones_anteriores=EDICIONES_ANTERIORES,
    limpiar_coletilla_de_curso=False,
)


ETAPAS = {"eso": ESO, "bachillerato": BACHILLERATO}
