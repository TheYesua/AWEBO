"""La conexión curricular exportada dice QUÉ cita, no solo su código.

EL PROBLEMA QUE RESUELVE
-------------------------
Hasta el 16/08/2026 las tres tablas de la conexión curricular se pintaban con
dos columnas: código y justificación. El docente recibía esto:

    | Código | Justificación          |
    | 20.1   | Se trabaja al analizar |

Y no tenía forma de saber a qué saber se refiere `20.1`. En Cataluña era
directamente un callejón sin salida: **el Decret 175/2022 no numera sus bloques
de saberes**, así que ese código es un índice de orden nuestro que no aparece
en ningún boletín. En Ceuta y Andalucía el código sí es real, pero obligaba a
abrir el BOE o el BOJA para saber qué dice.

El texto estaba disponible desde el 11/08 y no se usaba: `enlaces_curriculares`
deja pobladas `sa.competencias`, `sa.criterios` y `sa.saberes` con las filas
reales del catálogo.

POR QUÉ ESTE FICHERO INSISTE EN LAS DOS RUTAS
----------------------------------------------
Porque hay **dos** exportaciones —PDF por plantilla Jinja y DOCX por
python-docx— y ya se falló una vez en esto: el 14/08 el aviso de sección
incompleta se añadió solo al DOCX y el PDF salió sin él durante un día. Nadie
lo detectó porque cada ruta se probaba por separado y las dos pasaban.
"""
from __future__ import annotations

import re
from types import SimpleNamespace as NS

import pytest

from app.services.exportacion_service import filas_de_conexion


def _sa(citados: dict, competencias=(), criterios=(), saberes=()):
    return NS(
        contenido={"conexion_curricular": citados},
        competencias=list(competencias),
        criterios=list(criterios),
        saberes=list(saberes),
        # La SdA real siempre tiene idioma: es lo que decide en qué lengua se
        # redacta, y de compararlo con el del currículo sale el aviso de
        # documento bilingüe.
        idioma="ca",
    )


CATALAN = _sa(
    citados={
        "competencias": [{"codigo": "2", "justificacion": "Justif. comp."}],
        "criterios": [{"codigo": "2.1", "competencia": "2", "justificacion": "Justif. crit."}],
        "saberes": [{"codigo": "20.1", "justificacion": "Justif. saber."}],
    },
    # `comunidad` e `idioma` van en el doble porque van en la fila real: son
    # NOT NULL en las tres tablas desde la migración `a4c81e9d2f60`. Un doble
    # que no se parece a lo que sustituye deja pasar fallos — este los dejó
    # pasar hasta que `procedencia_del_curriculo` los pidió.
    competencias=[NS(codigo="2", descripcion="Cercar i seleccionar informació",
                     comunidad="cataluna", idioma="ca")],
    criterios=[NS(codigo="2.1", descripcion="Analitzar conceptes i processos",
                  comunidad="cataluna", idioma="ca")],
    saberes=[NS(codigo="20.1", bloque="Comunicació · Context",
                descripcion="Els elements del context comunicatiu",
                comunidad="cataluna", idioma="ca")],
)


class TestElTextoLlegaALaTabla:
    def test_cada_parte_trae_su_texto(self):
        filas = filas_de_conexion(CATALAN)

        assert filas["competencias"][0]["texto"] == "Cercar i seleccionar informació"
        assert filas["criterios"][0]["texto"] == "Analitzar conceptes i processos"
        assert filas["saberes"][0]["texto"] == "Els elements del context comunicatiu"

    def test_el_saber_trae_su_bloque(self):
        """Es lo que sitúa el saber en el decreto cuando no hay número: el
        decreto nombra sus bloques aunque no los numere."""
        assert filas_de_conexion(CATALAN)["saberes"][0]["bloque"] == "Comunicació · Context"

    def test_se_conserva_la_justificacion_del_modelo(self):
        """El texto es del catálogo y la justificación del modelo. Si al
        combinar se perdiera una de las dos, la tabla quedaría a medias."""
        filas = filas_de_conexion(CATALAN)

        assert filas["saberes"][0]["justificacion"] == "Justif. saber."
        assert filas["criterios"][0]["competencia"] == "2"


class TestLosCodigosHuerfanos:
    """Los que el modelo cita y no existen en el catálogo."""

    def test_se_dicen_en_vez_de_dejar_la_celda_vacia(self):
        """Un hueco en blanco parece un fallo de formato; el aviso dice que hay
        algo que revisar. Y es la señal de que el modelo se inventó el código,
        que es la única medida directa que hay de cuánto alucina."""
        sa = _sa(
            citados={"saberes": [{"codigo": "99.9", "justificacion": "inventado"}]},
            saberes=[NS(codigo="20.1", bloque="B", descripcion="Existe")],
        )

        fila = filas_de_conexion(sa)["saberes"][0]

        assert "no encontrado" in fila["texto"]
        assert fila["justificacion"] == "inventado"

    def test_no_se_inventa_un_texto_plausible(self):
        """Rellenar con el saber más parecido sería peor que dejarlo vacío:
        el documento afirmaría algo que la norma no dice."""
        sa = _sa(
            citados={"saberes": [{"codigo": "99.9", "justificacion": "x"}]},
            saberes=[NS(codigo="20.1", bloque="B", descripcion="Els elements del context")],
        )

        assert "context" not in filas_de_conexion(sa)["saberes"][0]["texto"].lower()


class TestCasosQueRompenElCombinado:
    def test_una_seccion_ausente_no_revienta(self):
        """Pasa de verdad: el modelo devuelve la conexión sin `criterios`. Ya
        hay un aviso para eso; lo que no puede es fallar al exportar."""
        filas = filas_de_conexion(_sa(citados={"competencias": []}))

        assert filas["criterios"] == []
        assert filas["saberes"] == []

    def test_una_sda_sin_contenido_no_revienta(self):
        filas = filas_de_conexion(NS(contenido=None, competencias=[], criterios=[], saberes=[]))

        assert filas == {"competencias": [], "criterios": [], "saberes": []}

    def test_un_citado_que_no_es_diccionario_se_ignora(self):
        """El JSONB viene del modelo: si devuelve una lista de cadenas en vez
        de objetos, hay que sobrevivir. Antes esto lanzaba AttributeError en
        mitad de la exportación."""
        sa = _sa(citados={"saberes": ["20.1", {"codigo": "20.1", "justificacion": "ok"}]})

        assert len(filas_de_conexion(sa)["saberes"]) == 1

    def test_la_conexion_no_es_un_diccionario(self):
        sa = NS(contenido={"conexion_curricular": "texto suelto"},
                competencias=[], criterios=[], saberes=[])

        assert filas_de_conexion(sa)["saberes"] == []


class TestLasDosRutasPintanLoMismo:
    """EL TEST QUE IMPORTA, por el historial: PDF y DOCX se calculan de la
    misma fuente. Si divergen tiene que ser por una cabecera distinta, no
    porque una tenga datos que la otra no."""

    def test_el_docx_se_genera_de_verdad(self):
        """EL TEST QUE FALTABA, y su ausencia costó una exportación rota.

        Al renombrar `textos_del_catalogo` a `filas_de_conexion` quedó la
        llamada vieja dentro de `renderizar_docx`. **Toda la exportación a DOCX
        lanzaba NameError**, y los usuarios veían la descarga fallar.

        Los tests de entonces no lo vieron porque ninguno ejecutaba
        `renderizar_docx`: probaban `filas_de_conexion` por su cuenta y
        comprobaban con `in` que ciertas líneas estuvieran en el fichero. Y el
        colmo — uno de esos `assert` daba por buena justamente la línea rota,
        porque comprobaba que el texto apareciera, no que funcionara.

        Comprobar el código fuente con `in` no es probar el camino."""
        import io

        from docx import Document

        from app.services.exportacion_service import renderizar_docx

        sa = NS(
            titulo="Prova", id_situacion=58, id_situacion_origen=None,
            tipo_adaptacion=None, materia="Llatí", curso="4º ESO",
            num_sesiones=5, duracion_sesion_minutos=55,
            contenido=CATALAN.contenido,
            competencias=CATALAN.competencias,
            criterios=CATALAN.criterios,
            saberes=CATALAN.saberes,
        )

        datos = renderizar_docx(sa, NS(nombre="Ana", centro_educativo="IES X"))

        assert datos[:2] == b"PK", "un DOCX es un zip"
        doc = Document(io.BytesIO(datos))
        filas = [[c.text for c in t.rows[-1].cells] for t in doc.tables]
        # El texto del saber llega hasta el documento final, no solo al dict.
        assert any("Els elements del context comunicatiu" in c
                   for f in filas for c in f)
        assert any("Comunicació · Context" in c for f in filas for c in f)

    def test_el_pdf_pinta_desde_las_filas_combinadas(self):
        """De la plantilla sí se comprueba el texto, porque renderizarla exige
        contexto de aplicación y eso ya es un test de integración. Lo que se
        vigila es que no vuelva a pintar del JSONB crudo."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[1].parent / "app"
        py = (raiz / "services" / "exportacion_service.py").read_text(encoding="utf-8")
        html = (raiz / "templates" / "exportacion" / "pdf.html").read_text(encoding="utf-8")

        assert "conexion=filas_de_conexion(sa)" in py
        assert "conexion.saberes" in html
        assert "tabla_curr(d.saberes" not in html, "el PDF volvió a pintar del JSONB"

    def test_las_cabeceras_son_las_mismas_en_las_dos(self):
        """Este test existe porque el desliz se cometió al escribir el propio
        arreglo: el PDF pasó a traducir sus cabeceras y el DOCX se quedó con
        ellas en castellano fijo. Las dos rutas se probaban por separado y las
        dos pasaban.

        Se comparan los rótulos marcados para traducir, que es lo que se ve en
        la cabecera de cada tabla."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[1].parent / "app"
        py = (raiz / "services" / "exportacion_service.py").read_text(encoding="utf-8")
        html = (raiz / "templates" / "exportacion" / "pdf.html").read_text(encoding="utf-8")

        bloque_docx = py[py.index("def _docx_conexion_curricular"):]
        bloque_docx = bloque_docx[:bloque_docx.index("\ndef ", 10)] if "\ndef " in bloque_docx[10:] else bloque_docx
        macro_pdf = html[html.index("macro render_conexion_curricular"):
                         html.index("macro render_secuencia")]

        rotulos_docx = set(re.findall(r'_\("([^"]+)"\)', bloque_docx))
        rotulos_pdf = set(re.findall(r"_\('([^']+)'\)", macro_pdf))

        solo_docx = rotulos_docx - rotulos_pdf
        assert solo_docx == set(), f"el DOCX rotula cosas que el PDF no: {solo_docx}"

    def test_ningun_rotulo_de_tabla_se_quedo_sin_traducir(self):
        """Las cabeceras del DOCX estaban en castellano fijo desde siempre. Al
        añadir columnas habrían quedado más, y el documento sale en el idioma
        de la interfaz."""
        from pathlib import Path

        py = (Path(__file__).resolve().parents[1].parent / "app" / "services"
              / "exportacion_service.py").read_text(encoding="utf-8")
        bloque = py[py.index("def _docx_conexion_curricular"):]
        bloque = bloque[:bloque.index("\ndef ", 10)] if "\ndef " in bloque[10:] else bloque

        crudas = re.findall(r'cabecera=\[([^\]]+)\]', bloque)
        for lista in crudas:
            sin_marcar = [
                t for t in re.findall(r'"([^"]+)"', lista)
                if f'_("{t}")' not in lista
            ]
            assert sin_marcar == [], f"cabeceras sin traducir: {sin_marcar}"

    @pytest.mark.parametrize("parte, columnas", [
        ("competencias", {"codigo", "texto", "justificacion"}),
        ("criterios", {"codigo", "competencia", "texto", "justificacion"}),
        ("saberes", {"codigo", "bloque", "texto", "justificacion"}),
    ])
    def test_cada_fila_trae_todas_sus_columnas(self, parte, columnas):
        """Si falta una clave, una ruta pinta «—» y la otra revienta con
        KeyError. Mejor que las filas estén completas desde el origen."""
        filas = filas_de_conexion(CATALAN)[parte]

        assert filas and set(filas[0]) == columnas
