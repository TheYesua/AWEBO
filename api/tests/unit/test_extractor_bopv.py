"""Tests del extractor del BOPV (currículo vasco, Decreto 77/2023).

No tocan base de datos ni Flask. Los que necesitan el PDF real se saltan si no
está: no se versiona, como el resto de las fuentes.

DÓNDE ESTUVO EL RIESGO EN ESTE EXTRACTOR
-----------------------------------------
En lo de siempre: **ningún fallo lanzó una excepción**. Todos produjeron JSON
válidos con datos plausibles y mal. Los que se cometieron escribiéndolo:

1. La primera versión leyó el anexo como **texto corrido**, y los criterios y
   los saberes van en tablas de dos columnas —una por ciclo— en 69 de las 226
   páginas. Resultado: las dos columnas intercaladas, Matemáticas con 249
   saberes y seis materias con cero criterios.
2. Al pasar a leer tablas, una cabecera de una sola columna
   —`['Lehen eta bigarren mailak', '']`— se tomó por dos columnas paralelas, y
   **cada saber se duplicó en dos tramos**. Matemáticas salía con 251 en cada
   uno y los dos JSON eran válidos.
3. `III ERANSKINA` **va sin punto** tras la cifra y `II.` y `IV.` lo llevan, así
   que la expresión regular encontraba todos los anexos menos el único que
   importa.
4. El código del criterio lleva punto final unas veces y otras no. Exigirlo
   dejaba seis materias con **cero criterios**, sin ningún aviso.
5. Los bloques de saberes se marcan de **cinco formas distintas**, y cada una
   se descubrió por una materia que salía con cero saberes.
6. La cabecera de ciclo de Musika es un rango —«Lehen mailatik hirugarrenera»—.
   Sin reconocerlo, su columna de 1.º a 3.º se acumulaba en la de 4.º y la
   materia entera salía como de cuarto.
7. Matemáticas de 4.º tiene **itinerarios A y B**, y el separador entre «maila»
   y la letra es unas veces espacio y otras punto. Con solo el espacio, los
   criterios se partían bien y los 114 saberes caían en un tramo sin
   itinerario, dejando A y B con cero.

Por eso aquí se comprueban cantidades, reparto y unicidad, y no que las
funciones devuelvan algo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.curriculo.extractor_bopv import (
    CURSOS_DEL_ARTICULADO,
    RX_BLOQUE,
    RX_BLOQUE_MULTZOA,
    RX_CRITERIO,
    RX_ERANSKINA,
    SIN_CICLO,
    _Tabla,
    _bonito,
    _es_ruido,
    _es_titulo_de_materia,
    _parsear,
    _unir,
    ciclo_de_cabecera,
    cursos_de_ciclo,
    extraer,
)


#: `curriculo/` está montado en `/curriculo` dentro del contenedor y no
#: colgando de la raíz, que es `/repo` y solo tiene cuatro ficheros sueltos.
#: Escribir `RAIZ / "curriculo"` ha roto tests solo dentro de Docker cuatro
#: veces, así que aquí se resuelven las dos posibilidades.
_RAIZ = Path(__file__).resolve().parents[3]
_FUENTES = (Path("/curriculo") if Path("/curriculo").is_dir()
            else _RAIZ / "curriculo") / "fuentes" / "pais-vasco"
_DECRETO = _FUENTES / "20230731_oinarrizkoa_curriculum_dekretua_e_ZUZENDUTA.pdf"


class TestPiezasSueltas:
    """Lo que se puede comprobar sin abrir el PDF."""

    def test_el_anexo_tercero_se_reconoce_sin_punto(self):
        """El fallo que dejaba el extractor sin encontrar su propio anexo."""
        assert RX_ERANSKINA.match("III ERANSKINA").group(1) == "III"
        assert RX_ERANSKINA.match("II. ERANSKINA").group(1) == "II"
        assert RX_ERANSKINA.match("IV. ERANSKINA").group(1) == "IV"

    @pytest.mark.parametrize("linea, codigo", [
        ("1.1. Planteatutako problemak edo beharrak definitzea", "1.1"),
        ("1.1 Osasunaren kontzeptu integralera zuzendutako", "1.1"),
        ("10.2 Zerbait", "10.2"),
    ])
    def test_el_codigo_del_criterio_admite_o_no_el_punto(self, linea, codigo):
        """Seis materias salieron con cero criterios por exigir el punto."""
        m = RX_CRITERIO.match(linea)
        assert m and f"{m.group(1)}.{m.group(2)}" == codigo

    @pytest.mark.parametrize("linea, codigo", [
        ("A. Problemak ebazteko prozesua", "A"),
        ("A. HIZKUNTZAK ETA BEREN HIZTUNAK.", "A"),
    ])
    def test_bloque_con_letra(self, linea, codigo):
        assert RX_BLOQUE.match(linea).group(1) == codigo

    @pytest.mark.parametrize("linea, codigo", [
        ("D multzoa. Aurkaritza-egoerak", "D"),
        ("A multzoak. Jokoak eta kirolak.", "A"),
        ("1. multzoa.Zientzia eta informazio zientifikoa", "1"),
    ])
    def test_bloque_con_multzoa_en_sus_tres_variantes(self, linea, codigo):
        """Singular, plural, número y sin espacio tras el punto. Cada una se
        descubrió por una materia que salía con cero saberes."""
        assert RX_BLOQUE_MULTZOA.match(linea).group(1).upper() == codigo

    @pytest.mark.parametrize("cabecera, cursos, itin", [
        ("Lehen eta bigarren mailak", ["1º ESO", "2º ESO"], ""),
        ("Hirugarren eta laugarren mailak", ["3º ESO", "4º ESO"], ""),
        ("Laugarren maila", ["4º ESO"], ""),
        ("Bigarren maila", ["2º ESO"], ""),
        # El rango, que solo usa Musika.
        ("Lehen mailatik hirugarrenera", ["1º ESO", "2º ESO", "3º ESO"], ""),
        # El itinerario, con las dos puntuaciones que usa el decreto.
        ("Laugarren maila A matematika", ["4º ESO"], "A"),
        ("Laugarren maila. B matematika", ["4º ESO"], "B"),
        ("Oinarrizko jakintzak. Laugarren maila. A matematika", ["4º ESO"], "A"),
    ])
    def test_la_cabecera_de_ciclo_da_cursos_e_itinerario(self, cabecera, cursos, itin):
        assert ciclo_de_cabecera(cabecera) == (cursos, itin)

    @pytest.mark.parametrize("t", [
        "MATEMATIKA",
        "Konpetentzia espezifiko hau lotzen da",
        "Ikasleek gaitasunak garatuko dituzte mailakatuta",
    ])
    def test_lo_que_no_es_cabecera_de_ciclo_no_lo_parece(self, t):
        """`cursos_de_ciclo` decide también si una línea es un título de
        materia, así que un falso positivo aquí borra una materia entera."""
        assert cursos_de_ciclo(t) is None

    def test_se_deshacen_los_guiones_de_division(self):
        """El PDF parte con guion normal, no con el blando: juntar por espacios
        dejaba «esperi- mentatuz» dentro del texto del docente."""
        assert _unir(["simulazio-tresnekin esperi-", "mentatuz, problema"]) == \
            "simulazio-tresnekin esperimentatuz, problema"

    def test_el_guion_suspendido_del_euskera_se_respeta(self):
        """«kultura- eta musika-ondarea» es correcto y no es una partición.

        Se comprueba porque la primera medida de «restos de partición» contó
        estos 201 casos como fallos y estuvo a punto de mandar a arreglar algo
        que funcionaba. Una cifra de contraste mal construida da falsa alarma
        en un sentido y falsa confianza en el otro."""
        assert _unir(["Euskal kultura- eta", "musika-ondarea"]) == \
            "Euskal kultura- eta musika-ondarea"

    @pytest.mark.parametrize("t", [
        "144. zk.",
        "EUSKAL HERRIKO AGINTARITZAREN ALDIZKARIA",
        "2023ko uztailaren 31, astelehena",
        "2023/3691 (330/206)",
    ])
    def test_la_cabecera_del_boletin_es_ruido(self, t):
        assert _es_ruido(t)

    def test_un_bloque_en_mayusculas_no_es_una_materia(self):
        """En Lengua los bloques van EN MAYÚSCULAS. Sin esto se colaban como
        materias: se inventaron cuatro y Lengua se quedó sin ningún saber."""
        assert not _es_titulo_de_materia("A. HIZKUNTZAK ETA BEREN HIZTUNAK.")
        assert _es_titulo_de_materia("GEOGRAFIA ETA HISTORIA")

    def test_los_descriptores_no_son_una_materia(self):
        """«STEM4, KD1, KPSII5.» también es una línea en mayúsculas."""
        assert not _es_titulo_de_materia("STEM4, KD1, KPSII5, KAKK2.")

    def test_las_siglas_no_se_capitalizan_como_palabras(self):
        assert _bonito("KULTURA ZIENTIFIKOA, DBHKO 3. MAILA") == \
            "Kultura Zientifikoa, DBHko 3. Maila"
        assert _bonito("GEOGRAFIA ETA HISTORIA") == "Geografia eta Historia"


class TestLaCabeceraDeUnaSolaColumna:
    """El fallo que duplicaba cada saber en dos tramos.

    `['Lehen eta bigarren mailak', '']` **no** parte la tabla en dos ciclos:
    dice que toda ella es de primero y segundo. Tomarlo por columnas paralelas
    hacía que cada fila con la segunda celda vacía se mandara a los dos tramos.
    """

    def _materia(self, tabla):
        from app.curriculo.extractor_bopv import _Linea
        elementos = [
            _Linea("MATEMATIKA", 50.0),
            _Linea("OINARRIZKO JAKINTZAK", 214.0),
            tabla,
        ]
        return _parsear(elementos)[0]

    def test_una_sola_columna_con_ciclo_no_duplica(self):
        m = self._materia(_Tabla([
            [["Lehen eta bigarren mailak"], [""]],
            [["A. Zentzu numerikoa"], [""]],
            [["1. Zenbaketa"], ["Problema matematikoak."]],
        ]))
        assert len(m.tramos) == 1
        (clave,) = m.tramos
        assert clave == (("1º ESO", "2º ESO"), "")

    def test_dos_columnas_con_ciclo_si_se_separan(self):
        m = self._materia(_Tabla([
            [["Lehen eta bigarren mailak"], ["Hirugarren maila"]],
            [["A. Zentzu numerikoa"], ["A. Zentzu numerikoa"]],
            [["Lehen saber."], ["Hirugarren saber."]],
        ]))
        assert set(m.tramos) == {(("1º ESO", "2º ESO"), ""), (("3º ESO",), "")}


@pytest.mark.skipif(not _DECRETO.is_file(), reason="el PDF no está descargado")
class TestElAnexoCompleto:
    """Contra el PDF real. Se comprueban cantidades y reparto."""

    @pytest.fixture(scope="class")
    def todo(self):
        return extraer(_DECRETO)

    def test_salen_las_treinta_materias(self, todo):
        """Treinta títulos en el Anexo III y treinta PDF por materia en
        Berrigasteiz. Es el contraste que vale porque las dos cifras se cuentan
        sobre cosas comparables: una materia, un fichero."""
        assert len({mc.materia_oficial for mc in todo}) == 30

    def test_ninguna_sale_a_medias(self, todo):
        """Una materia sin criterios o sin saberes es un fallo de lectura, no
        un currículo raro: las treinta tienen las tres secciones."""
        cojas = [f"{mc.materia_efectiva} ({mc.ciclo})" for mc in todo
                 if not mc.competencias or not mc.criterios or not mc.saberes]
        assert not cojas, f"salen a medias: {cojas}"

    def test_todas_tienen_cursos(self, todo):
        """Una fila sin cursos no casa con ninguno, así que se cargaría en la
        base de datos y no aparecería en ningún desplegable."""
        sin = [mc.materia_efectiva for mc in todo if not mc.cursos_aplicables]
        assert not sin, f"sin cursos: {sin}"

    def test_cada_criterio_apunta_a_una_competencia_que_existe(self, todo):
        """Si el número del código no casa con ninguna competencia, la
        exportación pinta «(no encontrado en el currículo)» al docente."""
        malos = []
        for mc in todo:
            codigos = {c.codigo for c in mc.competencias}
            malos += [f"{mc.materia_efectiva}:{cr.codigo}" for cr in mc.criterios
                      if cr.competencia not in codigos]
        assert not malos, f"criterios huérfanos: {malos[:10]}"

    def test_matematicas_separa_sus_itinerarios(self, todo):
        """A y B tienen currículos distintos. Cuando no se distinguían, las dos
        columnas caían en el mismo tramo y quedaba una materia con el doble de
        criterios y ningún aviso."""
        mates = {mc.materia_efectiva: mc for mc in todo
                 if mc.materia_oficial == "MATEMATIKA"}
        assert {"Matematika A", "Matematika B"} <= set(mates)
        a, b = mates["Matematika A"], mates["Matematika B"]
        assert a.criterios and b.criterios and a.saberes and b.saberes
        # Currículos distintos: si fueran el mismo texto es que se han
        # copiado en vez de leerse por columna.
        assert [c.descripcion for c in a.criterios] != \
            [c.descripcion for c in b.criterios]

    def test_musika_no_se_carga_entera_en_cuarto(self, todo):
        """Su cabecera es un rango, «Lehen mailatik hirugarrenera»."""
        cursos = {c for mc in todo if mc.materia_oficial == "MUSIKA"
                  for c in mc.cursos_aplicables}
        assert cursos == {"1º ESO", "2º ESO", "3º ESO", "4º ESO"}

    def test_los_tramos_de_una_materia_no_se_repiten(self, todo):
        """El nombre del JSON sale de (materia, cursos): dos entradas con la
        misma clave se pisan, que es lo que pasó en Galicia."""
        vistos = [(mc.materia_efectiva, tuple(mc.cursos_aplicables))
                  for mc in todo]
        assert len(vistos) == len(set(vistos))

    def test_ningun_tramo_acapara_los_criterios_de_otro(self, todo):
        """Con las columnas mezcladas, un tramo se llevaba los dos juegos."""
        for mc in todo:
            codigos = [cr.codigo for cr in mc.criterios]
            assert len(codigos) == len(set(codigos)), \
                f"{mc.materia_efectiva} ({mc.ciclo}) repite códigos"

    def test_el_texto_llega_entero(self, todo):
        """Un criterio de una línea suele ser una lectura truncada."""
        cortos = [f"{mc.materia_efectiva}:{cr.codigo}" for mc in todo
                  for cr in mc.criterios if len(cr.descripcion) < 40]
        assert len(cortos) < 5, f"criterios sospechosamente cortos: {cortos[:10]}"

    def test_no_queda_cabecera_del_boletin_dentro_del_texto(self, todo):
        """Se repite en cada página y es lo primero que se cuela."""
        sucios = [mc.materia_efectiva for mc in todo
                  if any("AGINTARITZAREN" in cr.descripcion for cr in mc.criterios)
                  or any("AGINTARITZAREN" in i for b in mc.saberes for i in b.items)]
        assert not sucios, f"con cabecera dentro: {sucios}"

    def test_ningun_saber_arrastra_el_titulo_de_su_subapartado(self, todo):
        """El fallo que se vio en el documento del docente, no en un test.

        Las tablas de saberes van a dos niveles: la primera columna es un
        subapartado numerado —«1. Zenbaketa»— y la segunda los saberes que
        cuelgan de él. Al leerlas de corrido, el título se pegaba al primer
        saber y en la SdA 60 se leía «3. Eragiketen zentzua Eragiketa
        aritmetikoen propietateak…». Eran 157 saberes en 12 materias, y ni el
        recuento ni la validez del JSON lo delataban."""
        pegados = [f"{mc.materia_efectiva}: {i[:60]}" for mc in todo
                   for b in mc.saberes for i in b.items
                   if re.match(r"^\d{1,2}\.\s+[A-ZÁÉÍÓÚÜÑ]", i)]
        assert not pegados, f"subapartado pegado al saber: {pegados[:5]}"

    def test_el_subapartado_es_un_bloque_con_codigo_del_decreto(self, todo):
        """Se conserva como bloque hijo en vez de descartarlo: el código sale
        entero de la norma —letra del bloque y número del subapartado— así que
        sigue siendo citable."""
        mates = next(mc for mc in todo if mc.materia_efectiva == "Matematika"
                     and "1º ESO" in mc.cursos_aplicables)
        codigos = {b.codigo for b in mates.saberes}
        assert "A.1" in codigos, f"sin subapartados: {sorted(codigos)[:8]}"
        hijo = next(b for b in mates.saberes if b.codigo == "A.1")
        assert " · " in hijo.titulo, hijo.titulo

    def test_no_se_cargan_bloques_sin_saberes(self, todo):
        """Un bloque cuyos saberes cuelgan todos de subapartados se queda sin
        items propios. Eran 43, y aparecerían en el catálogo con título y sin
        nada que citar."""
        vacios = [f"{mc.materia_efectiva}:{b.codigo}" for mc in todo
                  for b in mc.saberes if not b.items]
        assert not vacios, f"bloques vacíos: {vacios[:10]}"

    def test_la_tabla_de_cursos_no_tiene_sobrantes(self, todo):
        """Si una entrada de `CURSOS_DEL_ARTICULADO` deja de usarse es que el
        título cambió, y entonces esa materia se está cargando sin cursos."""
        usados = {mc.materia_oficial for mc in todo}
        sobran = set(CURSOS_DEL_ARTICULADO) - usados
        assert not sobran, f"entradas que ya no casan con ningún título: {sobran}"
