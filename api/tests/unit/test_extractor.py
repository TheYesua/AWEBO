"""Tests del extractor del currículo del BOE.

No tocan base de datos ni Flask: el extractor es una función pura de
(XML, perfil) -> lista de MateriaCiclo.

El foco está en el reconocimiento de cabeceras de materia, que es donde
el BOE es más traicionero: un nombre que *parece* idéntico al que hemos
escrito en el perfil puede no serlo a nivel de bytes, y el síntoma no es
un error sino una materia que desaparece de la salida sin decir nada.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.curriculo.extractor import (
    CLASE_AKN_TEXTO,
    CLASE_AKN_TITULO,
    PERFIL_ORDEN_EFP_754,
    PERFIL_RD_217,
    Perfil,
    _norm_cabecera,
    derivar_cursos,
    extraer,
    leer_parrafos_akn_eadop,
    volcar,
)


#: Los XML oficiales viven en el repositorio, en ``curriculo/fuentes/<comunidad>/``
#: —una carpeta por comunidad desde el 14/08/2026—
#: justamente para que estos tests puedan volver a la fuente en vez de fiarse
#: de una transcripción.
_FUENTES = Path(__file__).resolve().parents[2].parent / "curriculo" / "fuentes"
XML_RD_217 = _FUENTES / "estatal" / "rd_217_2022.xml"
XML_ORDEN_754 = _FUENTES / "ceuta" / "orden_efp_754_2022.xml"
XML_DECRET_175 = _FUENTES / "cataluna" / "decret_175_2022.xml"


# ---------------------------------------------------------------------------
# Utilidades de construcción de XML
# ---------------------------------------------------------------------------


def _documento(parrafos: list[tuple[str, str]]) -> str:
    """Envuelve una lista de ``(clase, texto)`` en la estructura del BOE."""
    cuerpo = "\n".join(
        f'<p class="{clase}">{texto}</p>' for clase, texto in parrafos
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<documento><texto>\n{cuerpo}\n</texto></documento>'


def _materia_completa(cabecera: str) -> list[tuple[str, str]]:
    """Una materia mínima pero válida: 1 CE, 1 criterio y 1 bloque de saberes."""
    return [
        ("centro_negrita", cabecera),
        ("parrafo", "Competencias específicas."),
        ("parrafo_2", "1. Resolver problemas del entorno cercano."),
        ("parrafo_2", "Descriptores del Perfil de salida: STEM1, STEM2."),
        ("parrafo", "Criterios de evaluación."),
        ("parrafo", "Competencia específica 1."),
        ("parrafo_2", "1.1 Identificar los datos relevantes del problema."),
        ("parrafo", "Saberes básicos."),
        ("parrafo_2", "A. Resolución de problemas."),
        ("parrafo_2", "− Estrategias de descomposición."),
    ]


def _escribir(tmp_path, parrafos):
    ruta = tmp_path / "boe.xml"
    ruta.write_text(_documento(parrafos), encoding="utf-8")
    return ruta


def _perfil(materias: dict[str, str]) -> Perfil:
    return Perfil(
        nombre="prueba",
        clase_cabecera_materia="centro_negrita",
        cabecera_mayusculas=False,
        materias_objetivo=materias,
        cursos_por_defecto={},
    )


# ---------------------------------------------------------------------------
# Normalización de cabeceras
# ---------------------------------------------------------------------------


class TestNormCabecera:
    def test_espacio_normal_no_cambia(self):
        assert _norm_cabecera("Física y Química") == "Física y Química"

    @pytest.mark.parametrize(
        "raro",
        [
            " ",  # espacio duro, el que usa el BOE
            " ",  # espacio duro fino
            " ",  # espacio fino
        ],
    )
    def test_espacios_raros_pasan_a_espacio_normal(self, raro):
        assert _norm_cabecera(f"Física y{raro}Química") == "Física y Química"

    def test_colapsa_espacios_repetidos_y_recorta(self):
        assert _norm_cabecera("  Latín   y  Griego  ") == "Latín y Griego"

    def test_no_toca_acentos_ni_mayusculas(self):
        # Deliberado: las claves del perfil son el nombre oficial tal cual.
        # Si normalizásemos también el caso, "TECNOLOGÍA" del perfil de
        # Ceuta y Melilla casaría con "Tecnología" del RD y mezclaríamos
        # dos fuentes distintas.
        assert _norm_cabecera("Economía") == "Economía"
        assert _norm_cabecera("ECONOMÍA") != _norm_cabecera("Economía")


# ---------------------------------------------------------------------------
# Reconocimiento de la cabecera dentro del extractor
# ---------------------------------------------------------------------------


class TestCabeceraConEspacioDuro:
    """Regresión del fallo real del RD 217/2022.

    Cuatro materias del BOE llevan U+00A0 en la cabecera. Antes de
    normalizar, ``texto in materias_objetivo`` no casaba nunca y esas
    materias no salían en el JSON. Este test falla (0 resultados) si se
    revierte ``_norm_cabecera``.
    """

    def test_materia_con_espacio_duro_se_extrae(self, tmp_path):
        xml = _escribir(tmp_path, _materia_completa("Física y Química"))
        res = extraer(xml, _perfil({"Física y Química": "Física y Química"}))

        assert len(res) == 1, "la cabecera con U+00A0 no se ha reconocido"
        assert res[0].materia_oficial == "Física y Química"
        assert res[0].materia_corta == "Física y Química"

    def test_el_nombre_guardado_es_la_clave_del_perfil_no_el_del_boe(self, tmp_path):
        """El U+00A0 no debe filtrarse a la salida.

        ``materia_oficial`` se usa como clave en ``cursos_por_defecto`` y
        acaba en el JSON y en la BD. Si arrastrase el espacio duro, un
        ``WHERE materia = 'Física y Química'` escrito a mano no encontraría
        nada.
        """
        xml = _escribir(tmp_path, _materia_completa("Economía y Emprendimiento"))
        res = extraer(
            xml, _perfil({"Economía y Emprendimiento": "Economía y Emprendimiento"})
        )

        assert " " not in res[0].materia_oficial

    def test_contenido_completo_pese_al_espacio_duro(self, tmp_path):
        """Reconocer la cabecera no basta: hay que llegar hasta los saberes."""
        xml = _escribir(
            tmp_path, _materia_completa("Educación en Valores Cívicos y Éticos")
        )
        res = extraer(
            xml,
            _perfil(
                {"Educación en Valores Cívicos y Éticos": "Valores Cívicos y Éticos"}
            ),
        )

        mc = res[0]
        assert [c.codigo for c in mc.competencias] == ["CE1"]
        assert mc.competencias[0].descriptores == ["STEM1", "STEM2"]
        assert [c.codigo for c in mc.criterios] == ["1.1"]
        assert [b.codigo for b in mc.saberes] == ["A"]
        assert mc.saberes[0].items == ["Estrategias de descomposición."]

    def test_una_materia_sin_espacio_duro_sigue_funcionando(self, tmp_path):
        """La normalización no debe romper el caso corriente."""
        xml = _escribir(tmp_path, _materia_completa("Biología y Geología"))
        res = extraer(xml, _perfil({"Biología y Geología": "Biología y Geología"}))

        assert len(res) == 1
        assert res[0].materia_oficial == "Biología y Geología"

    def test_una_materia_fuera_del_perfil_no_se_extrae(self, tmp_path):
        """La normalización no debe ampliar el alcance por accidente."""
        xml = _escribir(tmp_path, _materia_completa("Física y Química"))
        res = extraer(xml, _perfil({"Latín": "Latín"}))

        assert res == []


# ---------------------------------------------------------------------------
# Contra el BOE de verdad
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not XML_RD_217.exists(), reason=f"no está {XML_RD_217}")
class TestContraElBOEReal:
    """Estos tests leen el RD 217/2022 completo, no un XML de juguete.

    Son lentos comparados con el resto pero es el único sitio donde se
    comprueba que lo que dice el perfil y lo que dice el BOE coinciden.
    """

    def test_estan_las_dieciocho_materias_del_anexo_ii(self):
        oficiales = {mc.materia_oficial for mc in extraer(XML_RD_217, PERFIL_RD_217)}

        assert oficiales == set(PERFIL_RD_217.materias_objetivo), (
            "hay materias del perfil que el BOE no devuelve, o al revés"
        )
        assert len(oficiales) == 18

    def test_los_ambitos_de_fp_basica_quedan_fuera(self):
        """El Anexo V se extrae igual de bien, pero no es ESO.

        ``to_dict()`` escribe ``etapa: ESO`` sin preguntar, así que colarlos
        guardaría un dato falso. Si algún día se añaden, este test debe
        cambiarse a la vez que el modelo, no antes.
        """
        oficiales = {mc.materia_oficial for mc in extraer(XML_RD_217, PERFIL_RD_217)}

        assert "Ciencias Aplicadas" not in oficiales
        assert "Comunicación y Ciencias Sociales" not in oficiales

    def test_ninguna_competencia_se_queda_sin_descriptores(self):
        """El espacio duro del BOE otra vez, esta vez en otro sitio.

        La competencia específica 2 de Biología y Geología lleva
        "descriptores del\\xa0Perfil de salida:". Con la expresión escrita con
        espacios literales no casaba y esa competencia salía con la lista de
        descriptores vacía, en las dos normas. Como el extractor no falla
        cuando no encuentra descriptores, el único síntoma era un hueco en el
        JSON.

        Este test recorre las dos fuentes precisamente para que un descuido
        así no dependa de que alguien se fije en un fichero concreto.
        """
        for xml, perfil in ((XML_RD_217, PERFIL_RD_217),
                            (XML_ORDEN_754, PERFIL_ORDEN_EFP_754)):
            if not xml.exists():
                continue
            sin_descriptores = [
                f"{mc.materia_oficial}/{mc.ciclo}/{ce.codigo}"
                for mc in extraer(xml, perfil)
                for ce in mc.competencias
                if not ce.descriptores
            ]
            assert not sin_descriptores, (
                f"{perfil.nombre}: competencias sin descriptores del Perfil "
                f"de salida: {sin_descriptores}"
            )

    def test_toda_materia_tiene_competencias_criterios_y_saberes(self):
        """Salvo Segunda Lengua Extranjera, que no tiene currículo propio."""
        vacias = []
        for mc in extraer(XML_RD_217, PERFIL_RD_217):
            saberes = sum(len(b.items) for b in mc.saberes)
            if not (mc.competencias and mc.criterios and saberes):
                vacias.append(mc.materia_oficial)

        assert set(vacias) == {"Segunda Lengua Extranjera"}, (
            f"materias sin contenido: {sorted(set(vacias))}"
        )

    def test_segunda_lengua_extranjera_remite_a_la_primera(self):
        """No es un fallo del extractor: lo dice el propio BOE.

        "Las enseñanzas de una segunda lengua extranjera deben ir dirigidas a
        la consecución de las mismas competencias específicas establecidas
        para la primera lengua extranjera". Su sección no lista ni una CE, así
        que la app debe reutilizar el currículo de Lengua Extranjera.
        """
        res = extraer(XML_RD_217, PERFIL_RD_217)
        sle = [mc for mc in res if mc.materia_oficial == "Segunda Lengua Extranjera"]

        assert len(sle) == 1
        assert sle[0].competencias == []
        assert sle[0].criterios == []

    def test_la_tabla_de_cursos_sigue_coincidiendo_con_los_articulos(self):
        """Ata ``_CURSOS_RD_217`` al texto dispositivo del RD.

        La tabla está escrita a mano en el módulo por legibilidad, pero el
        dato viene de los artículos 8, 9 y 10. Aquí se vuelve a derivar y se
        comprueba que no han divergido.
        """
        derivada = derivar_cursos(XML_RD_217, PERFIL_RD_217)

        for materia, cursos in PERFIL_RD_217.cursos_por_defecto.items():
            assert derivada[materia] == cursos, (
                f"{materia}: el perfil dice {cursos} y los artículos "
                f"{derivada[materia]}"
            )

    def test_los_articulos_reparten_cursos_como_esperamos(self):
        """Casos concretos, para que el test anterior no sea circular.

        Si ``derivar_cursos`` tuviera un bug y la tabla del perfil se hubiera
        generado con él, el test anterior seguiría verde. Estos valores están
        leídos del BOE a mano.
        """
        d = derivar_cursos(XML_RD_217, PERFIL_RD_217)

        # Artículo 9.2: materias de opción, solo cuarto.
        assert d["Latín"] == ["4º ESO"]
        assert d["Economía y Emprendimiento"] == ["4º ESO"]
        # Artículo 8.1: solo los tres primeros. En cuarto su relevo es
        # Expresión Artística.
        assert d["Educación Plástica, Visual y Audiovisual"] == [
            "1º ESO",
            "2º ESO",
            "3º ESO",
        ]
        assert d["Expresión Artística"] == ["4º ESO"]
        # Aparece en 8.1 y en 9.2: los cuatro cursos.
        assert d["Física y Química"] == ["1º ESO", "2º ESO", "3º ESO", "4º ESO"]
        # Artículo 10, que no tiene items: "en algún curso de la etapa".
        assert d["Educación en Valores Cívicos y Éticos"] == [
            "1º ESO",
            "2º ESO",
            "3º ESO",
            "4º ESO",
        ]
        # Trampa de prefijos, y la razón de emparejar del nombre más largo al
        # más corto: "Tecnología" es prefijo de "Tecnología y Digitalización".
        # Al revés, el item 8.1.j) se lo quedaría Tecnología (que es de 4.º) y
        # Tecnología y Digitalización se quedaría sin cursos.
        assert d["Tecnología"] == ["4º ESO"]
        assert d["Tecnología y Digitalización"] == ["1º ESO", "2º ESO", "3º ESO"]
        # Este otro par lo separa ``startswith`` por sí solo, sin depender del
        # orden: "Segunda Lengua Extranjera" contiene "Lengua Extranjera"
        # pero no empieza por ella.
        assert d["Segunda Lengua Extranjera"] == ["4º ESO"]
        assert d["Lengua Extranjera"] == ["1º ESO", "2º ESO", "3º ESO", "4º ESO"]

    def test_un_titulo_de_articulo_inesperado_es_un_error_ruidoso(self, tmp_path):
        """Si el BOE se renumerase, preferimos petar a repartir cursos al azar."""
        xml = _escribir(
            tmp_path,
            [
                ("parrafo", "Artículo 8. De las bicicletas y su cuidado."),
                ("parrafo", "1. Las materias serán las siguientes:"),
                ("parrafo", "a) Latín."),
            ],
        )
        with pytest.raises(RuntimeError, match="artículo 8"):
            derivar_cursos(xml, _perfil({"Latín": "Latín"}))


@pytest.mark.skipif(not XML_ORDEN_754.exists(), reason=f"no está {XML_ORDEN_754}")
class TestContraLaOrdenEFP754:
    """La Orden EFP/754 es la fuente de la que sale el currículo cargado.

    Desarrolla el mismo RD para Ceuta y Melilla, pero con dos diferencias que
    importan: parte el currículo por curso individual en vez de por ciclo, y
    trae Matemáticas A y B de cuarto, que el RD 217 no tiene.
    """

    def test_estan_las_veintiuna_materias(self):
        oficiales = {
            mc.materia_oficial for mc in extraer(XML_ORDEN_754, PERFIL_ORDEN_EFP_754)
        }

        assert oficiales == set(PERFIL_ORDEN_EFP_754.materias_objetivo)
        assert len(oficiales) == 21

    def test_trae_matematicas_de_cuarto_en_sus_dos_itinerarios(self):
        """Es la razón principal para preferir esta fuente al RD 217.

        El RD 217 no publica currículo de Matemáticas de 4.º, ni A ni B, así
        que con él ese curso se quedaría sin su materia troncal.
        """
        mates = [
            mc
            for mc in extraer(XML_ORDEN_754, PERFIL_ORDEN_EFP_754)
            if mc.materia_oficial == "MATEMÁTICAS"
        ]

        assert {mc.itinerario for mc in mates} == {None, "A", "B"}
        assert {mc.materia_efectiva for mc in mates} == {
            "Matemáticas",
            "Matemáticas A",
            "Matemáticas B",
        }

    def test_solo_segunda_lengua_extranjera_sale_sin_contenido(self):
        vacias = []
        for mc in extraer(XML_ORDEN_754, PERFIL_ORDEN_EFP_754):
            saberes = sum(len(b.items) for b in mc.saberes)
            if not (mc.competencias and mc.criterios and saberes):
                vacias.append(mc.materia_oficial)

        assert set(vacias) == {"SEGUNDA LENGUA EXTRANJERA"}

    def test_la_tabla_de_cursos_sigue_coincidiendo_con_los_articulos(self):
        derivada = derivar_cursos(XML_ORDEN_754, PERFIL_ORDEN_EFP_754)

        for materia, cursos in PERFIL_ORDEN_EFP_754.cursos_por_defecto.items():
            assert derivada[materia] == cursos, (
                f"{materia}: el perfil dice {cursos} y los artículos "
                f"{derivada[materia]}"
            )

    def test_reparte_las_materias_de_un_item_con_varias(self):
        """El artículo 9.2 mete varias materias por item y el curso al final.

            b) Educación en Valores Cívicos y Éticos, Física y Química,
               Música, y Tecnología y Digitalización en segundo curso.

        Quedarse con la primera perdería tres de cada cuatro, y partir por
        comas rompería "Educación Plástica, Visual y Audiovisual".
        """
        d = derivar_cursos(XML_ORDEN_754, PERFIL_ORDEN_EFP_754)

        # Las cuatro del item b) tienen que llevar 2.º.
        for materia in (
            "EDUCACIÓN EN VALORES CÍVICOS Y ÉTICOS",
            "FÍSICA Y QUÍMICA",
            "MÚSICA",
            "TECNOLOGÍA Y DIGITALIZACIÓN",
        ):
            assert "2º ESO" in d[materia], materia

        # Y el reparto por curso tiene que ser el de la Orden, no 1.º-3.º
        # en bloque: Biología y Geología va en 1.º y 3.º pero no en 2.º.
        assert d["BIOLOGÍA Y GEOLOGÍA"] == ["1º ESO", "3º ESO", "4º ESO"]
        assert d["EDUCACIÓN PLÁSTICA, VISUAL Y AUDIOVISUAL"] == ["1º ESO", "3º ESO"]
        assert d["TECNOLOGÍA Y DIGITALIZACIÓN"] == ["2º ESO", "3º ESO"]

    def test_no_se_vuelca_ningun_json_sin_criterios(self, tmp_path):
        """Una materia vacía en la BD es una materia rota en el formulario.

        El docente la vería en el desplegable y al entrar no podría
        seleccionar ningún criterio, sin ningún aviso previo.
        """
        res = extraer(XML_ORDEN_754, PERFIL_ORDEN_EFP_754)
        rutas = volcar(res, tmp_path)

        assert len(rutas) == len(res) - 1  # se queda fuera Segunda Lengua
        assert not (tmp_path / "segunda_lengua_extranjera__4.json").exists()
        for ruta in rutas:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            assert datos["criterios_evaluacion"], ruta.name

    def test_las_dos_tecnologias_son_materias_distintas(self):
        """Compartieron la etiqueta "Tecnología" hasta el 7/8/2026.

        No era solo un nombre corto: como ``seed_curriculo`` identifica las
        competencias por ``(codigo, materia)``, la CE1 de Tecnología de 4.º
        sobrescribía la descripción de la CE1 de Tecnología y Digitalización
        de 2.º-3.º y los cursos se fusionaban. Son siete competencias frente a
        seis, con textos que no se parecen.
        """
        res = extraer(XML_ORDEN_754, PERFIL_ORDEN_EFP_754)
        tyd = [mc for mc in res if mc.materia_oficial == "TECNOLOGÍA Y DIGITALIZACIÓN"]
        tec = [mc for mc in res if mc.materia_oficial == "TECNOLOGÍA"]

        assert {mc.materia_corta for mc in tyd} == {"Tecnología y Digitalización"}
        assert {mc.materia_corta for mc in tec} == {"Tecnología"}
        # Que las etiquetas difieran no basta: hay que ver que el contenido
        # también, o el arreglo sería cosmético.
        assert len(tyd[0].competencias) == 7
        assert len(tec[0].competencias) == 6
        assert tyd[0].competencias[0].descripcion != tec[0].competencias[0].descripcion

    def test_ninguna_etiqueta_corta_agrupa_dos_materias_del_boe(self):
        """Red para el mismo fallo en cualquier otra materia.

        Dos nombres oficiales bajo una misma etiqueta significan que el seed
        las mezclará, porque su clave de unicidad es ``(codigo, materia)``.
        Solo se acepta cuando de verdad es la misma materia con dos nombres,
        y hoy no hay ningún caso así.
        """
        agrupadas: dict[str, set[str]] = {}
        for oficial, corta in PERFIL_ORDEN_EFP_754.materias_objetivo.items():
            agrupadas.setdefault(corta, set()).add(oficial)

        colisiones = {c: sorted(o) for c, o in agrupadas.items() if len(o) > 1}
        assert not colisiones, (
            f"etiquetas que agrupan varias materias del BOE: {colisiones}"
        )

    def test_las_optativas_de_centro_no_reciben_curso(self):
        """No es un fallo: la norma no se lo fija.

        Cultura Clásica, Introducción a la Filosofía y Medios y Recursos
        Digitales las autoriza la Dirección Provincial curso a curso, así que
        se quedan con el 1.º-4.º por defecto del extractor.
        """
        d = derivar_cursos(XML_ORDEN_754, PERFIL_ORDEN_EFP_754)

        assert "CULTURA CLÁSICA" not in d
        assert "INTRODUCCIÓN A LA FILOSOFÍA" not in d
        assert "MEDIOS Y RECURSOS DIGITALES" not in d


# ---------------------------------------------------------------------------
# La costura del formato y del idioma
# ---------------------------------------------------------------------------


class TestOtroBoletinYOtroIdioma:
    """Que `Perfil` admita un boletín que no sea el BOE.

    POR QUÉ ESTE TEST NO USA EL DOGC
    ---------------------------------
    Porque todavía no tengo el documento delante, y **diseñar contra un formato
    imaginado es exactamente el error que dejó la abstracción como estaba**:
    los dos perfiles que existen son del BOE, así que todo lo que comparten se
    quedó fuera del `Perfil` sin que nadie decidiera que debía quedarse fuera.
    Repetir la jugada adivinando cómo es el Akoma Ntoso sería el mismo fallo
    con otra cara.

    Lo que sí se puede comprobar hoy, y es lo que hace falta comprobar: que los
    tres supuestos del BOE que estaban incrustados —de dónde salen los
    párrafos, en qué idioma están los marcadores y qué palabra delata un
    marcador de curso— son ahora **parámetros**, y que cambiándolos el mismo
    extractor lee otra cosa.

    El boletín de aquí es de mentira y está en catalán a propósito: es la
    primera comunidad de la fase 2, así que si algo del extractor solo funciona
    en castellano, sale aquí.
    """

    #: Un "boletín" que no es XML ni tiene clases CSS: dos columnas separadas
    #: por `|`. Deliberadamente distinto del BOE, para que ningún supuesto
    #: suyo se cuele sin que se note.
    FUENTE = "\n".join([
        "titol|Matemàtiques",
        "text|Primer curs",
        "text|Competències específiques.",
        "text2|1. Resoldre problemes de l'entorn proper.",
        "text|Criteris d'avaluació.",
        "text|Competencia específica 1.",
        "text2|1.1 Identificar les dades rellevants del problema.",
        "text|Sabers.",
        "text2|A. Resolució de problemes.",
        "text2|− Estratègies de descomposició.",
    ])

    @staticmethod
    def _lector(ruta):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            clase, _, texto = linea.partition("|")
            if texto:
                yield clase, texto

    def _perfil_catalan(self):
        return Perfil(
            nombre="ficticio_ca",
            clase_cabecera_materia="titol",
            cabecera_mayusculas=False,
            materias_objetivo={"Matemàtiques": "Matemáticas"},
            cursos_por_defecto={"Matemàtiques": ["1º ESO"]},
            lector=self._lector,
            marcador_competencias="competències específiques",
            marcador_criterios="criteris d'avaluació",
            marcador_saberes="sabers",
            palabra_curso="curs",
            patrones_ciclo=[(
                re.compile(r"^(primer|segon|tercer|quart) curs$"),
                lambda m: [f"{['primer','segon','tercer','quart'].index(m.group(1)) + 1}º ESO"],
            )],
        )

    def _extraer(self, tmp_path):
        ruta = tmp_path / "dogc_de_mentira.txt"
        ruta.write_text(self.FUENTE, encoding="utf-8")
        return extraer(ruta, self._perfil_catalan())

    def test_lee_un_formato_que_no_es_el_del_boe(self, tmp_path):
        res = self._extraer(tmp_path)

        assert len(res) == 1, "no reconoció la materia con otro lector"
        assert res[0].materia_oficial == "Matemàtiques"

    def test_encuentra_las_tres_secciones_en_catalan(self, tmp_path):
        """La que más importa. Con los marcadores en castellano incrustados,
        esto NO daba error: daba una materia con cero competencias, cero
        criterios y cero saberes. Un currículo vacío que parece cargado."""
        mc = self._extraer(tmp_path)[0]

        assert len(mc.competencias) == 1, "no encontró «Competències específiques»"
        assert len(mc.criterios) == 1, "no encontró «Criteris d'avaluació»"
        assert len(mc.saberes) == 1, "no encontró «Sabers»"

    def test_el_texto_se_guarda_en_su_idioma_sin_tocarlo(self, tmp_path):
        """`_norm` es solo para comparar. Lo que se guarda es el original, y
        con lenguas cooficiales eso deja de ser un detalle: es la diferencia
        entre citar el decreto y parafrasearlo."""
        mc = self._extraer(tmp_path)[0]

        assert mc.competencias[0].descripcion.startswith("Resoldre problemes")
        assert "Estratègies" in mc.saberes[0].items[0]

    def test_los_perfiles_del_boe_siguen_sin_declarar_lector(self):
        """El defecto tiene que seguir siendo el BOE: los dos perfiles reales
        no declaran lector, y si el defecto se rompiera dejarían de extraer
        nada. Que `lector` sea None y `leer` funcione es justo el contrato."""
        for perfil in (PERFIL_RD_217, PERFIL_ORDEN_EFP_754):
            assert perfil.lector is None
            assert perfil.leer.__self__ is perfil

    def test_un_marcador_sin_tilde_no_casa_y_conviene_saberlo(self, tmp_path):
        """`_norm` pasa a minúsculas pero **no quita los acentos**. Escribir el
        marcador sin tildes en un perfil nuevo no da error: da secciones
        vacías. Se deja escrito aquí porque es la trampa más probable al
        añadir el siguiente boletín."""
        from dataclasses import replace

        ruta = tmp_path / "dogc_de_mentira.txt"
        ruta.write_text(self.FUENTE, encoding="utf-8")
        perfil = replace(self._perfil_catalan(),
                         marcador_competencias="competencies especifiques")

        mc = extraer(ruta, perfil)[0]

        assert mc.competencias == [], "si esto falla, _norm ya quita acentos"

    def test_el_marcador_de_ciclo_tambien_se_lee_en_catalan(self, tmp_path):
        """`palabra_curso` sola era un arreglo falso.

        Cambiarla a «curs» hace que el atajo deje pasar el texto catalán, pero
        después lo miden regex que dicen «primer curso» y no casa ninguna. El
        resultado no es un error: es la materia con los cursos por defecto, que
        es peor que un fallo porque parece un dato bueno.
        """
        mc = self._extraer(tmp_path)[0]

        assert mc.cursos_aplicables == ["1º ESO"]
        assert mc.ciclo == "Primer curs", (
            "cayó en los cursos por defecto en vez de leer el marcador"
        )

    def test_si_ningun_articulo_da_cursos_se_dice_a_gritos(self, tmp_path, caplog):
        """El silencio aquí es el fallo, no el diccionario vacío.

        `derivar_cursos` devuelve {} cuando no reconoce ningún artículo, y
        quien llama lo interpreta como «ninguna materia tiene curso derivado»:
        todas se quedan con `cursos_por_defecto`. El extractor termina bien,
        escribe sus JSON, y el currículo sale con los cursos equivocados sin
        que nada lo diga. Es el fallo de «Matemáticas · 4º ESO» otra vez.
        """
        import logging

        ruta = tmp_path / "dogc_de_mentira.txt"
        ruta.write_text(self.FUENTE, encoding="utf-8")

        with caplog.at_level(logging.ERROR, logger="curriculo.extractor"):
            derivada = derivar_cursos(ruta, self._perfil_catalan())

        assert derivada == {}
        assert any("cursos_por_defecto" in r.getMessage() for r in caplog.records), (
            "se quedó callado: nadie se enteraría de que los cursos son inventados"
        )


@pytest.mark.skipif(not XML_DECRET_175.exists(), reason=f"no está {XML_DECRET_175}")
class TestElAkomaNtosoDelDOGC:
    """El lector del Portal Jurídic, contra el fichero de verdad.

    LO QUE ESTE FICHERO ENSEÑÓ, Y NO SE PODÍA SABER LEYENDO LA ESPECIFICACIÓN
    -------------------------------------------------------------------------
    Akoma Ntoso es un estándar con jerarquía semántica, y por eso se eligió
    frente al PDF. Al abrirlo resultó que el EADOP no lo usa así:

    * el `<body>` es una lista plana de `<hcontainer>` **sin `eId` ni número**;
    * el texto va **dentro del atributo `@period`**, escapado como HTML, y
      `period` es en el esquema la *vigencia temporal* del elemento;
    * y los anexos —donde vive el currículo— **no están**: son enlaces a PDF.

    O sea que el lector se parece más al del BOE que a un lector de Akoma
    Ntoso: saca párrafos de un HTML que viene dentro de un atributo. Esa es
    justo la clase de cosa por la que no se escribió este lector la sesión
    anterior, cuando el fichero todavía no estaba.
    """

    def _parrafos(self):
        return list(leer_parrafos_akn_eadop(XML_DECRET_175))

    def test_saca_titulos_y_texto_y_no_solo_una_cosa(self):
        clases = {c for c, _ in self._parrafos()}

        assert clases == {CLASE_AKN_TITULO, CLASE_AKN_TEXTO}

    def test_los_titulos_del_articulado_estan_completos(self):
        """Los dos artículos que reparten materias por curso. Son el sustituto
        catalán de los artículos 8/9/10 del BOE, y sin ellos no hay forma de
        saber que Llatí no se imparte en 1.º."""
        titulos = [x for c, x in self._parrafos() if c == CLASE_AKN_TITULO]

        assert "Matèries de l'educació secundària obligatòria de primer a tercer curs" in titulos
        assert "Matèries de l'educació secundària obligatòria a quart curs" in titulos

    def test_las_materias_de_un_articulo_llegan_una_por_linea(self):
        """El EADOP separa los items de una enumeración con `<br />` dentro de
        un solo `<p>`. Cortando solo por `</p>`, las trece materias llegarían
        pegadas en una línea y `RX_ITEM_LETRA` no reconocería ninguna: el
        artículo entero se perdería sin dar ningún error."""
        parrafos = [x for _, x in self._parrafos()]
        i = parrafos.index(
            [p for p in parrafos if p.startswith("1. Les matèries") and "primer a tercer" in p][0]
        )
        siguientes = parrafos[i + 1:i + 13]

        assert siguientes[0] == "Aranès i Literatura a l'Aran" or siguientes[0].startswith("a)")
        assert any("Biologia i Geologia" in s for s in siguientes)
        assert any("Matemàtiques" in s for s in siguientes)

    def test_el_texto_llega_desescapado(self):
        """Va escapado como HTML dentro del atributo. Sin deshacerlo, el
        currículo catalán se guardaría lleno de `&egrave;` y `&#39;`."""
        todo = " ".join(x for _, x in self._parrafos())

        assert "&egrave;" not in todo and "&#39;" not in todo
        assert "matèries" in todo.lower()

    def test_el_curriculo_NO_esta_en_este_fichero(self):
        """La comprobación más importante, y la que da la mala noticia.

        Los anexos son enlaces a PDF: el Anexo 3 —las materias de la ESO— es
        `ANNEX3Matriessecundriaobligatriadefcat.pdf`. Si algún día el EADOP
        empezara a incluirlos, este test se pondría rojo, que es justo lo que
        queremos que pase: sería la señal de que se puede dejar de depender de
        un PDF descargado a mano.
        """
        todo = " ".join(x for _, x in self._parrafos())

        assert "Competències específiques" not in todo, (
            "¡el currículo está en el XML! Revisar: ya no haría falta el PDF"
        )
        assert "Vegeu la imatge al final del document" in todo, (
            "el marcador de anexo-en-PDF ha cambiado; comprobar qué trae ahora"
        )
