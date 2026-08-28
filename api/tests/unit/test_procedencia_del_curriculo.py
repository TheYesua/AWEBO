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


def _fila(comunidad="pais-vasco", idioma="eu"):
    return SimpleNamespace(comunidad=comunidad, idioma=idioma,
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

    def test_todas_las_comunidades_cargadas_tienen_su_norma(self):
        """Si se carga una comunidad y se olvida la norma, el documento sale
        sin la cita. Este test lo dice antes de que salga así."""
        from pathlib import Path
        raiz = Path("/curriculo") if Path("/curriculo").is_dir() \
            else Path(__file__).resolve().parents[3] / "curriculo"
        salidas = [p.name for p in raiz.glob("salida*") if p.is_dir()]
        if not salidas:
            pytest.skip("no hay ninguna salida generada")
        # `salida` a secas es Ceuta, por historia.
        codigos = {"salida": "ceuta"}
        for s in salidas:
            codigo = codigos.get(s) or s.replace("salida_", "").replace("_", "-")
            assert comunidades.norma(codigo), (
                f"«{codigo}» tiene currículo generado y no está en NORMAS: "
                "sus documentos saldrían sin citar la norma"
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
