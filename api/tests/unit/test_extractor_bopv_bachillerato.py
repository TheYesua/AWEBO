"""El mismo lector del BOPV, leyendo el decreto de Bachillerato.

POR QUÉ UN FICHERO APARTE Y NO EL MISMO
----------------------------------------
El código es uno —`extractor_bopv` con `EtapaBOPV`— pero los fallos no. Los de
la ESO están fijados en `test_extractor_bopv.py` con su historia; estos son los
que aparecieron al abrir el Decreto 76/2023, y mezclarlos haría más difícil
saber qué caso protege cada test.

LO QUE COSTÓ, Y NINGUNO DIO ERROR
----------------------------------
1. **El anexo es el II y no el III.** No es un detalle de numeración: en el
   decreto de Educación Básica el Anexo II es el currículo de **primaria**, así
   que equivocarse no da error, da la etapa equivocada.
2. **El encabezado del anexo lleva el decreto delante** —«MAIATZAREN 30EKO
   76/2023 DEKRETUAREN II. ERANSKINA»— y la expresión solo aceptaba el numeral
   suelto. Ese sí falló ruidosamente, que es lo bueno de lanzar en vez de
   devolver una lista vacía.
3. **Una sexta forma de marcar los bloques**: en «Kultura Zientifikoa» van en
   MAYÚSCULAS y sin letra ni número. El primer intento de distinguirlos —dentro
   de los saberes, mayúsculas es bloque— dejó el extractor **con dos materias
   de 65**, porque el título de la siguiente llega precisamente cuando el
   estado son los saberes de la anterior.
4. **Un título partido en dos líneas**, como los ámbitos de Galicia.
5. **Seis optativas no marcan sus bloques de ninguna forma reconocible**, y
   descartar esas líneas las dejaba con cero saberes.
6. **El código del criterio con guion**: `1.1-` en Psikologia. Exigir el punto
   o el espacio la dejaba con cero criterios.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.curriculo.bopv_etapas import BACHILLERATO, CURSOS_BACHILLERATO, ESO
from app.curriculo.extractor_bopv import (
    RX_CRITERIO,
    RX_ERANSKINA,
    _es_titulo_de_materia,
    ciclo_de_cabecera,
    extraer,
    titulos_de_materia,
)


_RAIZ = Path(__file__).resolve().parents[3]
_FUENTES = (Path("/curriculo") if Path("/curriculo").is_dir()
            else _RAIZ / "curriculo") / "fuentes" / "pais-vasco-bachillerato"
_DECRETO = _FUENTES / "20230724_batxilergoa_curriculum_dekretua_e_ZUZENDUTA.pdf"


class TestPiezasSueltas:

    def test_el_encabezado_admite_el_decreto_delante(self):
        """«MAIATZAREN 30EKO 76/2023 DEKRETUAREN II. ERANSKINA»: sin esto, el
        extractor de Bachillerato no encontraba su propio anexo."""
        m = RX_ERANSKINA.match("MAIATZAREN 30EKO 76/2023 DEKRETUAREN II. ERANSKINA")
        assert m and m.group(1) == "II"

    def test_y_sigue_valiendo_el_numeral_suelto(self):
        """El de la ESO va sin prefijo, y no puede dejar de reconocerse."""
        assert RX_ERANSKINA.match("III ERANSKINA").group(1) == "III"

    @pytest.mark.parametrize("linea, codigo", [
        ("1.1. Planteatutako problemak", "1.1"),   # Teknologia, ESO
        ("1.1 Osasunaren kontzeptu", "1.1"),       # Heziketa Fisikoa, ESO
        ("1.1- Psikologiaren oinarrizko", "1.1"),  # Psikologia, Bachillerato
    ])
    def test_el_codigo_del_criterio_admite_las_tres_puntuaciones(self, linea, codigo):
        m = RX_CRITERIO.match(linea)
        assert m and f"{m.group(1)}.{m.group(2)}" == codigo

    def test_los_cursos_llevan_el_nombre_de_la_etapa(self):
        """Con el sufijo de la ESO, Bachillerato habría cargado «1º ESO» y sus
        materias no aparecerían en ningún desplegable de Bachillerato."""
        assert ciclo_de_cabecera("Bigarren maila", BACHILLERATO)[0] == \
            ["2º Bachillerato"]
        assert ciclo_de_cabecera("Bigarren maila", ESO)[0] == ["2º ESO"]

    def test_la_cabecera_del_anexo_no_es_una_materia(self):
        """«BATXILERGOKO JAKINTZAGAIAK» va en mayúsculas y en su propia línea,
        igual que un título. Sin excluirla se pegaba al de la primera materia:
        «BATXILERGOKO JAKINTZAGAIAK ATZERRIKO LEHEN HIZKUNTZA»."""
        assert not _es_titulo_de_materia("BATXILERGOKO JAKINTZAGAIAK")
        assert not _es_titulo_de_materia("DERRIGORREZKO BIGARREN HEZKUNTZAKO JAKINTZAGAIAK")
        assert _es_titulo_de_materia("PSIKOLOGIA")


class TestQueEsUnaMateriaYQueUnBloque:
    """La pasada previa, que es lo que los distingue."""

    def _elementos(self, *lineas):
        from app.curriculo.extractor_bopv import _Linea
        return [_Linea(t, 50.0) for t in lineas]

    def test_una_materia_lleva_competencias_detras(self):
        titulos, _ = titulos_de_materia(self._elementos(
            "PSIKOLOGIA", "Introducción larga de la materia.",
            "KONPETENTZIA ESPEZIFIKOAK", "1. Lo que sea.",
        ))
        assert titulos == {"PSIKOLOGIA"}

    def test_un_bloque_de_saberes_no(self):
        """«ZAHARTZEA» es una palabra suelta igual que «BOLUMENA», que sí es
        una materia. Lo único que los separa es que a una le siguen sus
        competencias."""
        titulos, _ = titulos_de_materia(self._elementos(
            "KULTURA ZIENTIFIKOA", "Introducción.",
            "KONPETENTZIA ESPEZIFIKOAK", "1. Lo que sea.",
            "OINARRIZKO JAKINTZAK", "ZAHARTZEA", "Zelulen birprogramazioa.",
        ))
        assert titulos == {"KULTURA ZIENTIFIKOA"}

    def test_un_titulo_en_dos_lineas_se_junta(self):
        titulos, partidos = titulos_de_materia(self._elementos(
            "EGUNGO MUNDUAREN GATAZKAK ETA ERREALITATEAK, ETA KOMUNIKABIDEEKIN ETA",
            "SARE SOZIALEKIN DUTEN ERLAZIOA",
            "KONPETENTZIA ESPEZIFIKOAK", "1. Lo que sea.",
        ))
        completo = ("EGUNGO MUNDUAREN GATAZKAK ETA ERREALITATEAK, ETA "
                    "KOMUNIKABIDEEKIN ETA SARE SOZIALEKIN DUTEN ERLAZIOA")
        assert titulos == {completo}
        assert partidos["SARE SOZIALEKIN DUTEN ERLAZIOA"] == completo

    def test_pero_solo_si_van_seguidas(self):
        """Los seis bloques de «Kultura Zientifikoa» tienen saberes entre
        ellos, y sin esta condición salía un título de siete líneas:
        «ZER JATEN DUGU? ZAHARTZEA … LABORATEGIKO TEKNIKAK»."""
        titulos, _ = titulos_de_materia(self._elementos(
            "OINARRIZKO JAKINTZAK",
            "ZER JATEN DUGU?", "Elikagai funtzionalak: Omega 3.",
            "ZAHARTZEA", "Zelulen birprogramazioa.",
            "LABORATEGIKO TEKNIKAK", "Introducción de la materia.",
            "KONPETENTZIA ESPEZIFIKOAK", "1. Lo que sea.",
        ))
        assert titulos == {"LABORATEGIKO TEKNIKAK"}


class TestLaTablaDeCursos:

    def test_las_materias_con_I_y_II_van_a_los_dos_cursos(self):
        """El articulado distingue «Matematika I» de «Matematika II», pero el
        Anexo II las junta bajo un solo título."""
        assert CURSOS_BACHILLERATO["MATEMATIKA"] == \
            ["1º Bachillerato", "2º Bachillerato"]

    def test_las_de_un_solo_curso_lo_dicen(self):
        assert CURSOS_BACHILLERATO["BIOLOGIA"] == ["2º Bachillerato"]
        assert CURSOS_BACHILLERATO["FISIKA ETA KIMIKA"] == ["1º Bachillerato"]

    def test_la_optativa_que_el_decreto_sí_ata(self):
        """Artículo 17.2: Jarduera Fisikoa solo en segundo."""
        assert CURSOS_BACHILLERATO["JARDUERA FISIKOA, AISIA ETA OSASUNA"] == \
            ["2º Bachillerato"]

    def test_las_demás_optativas_van_a_los_dos(self):
        """No es una suposición de conveniencia: el artículo 17.1 deja que el
        centro ofrezca cualquiera de las del Anexo II sin restringir curso, y
        el Anexo V las agrupa sin nombrarlas."""
        assert BACHILLERATO.cursos_por_defecto == \
            ["1º Bachillerato", "2º Bachillerato"]
        assert "PSIKOLOGIA" not in CURSOS_BACHILLERATO


@pytest.mark.skipif(not _DECRETO.is_file(), reason="el PDF no está descargado")
class TestElAnexoCompleto:

    @pytest.fixture(scope="class")
    def todo(self):
        return extraer(_DECRETO, BACHILLERATO)

    def test_salen_las_sesenta_y_cinco_materias(self, todo):
        """65 títulos en el Anexo II y 65 con PDF en el portal —58 descargados
        más 7 con el enlace roto—. Es el contraste que da confianza, y el que
        destapó los bloques de «Kultura Zientifikoa» y el título partido."""
        assert len({mc.materia_oficial for mc in todo}) == 65

    def test_ninguna_sale_a_medias(self, todo):
        """Seis optativas salían con cero saberes y una con cero criterios."""
        cojas = [f"{mc.materia_efectiva} ({mc.ciclo})" for mc in todo
                 if not mc.competencias or not mc.criterios or not mc.saberes]
        assert not cojas, f"salen a medias: {cojas}"

    def test_todas_son_de_bachillerato(self, todo):
        """Sin la etapa, sus filas pisarían las de la ESO en la carga."""
        assert {mc.etapa for mc in todo} == {"Bachillerato"}
        cursos = {c for mc in todo for c in mc.cursos_aplicables}
        assert cursos == {"1º Bachillerato", "2º Bachillerato"}

    def test_el_titulo_partido_llega_entero(self, todo):
        """Si se queda con la última línea, la materia se llama «SARE
        SOZIALEKIN DUTEN ERLAZIOA» — el fallo que en Galicia cargó los ámbitos
        como «obrigatoria»."""
        titulos = {mc.materia_oficial for mc in todo}
        assert any(t.startswith("EGUNGO MUNDUAREN GATAZKAK") and
                   t.endswith("ERLAZIOA") for t in titulos)
        assert "SARE SOZIALEKIN DUTEN ERLAZIOA" not in titulos

    def test_kultura_zientifikoa_es_una_materia_y_no_siete(self, todo):
        """Sus seis bloques van en mayúsculas y sin marca."""
        kz = [mc for mc in todo if mc.materia_oficial == "KULTURA ZIENTIFIKOA"]
        assert kz, "no está"
        assert len(kz[0].saberes) >= 6
        for falso in ("ZAHARTZEA", "INGENIARITZA GENETIKOA", "ZER JATEN DUGU?"):
            assert falso not in {mc.materia_oficial for mc in todo}

    def test_cada_criterio_apunta_a_una_competencia_que_existe(self, todo):
        malos = []
        for mc in todo:
            codigos = {c.codigo for c in mc.competencias}
            malos += [f"{mc.materia_efectiva}:{cr.codigo}" for cr in mc.criterios
                      if cr.competencia not in codigos]
        assert not malos, f"criterios huérfanos: {malos[:10]}"

    def test_los_codigos_copiados_del_boletin_se_corrigen(self, todo):
        """El decreto arrastra bloques de criterios sin cambiar el primer dígito.

        Bajo «3. Konpetentzia espezifikoa» de Filosofiaren Historia van
        numerados `2.1` y `2.2`, y detrás un `3.3` que delata la copia. Igual
        en Euskal Herriko Historia bajo las cabeceras 2 y 8.

        No daba error de ninguna clase: el segundo `2.1` pisaba al primero al
        cargar y se perdía un criterio entero con su texto. El único síntoma
        fue que el seed dijo `cr_nuevos=1138` con 1144 en los JSON.
        """
        for materia, esperados in [
            ("FILOSOFIAREN HISTORIA", {"3.1", "3.2", "3.3"}),
            ("EUSKAL HERRIKO HISTORIA", {"2.1", "2.2", "8.1", "8.2"}),
        ]:
            mc = next(m for m in todo if m.materia_oficial == materia)
            codigos = [cr.codigo for cr in mc.criterios]
            assert len(codigos) == len(set(codigos)), (
                f"{materia}: códigos repetidos {sorted(codigos)}"
            )
            assert esperados <= set(codigos), (
                f"{materia}: faltan {esperados - set(codigos)}"
            )

    def test_el_duplicado_sin_evidencia_se_deja_como_esta(self, todo):
        """Euskara tiene dos `8.3` distintos bajo la cabecera 8.

        Aquí el código bueno del segundo sería `8.4`, y **el decreto no lo dice
        en ninguna parte**: deducirlo sería inventarse un código que un docente
        podría acabar citando en una programación oficial. Se deja repetido,
        que es lo que publica el boletín, y es el cargador el que se ocupa de
        no perder el segundo. Anotado como cabo abierto en la hoja de ruta.
        """
        mc = next(m for m in todo
                  if m.materia_oficial.startswith("EUSKARA ETA LITERATURA"))
        repetidos = [c for c in {cr.codigo for cr in mc.criterios}
                     if [x.codigo for x in mc.criterios].count(c) > 1]
        assert repetidos == ["8.3"], f"repetidos: {repetidos}"
        textos = {cr.descripcion for cr in mc.criterios if cr.codigo == "8.3"}
        assert len(textos) == 2, "son dos criterios distintos, no uno repetido"

    def test_ningun_saber_empieza_cortado_a_media_frase(self, todo):
        """Un saber que arranca en minúscula es una línea del PDF, no un saber.

        ESTE TEST NACIÓ MAL Y SE REESCRIBIÓ
        ------------------------------------
        Buscaba «el título del subapartado pegado al saber», reconocido por
        `N. MAYÚSCULAS` al principio. Encontró siete casos en
        Gizarte-antropologia y **los siete eran correctos**: esa materia
        redacta sus bloques como «1. ANTROPOLOGIARI SARRERA…: contenido», con
        el epígrafe y el texto en la misma línea, y el epígrafe forma parte
        del saber tal como lo publica el decreto.

        El fallo de verdad estaba al lado y el test no lo veía: los saberes
        rescatados salían **partidos por ancho de caja**, uno por línea del
        PDF, cortados a media palabra —«logiaren praktikak, datu bilketa…»—.
        La señal objetiva de eso es empezar en minúscula, que es lo que se
        mira ahora. Buscar la forma que yo esperaba en vez del defecto que
        importaba costó dos vueltas.

        No se exige cero: el boletín tiene saberes que de verdad empiezan en
        minúscula —«nazioarteko erakundeak…» detrás de dos puntos—, y el
        umbral separa esos pocos de una regresión del agrupador.
        """
        cortados = [f"{mc.materia_efectiva}: {i[:60]}" for mc in todo
                    for b in mc.saberes for i in b.items if i[:1].islower()]
        assert len(cortados) <= 35, (
            f"{len(cortados)} saberes empiezan cortados: {cortados[:5]}"
        )

    def test_gizarte_antropologia_tiene_sus_siete_epigrafes(self, todo):
        """El caso concreto que destapó lo anterior: siete bloques del decreto
        que salían como veintidós fragmentos."""
        ga = [mc for mc in todo if mc.materia_oficial == "GIZARTE-ANTROPOLOGIA"]
        assert ga, "no está"
        items = [i for b in ga[0].saberes for i in b.items]
        epigrafes = [i for i in items
                     if re.match(r"^\d{1,2}\.\s+[A-ZÁÉÍÓÚÜÑ]{4,}", i)]
        assert len(epigrafes) == 7, f"{len(epigrafes)} epígrafes de 7"
        # Ocho y no siete: el bloque 3 cierra con una frase aparte
        # —«Enkulturazioa nigan eta nire ingurukoengan.»— que el decreto pone
        # en su propia línea. Es texto completo, no un fragmento, así que se
        # deja como saber suyo. Lo que no puede volver son los veintidós.
        assert len(items) <= 9, f"{len(items)} saberes: vuelven los fragmentos"
        assert not [i for i in items if i[:1].islower()], "hay cortes"

    def test_no_queda_cabecera_del_boletin_dentro_del_texto(self, todo):
        sucios = [mc.materia_efectiva for mc in todo
                  if any("AGINTARITZAREN" in cr.descripcion for cr in mc.criterios)
                  or any("AGINTARITZAREN" in i for b in mc.saberes for i in b.items)]
        assert not sucios, f"con cabecera dentro: {sucios}"

    def test_la_tabla_de_cursos_no_tiene_sobrantes(self, todo):
        """Una entrada que ya no casa con ningún título significa que esa
        materia se está cargando con el reparto de las optativas."""
        usados = {mc.materia_oficial for mc in todo}
        sobran = set(CURSOS_BACHILLERATO) - usados
        assert not sobran, f"entradas que no casan con ningún título: {sobran}"
