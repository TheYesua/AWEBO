"""El documento dice de qué norma sale el currículo, y en qué lengua.

EL CABO QUE ESTO CIERRA
------------------------
«Documentos bilingües en las exportaciones», abierto el 14/08. Estaba asignado
«dentro de la tarea 9c» con este razonamiento: *con el currículo de cada
comunidad en su propia lengua, una SdA en catalán cita criterios en catalán, y
deja de haber mezcla*.

**El razonamiento era falso**, y se vio al cerrar 9c: la lengua de redacción la
elige el docente y la del currículo la fija el boletín, así que pueden no
coincidir. La SdA 60 se redactó en castellano y salió con sus criterios en
euskera —correctos— sin una línea que explicara por qué.

Lo que faltaba no era evitar la mezcla, que no se puede: era **decirla**.

POR QUÉ SE COMPRUEBAN LAS DOS RUTAS
------------------------------------
Porque hay dos, PDF y DOCX, y ya se cometió una vez el error de tocar solo una:
el aviso de sección incompleta se añadió al DOCX y el PDF salió sin él durante
un día. El texto se compone en un único sitio y aquí se comprueba que los dos
lo usan.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.curriculo import comunidades
from app.services.exportacion_service import (
    procedencia_del_curriculo,
    texto_de_procedencia,
)


def _fila(comunidad="pais-vasco", idioma="eu", etapa="ESO"):
    return SimpleNamespace(comunidad=comunidad, idioma=idioma, etapa=etapa,
                           codigo="1.1", descripcion="Testua")


def _sa(idioma="es", filas=None):
    filas = [_fila()] if filas is None else filas
    return SimpleNamespace(idioma=idioma, competencias=filas,
                           criterios=[], saberes=[])


class TestDeDondeSaleElDato:

    def test_sale_de_las_filas_enlazadas_y_no_de_la_situacion(self):
        """La comunidad de la SdA dice contra qué se generó; lo que el
        documento reproduce es el texto de las filas, y es de eso de lo que hay
        que responder."""
        sa = _sa(filas=[_fila(comunidad="galicia", idioma="gl")])
        sa.comunidad_autonoma = "Cataluña"   # no debe influir

        p = procedencia_del_curriculo(sa)
        assert p["comunidad"] == "Galicia"
        assert p["norma"] == "Decreto 156/2022"

    def test_sin_curriculo_enlazado_no_hay_nada_que_decir(self):
        """Una SdA en borrador no cita nada: inventar una procedencia sería
        peor que callar."""
        assert procedencia_del_curriculo(_sa(filas=[])) is None

    @pytest.mark.parametrize("comunidad, etapa, esperada", [
        ("cataluna", "ESO", "Decret 175/2022"),
        ("cataluna", "Bachillerato", "Decret 171/2022"),
        ("pais-vasco", "ESO", "Decreto 77/2023"),
        ("pais-vasco", "Bachillerato", "Decreto 76/2023"),
    ])
    def test_cada_etapa_cita_su_decreto(self, comunidad, etapa, esperada):
        """EL FALLO DE LA SdA 62. Su PDF, de 1.º de Bachillerato en Cataluña,
        decía «Currículo aplicado: Cataluña (Decret 175/2022)», que es el
        decreto de la ESO. El suyo es el 171/2022.

        Es el dato que esa nota existe para dar, así que darlo mal es peor que
        no darlo: el documento va a la programación de un docente.
        """
        sa = _sa(filas=[_fila(comunidad=comunidad, etapa=etapa, idioma="ca")])

        assert procedencia_del_curriculo(sa)["norma"] == esperada

    def test_con_dos_etapas_citadas_no_se_elige_una(self):
        """No debería pasar —los enlaces se filtran por curso— pero si pasara,
        citar la norma de una de las dos afirmaría algo falso sobre la mitad
        del documento. Sin nota es peor de ver y mejor de fiar."""
        sa = _sa(filas=[_fila(comunidad="cataluna", etapa="ESO", idioma="ca"),
                        _fila(comunidad="cataluna", etapa="Bachillerato",
                              idioma="ca")])

        assert procedencia_del_curriculo(sa)["norma"] == ""

    def test_cada_comunidad_y_etapa_cargada_tiene_su_norma(self):
        """Si se carga un currículo y se olvida su norma, el documento sale
        sin la cita. Este test lo dice antes de que salga así.

        **SE COMPRUEBA POR (COMUNIDAD, ETAPA), Y ANTES SOLO POR COMUNIDAD.**
        Ese era el agujero: con `norma("cataluna")` bastaba que existiera la
        norma de la ESO para que el test pasara, y el Bachillerato catalán
        salía citando el Decret 175/2022 —el de la ESO— en el PDF de la SdA
        62. El vasco llevaba igual desde el 02/09.

        Comprobar la clave entera es lo que convierte esto en una guarda: la
        pareja que no esté en la tabla no puede colarse por parecerse a otra.
        """
        from pathlib import Path
        raiz = Path("/curriculo") if Path("/curriculo").is_dir() \
            else Path(__file__).resolve().parents[3] / "curriculo"
        salidas = [p for p in raiz.glob("salida*") if p.is_dir()]
        if not salidas:
            pytest.skip("no hay ninguna salida generada")
        # La comunidad y la etapa se leen **del propio JSON** y no se deducen
        # del nombre del directorio. Deducirlas funcionaba mientras hubo una
        # carpeta por comunidad y dejó de funcionar con
        # `salida_pais_vasco_bachillerato`: ese nombre lleva también la etapa,
        # y «pais-vasco-bachillerato» no es ninguna comunidad. El dato está
        # dentro del fichero; sacarlo del nombre era una segunda fuente
        # esperando a divergir.
        import json as _json
        parejas = set()
        for s in salidas:
            for f in s.glob("*.json"):
                datos = _json.loads(f.read_text(encoding="utf-8"))
                # Los de `salida/` son anteriores a los dos campos: son de
                # Ceuta y de la ESO.
                parejas.add((datos.get("comunidad") or "ceuta",
                             datos.get("etapa") or "ESO"))
        sin_norma = sorted(p for p in parejas if not comunidades.norma(*p))

        assert sin_norma == [], (
            f"tienen currículo generado y no están en NORMAS: {sin_norma}. "
            "Sus documentos saldrían sin citar la norma"
        )


class TestLaMezclaDeLenguas:

    def test_se_avisa_cuando_el_curriculo_va_en_otra_lengua(self):
        """El caso de la SdA 60: redactada en castellano, currículo en euskera."""
        p = procedencia_del_curriculo(_sa(idioma="es"))
        assert p["mezcla"] is True
        assert "Euskara" in texto_de_procedencia(p)

    def test_no_se_avisa_cuando_coinciden(self):
        """Repetirlo en la mayoría de los documentos sería ruido: lo que hay
        que explicar es la excepción."""
        p = procedencia_del_curriculo(_sa(idioma="eu"))
        assert p["mezcla"] is False
        assert "Euskara" not in texto_de_procedencia(p)

    def test_la_norma_se_cita_siempre(self):
        """Aunque no haya mezcla: un documento que cita currículo debe decir de
        qué norma sale, que es lo que el docente pone en su programación."""
        assert "Decreto 77/2023" in texto_de_procedencia(
            procedencia_del_curriculo(_sa(idioma="eu"))
        )

    def test_citar_dos_comunidades_se_dice(self):
        """No debería pasar —los enlaces se filtran por comunidad— pero si
        pasara significaría que el catálogo tiene filas cruzadas, y elegir una
        en silencio ocultaría el problema."""
        sa = _sa(filas=[_fila(comunidad="galicia", idioma="gl"),
                        _fila(comunidad="pais-vasco", idioma="eu")])
        p = procedencia_del_curriculo(sa)
        assert p["varias_comunidades"] is True
        assert "más de una comunidad" in texto_de_procedencia(p)


class TestLasDosRutasDicenLoMismo:
    """El texto se compone una vez y lo usan las dos."""

    def test_el_pdf_pinta_la_nota(self):
        """Sin base de datos: solo hay que mirar que la plantilla la reciba.

        Comprobar la salida real exigiría WeasyPrint y una SdA completa, y para
        lo que se quiere saber —que no se ha tocado una ruta y no la otra—
        basta con esto."""
        from pathlib import Path
        plantilla = (
            Path(__file__).resolve().parents[1].parent
            / "app" / "templates" / "exportacion" / "pdf.html"
        ).read_text(encoding="utf-8")
        assert "render_conexion_curricular(datos, conexion, procedencia)" in plantilla, (
            "el macro del PDF ya no recibe la procedencia"
        )

    def test_el_docx_pinta_la_nota(self):
        import inspect
        from app.services import exportacion_service as exp
        fuente = inspect.getsource(exp._docx_conexion_curricular)
        assert "texto_de_procedencia" in fuente, (
            "el DOCX ya no compone la nota con la función compartida"
        )
