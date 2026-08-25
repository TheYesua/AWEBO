"""Una fila de currículo sin cursos no casa con ninguno.

EL PROBLEMA
------------
Con `cursos_aplicables = []`, dos capas respondían distinto a la misma
pregunta:

* `prompts/contexto.py` usa el operador JSONB `?`, que con la lista vacía
  **excluye** la fila: el modelo nunca la ve.
* `services/enlaces_curriculares.py` hacía `not fila.cursos_aplicables or curso
  in …`, que con la lista vacía **acepta para cualquier curso**.

Hoy no explotaba, porque lo que no entra en el contexto no lo cita el modelo y
por tanto nunca llegaba a enlazarse. Pero es una discrepancia esperando a que
un código llegue por otra vía —una SdA importada, una regeneración con el
catálogo a medias— y entonces una fila mal cargada encaja en los cuatro cursos.

POR QUÉ SE UNIFICÓ HACIA EXCLUIR
---------------------------------
Por lo que significa el estado, no por cuál de las dos era más cómoda. Un
elemento de currículo sin cursos **no es «válido para todos»**: es un elemento
del que no se sabe dónde va. Tratarlo como comodín hace que el catálogo afirme
que algo se imparte en 1.º de ESO cuando ninguna norma lo dice, y ese error
viaja hasta el documento del docente, que es donde más caro sale descubrirlo.

Aceptarlo tampoco tenía a favor ningún caso real: la única materia que estaba
así —Robòtica i Programació— era precisamente un fallo de carga, no un
currículo transversal.

Y el estado deja de ser silencioso: el seed lo registra con nivel `error` al
cargarlo, que es donde todavía se puede arreglar.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


APP = Path(__file__).resolve().parents[2] / "app"


class TestLasTresCapasUsanElMismoCriterio:
    """Comprobación sobre el código, porque las tres consultan de formas
    distintas —SQL con `?`, comprensión de listas en Python— y no hay una
    función común que se pueda llamar desde un test."""

    def test_enlaces_no_acepta_las_filas_sin_cursos(self):
        fuente = (APP / "services" / "enlaces_curriculares.py").read_text(encoding="utf-8")

        # El patrón viejo, en cualquiera de sus dos apariciones.
        vivo = [
            l.strip() for l in fuente.splitlines()
            if re.search(r"not \w+\.cursos_aplicables or", l) and not l.strip().startswith("#")
        ]

        assert vivo == [], f"vuelve a aceptar cursos vacíos como comodín: {vivo}"

    def test_el_contexto_sigue_excluyendo(self):
        """`?` es el operador de existencia de JSONB: con `[]` no encuentra
        nada. Si alguien lo cambiara por un `or`, la incoherencia volvería por
        el otro lado."""
        fuente = (APP / "prompts" / "contexto.py").read_text(encoding="utf-8")

        assert 'cursos_aplicables.op("?")(curso)' in fuente

    def test_la_cobertura_usa_el_mismo_criterio_que_el_enlace(self):
        """Si divergieran, una materia podría dar «hay currículo» en la
        comprobación de cobertura y luego no enlazar ni un código."""
        fuente = (APP / "services" / "enlaces_curriculares.py").read_text(encoding="utf-8")

        usos = re.findall(r"curso in \(\w+\.cursos_aplicables or \[\]\)", fuente)

        assert len(usos) == 2, f"esperaba las dos comprobaciones, hay {len(usos)}"


class TestElSeedAvisaDeLoQueNoSePodraUsar:
    def test_registra_un_error_cuando_faltan_los_cursos(self):
        """Sin aviso, el resultado es una materia **invisible**: se carga, no
        aparece en ningún desplegable y no enlaza nada. Robòtica i Programació
        estuvo así dos días sin que se notara."""
        fuente = (APP / "seeds" / "seed_curriculo.py").read_text(encoding="utf-8")

        assert "SIN CURSOS" in fuente
        assert re.search(r"if not cursos:\s*\n(\s*#[^\n]*\n)*\s*logger\.error", fuente), (
            "el aviso debe ser `error`: un warning se pierde entre los "
            "«Procesando …» de una carga de 36 ficheros"
        )


class TestLosDatosNoTienenFilasSinCursos:
    """Ya no debería haberlas. Si vuelve a aparecer una, es un fallo del
    extractor y conviene enterarse aquí y no en producción."""

    @pytest.mark.parametrize("carpeta", ["salida", "salida_cataluna", "salida_andalucia"])
    def test_ningun_json_viene_sin_cursos(self, carpeta):
        import json

        raiz = Path("/curriculo") if Path("/curriculo").is_dir() else APP.parents[1] / "curriculo"
        ruta = raiz / carpeta
        if not ruta.is_dir():
            pytest.skip(f"{carpeta} no está generada")

        sin_cursos = [
            f.name for f in ruta.glob("*.json")
            if not json.loads(f.read_text(encoding="utf-8"))["cursos_aplicables"]
        ]

        assert sin_cursos == [], (
            f"estos JSON se cargarían invisibles: {sin_cursos}. Mira "
            f"CURSOS_FUERA_DEL_ARTICULADO en el extractor."
        )
