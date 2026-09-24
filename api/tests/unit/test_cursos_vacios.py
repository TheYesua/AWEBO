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


def _raiz_curriculo() -> Path:
    """`/curriculo` dentro del contenedor; la del repositorio fuera."""
    return Path("/curriculo") if Path("/curriculo").is_dir() else APP.parents[1] / "curriculo"


def _carpetas_de_salida() -> set[str]:
    """Las carpetas de salida que existen, leídas del disco.

    Del disco y no de una lista escrita aquí: la que había tenía siete de las
    diez, y una lista a mano de las carpetas que existen tiene el mismo problema
    que el mapa web o la lista de `seed` del README —nadie la mira al añadir
    una—. Si la raíz no está montada devuelve vacío, y de eso avisa
    `test_estan_todas_las_salidas`.
    """
    raiz = _raiz_curriculo()
    if not raiz.is_dir():
        return set()
    return {d.name for d in raiz.iterdir() if d.is_dir() and d.name.startswith("salida")}


class TestLosDatosNoTienenFilasSinCursos:
    """Ya no debería haberlas. Si vuelve a aparecer una, es un fallo del
    extractor y conviene enterarse aquí y no en producción."""

    def test_estan_todas_las_salidas(self):
        """Regla 15, y aquí hacía falta de verdad.

        La lista de carpetas estaba **escrita a mano** y tenía siete de las
        diez: faltaban `salida_cataluna_batxillerat`, `salida_pais_vasco` y
        `salida_pais_vasco_bachillerato`. O sea que tres salidas enteras no se
        comprobaban, y una fila sin cursos ahí habría pasado sin que nadie se
        enterara —que es exactamente lo que le pasó a Robòtica i Programació
        durante dos días—.

        Se descubrió el 24/09 barriendo la batería en busca de tests que pasan
        por razones equivocadas. Ahora la lista sale del disco.
        """
        assert len(_carpetas_de_salida()) >= 10, sorted(_carpetas_de_salida())

    @pytest.mark.parametrize("carpeta", sorted(_carpetas_de_salida()))
    def test_ningun_json_viene_sin_cursos(self, carpeta):
        import json

        ruta = _raiz_curriculo() / carpeta
        if not ruta.is_dir():
            pytest.skip(f"{carpeta} no está generada")

        ficheros = sorted(ruta.glob("*.json"))
        assert ficheros, (
            f"{carpeta} existe y no tiene ni un JSON: sin esta comprobación, "
            f"el test de abajo pasaría en verde sin mirar nada"
        )

        sin_cursos = [
            f.name for f in ficheros
            if not json.loads(f.read_text(encoding="utf-8"))["cursos_aplicables"]
        ]

        assert sin_cursos == [], (
            f"estos JSON se cargarían invisibles: {sin_cursos}. Mira "
            f"CURSOS_FUERA_DEL_ARTICULADO en el extractor."
        )
