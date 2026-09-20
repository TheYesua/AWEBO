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

from app.services.exportacion_service import MISMO_BLOQUE, filas_de_conexion


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


class TestElBloqueNoSeRepiteEnFilasSeguidas:
    """El BOE no siempre titula el bloque con una etiqueta.

    En las materias literarias de la Orden EFP/755 el título del bloque es la
    frase entera que introduce sus saberes: el bloque A de Literatura Dramática
    mide **390 caracteres**. Pintado en cada fila, cinco saberes ocupaban una
    página entera del PDF y el docente leía el mismo párrafo cinco veces.

    Se colapsa en `filas_de_conexion` y no en las plantillas porque son dos
    —PDF y DOCX— y olvidarse de una ya costó un fallo.
    """

    #: El de verdad, tal cual está en `saber_basico.bloque`.
    LARGO = (
        "A. Construcción guiada y compartida de la interpretación de algunos "
        "textos relevantes de la literatura dramática inscritos en itinerarios "
        "temáticos que establezcan relaciones intertextuales entre obras y "
        "fragmentos de diferentes géneros, épocas, contextos culturales y "
        "códigos artísticos, así como con sus respectivos contextos de "
        "producción, de acuerdo a los siguientes ejes y estrategias:"
    )

    def _tres_del_mismo_bloque(self):
        return _sa(
            citados={"saberes": [
                {"codigo": "A.1", "justificacion": "j1"},
                {"codigo": "A.2", "justificacion": "j2"},
                {"codigo": "A.3", "justificacion": "j3"},
            ]},
            saberes=[
                NS(codigo="A.1", bloque=self.LARGO, descripcion="El libreto."),
                NS(codigo="A.2", bloque=self.LARGO, descripcion="El personaje."),
                NS(codigo="A.3", bloque=self.LARGO, descripcion="La escena."),
            ],
        )

    def test_la_primera_lo_dice_entero_y_las_siguientes_no(self):
        filas = filas_de_conexion(self._tres_del_mismo_bloque())["saberes"]

        assert filas[0]["bloque"] == self.LARGO
        assert filas[1]["bloque"] == MISMO_BLOQUE
        assert filas[2]["bloque"] == MISMO_BLOQUE

    def test_seguidas_no_es_lo_mismo_que_iguales(self):
        """Si el generador cita A, B y otra vez A, esa segunda A va entera:
        ya no está debajo de la suya."""
        sa = _sa(
            citados={"saberes": [{"codigo": c, "justificacion": "j"}
                                 for c in ("A.1", "B.1", "A.2")]},
            saberes=[
                NS(codigo="A.1", bloque="Bloque A", descripcion="uno"),
                NS(codigo="B.1", bloque="Bloque B", descripcion="dos"),
                NS(codigo="A.2", bloque="Bloque A", descripcion="tres"),
            ],
        )

        assert [f["bloque"] for f in filas_de_conexion(sa)["saberes"]] == [
            "Bloque A", "Bloque B", "Bloque A",
        ]

    def test_un_bloque_que_falta_no_se_colapsa(self):
        """«—» ya significa «no hay dato» y es corto: sustituirlo por «↳»
        diría «el mismo que arriba» de algo que no hay."""
        sa = _sa(
            citados={"saberes": [{"codigo": c, "justificacion": "j"}
                                 for c in ("X.1", "X.2")]},
            saberes=[
                NS(codigo="X.1", bloque="", descripcion="uno"),
                NS(codigo="X.2", bloque="", descripcion="dos"),
            ],
        )

        assert [f["bloque"] for f in filas_de_conexion(sa)["saberes"]] == ["—", "—"]

    def test_la_marca_no_es_una_celda_vacia(self):
        """Los dos caminos de exportación tratan distinto una cadena vacía: el
        PDF la pinta «—» —que aquí significa «no hay dato»— y el DOCX la deja
        en blanco. Una marca explícita hace que pinten lo mismo, que es para lo
        que existe `filas_de_conexion`."""
        assert MISMO_BLOQUE
        assert MISMO_BLOQUE != "—"


class TestElCriterioConDosObxectivos:
    """Lo que se guarda para no perderlo tiene que llegar al documento.

    `competencias_extra` se añadió el 20/09 porque la Guía LOMLOE asigna dos
    objetivos a dos criterios de Lingua Galega e Literatura de 1.º de
    Bacharelato: «OBX1 10». Guardarlo en una columna y no pintarlo habría sido
    no perderlo solo sobre el papel — el PDF del docente es donde ese dato se
    lee.
    """

    def _sa(self, extra):
        return _sa(
            citados={"criterios": [{"codigo": "1.3", "competencia": "1",
                                    "justificacion": "j"}]},
            competencias=[NS(codigo="1", descripcion="Explicar a diversidade")],
            criterios=[NS(codigo="1.3", descripcion="Recoñecer as linguas",
                          competencias_extra=extra)],
        )

    def test_se_pintan_los_dos(self):
        fila = filas_de_conexion(self._sa(["10"]))["criterios"][0]

        assert fila["competencia"] == "1, 10"

    def test_con_uno_solo_no_cambia_nada(self):
        """Ocho de las nueve comunidades no tienen ninguno: la columna tiene
        que seguir diciendo exactamente lo que decía."""
        fila = filas_de_conexion(self._sa([]))["criterios"][0]

        assert fila["competencia"] == "1"

    def test_sale_del_catalogo_y_no_de_lo_que_cito_el_modelo(self):
        """El JSONB de la SdA solo guarda el código que escribió el modelo. El
        reparto entre principal y extra lo decide el boletín, así que se lee de
        la fila del catálogo."""
        sa = _sa(
            citados={"criterios": [{"codigo": "1.3", "competencia": "1",
                                    "justificacion": "j"}]},
            competencias=[NS(codigo="1", descripcion="Explicar")],
            criterios=[NS(codigo="1.3", descripcion="Recoñecer",
                          competencias_extra=["10"])],
        )

        assert filas_de_conexion(sa)["criterios"][0]["competencia"] == "1, 10"

    def test_una_fila_sin_el_campo_no_revienta(self):
        """Las filas anteriores a la migración no lo traen, y un `getattr` con
        defecto es más barato que una guarda en cada sitio."""
        sa = _sa(
            citados={"criterios": [{"codigo": "1.3", "competencia": "1",
                                    "justificacion": "j"}]},
            competencias=[NS(codigo="1", descripcion="Explicar")],
            criterios=[NS(codigo="1.3", descripcion="Recoñecer")],
        )

        assert filas_de_conexion(sa)["criterios"][0]["competencia"] == "1"
