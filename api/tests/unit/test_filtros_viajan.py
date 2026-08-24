"""Los filtros del listado llegan al servidor, y el servidor los aplica.

EL FALLO
---------
El selector de provincia se montó el 15/08 **sin atributo `name`**, con este
razonamiento escrito en la propia plantilla:

    la provincia no filtra situaciones, solo decide qué materias se ofrecen.
    El endpoint acepta `curso` y `materia`, no `provincia`; mandarla sería
    inventar un filtro que el servidor ignora.

El razonamiento describe el mecanismo y no lo que espera quien lo usa. El
resultado fue lo contrario de lo pretendido: en vez de no prometer un filtro
inexistente, quedó un desplegable que promete y no cumple. Elegir «Barcelona»
seguía mostrando las SdA de Sevilla.

Y era difícil de describir porque **sí parecía funcionar** en cuanto se añadía
además un curso: entonces filtraba el curso.

POR QUÉ UN TEST DE PLANTILLA
-----------------------------
Porque el envío se hace con `new FormData(formulario)`, que recoge **por
`name`**. Un `<select>` sin `name` es invisible para el envío, y eso no lo ve
ningún test de servidor: el endpoint funciona perfectamente con el parámetro
que nunca le llega.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


PLANTILLA = (
    Path(__file__).resolve().parents[1].parent
    / "app" / "templates" / "situaciones" / "listar.html"
)
SERVICIO = (
    Path(__file__).resolve().parents[1].parent
    / "app" / "services" / "situacion_service.py"
)
ENDPOINT = (
    Path(__file__).resolve().parents[1].parent / "app" / "api" / "situaciones.py"
)


@pytest.fixture(scope="module")
def html() -> str:
    return PLANTILLA.read_text(encoding="utf-8")


class TestLosSelectoresViajan:
    @pytest.mark.parametrize("campo", ["provincia", "curso", "materia"])
    def test_cada_filtro_tiene_name(self, html, campo):
        """Sin `name`, `FormData` no lo recoge y el filtro no sale del navegador."""
        patron = re.compile(
            r'<select[^>]*id="f-' + campo + r'"[^>]*>', re.S
        )
        etiqueta = patron.search(html)

        assert etiqueta, f"no existe el selector f-{campo}"
        assert f'name="{campo}"' in etiqueta.group(0), (
            f'f-{campo} no tiene name: no viajará al servidor.\n{etiqueta.group(0)}'
        )

    def test_el_formulario_envia_por_formdata(self, html):
        """Si algún día se envía a mano campo a campo, el test de arriba deja
        de significar nada y conviene enterarse."""
        assert "new FormData(ev.target)" in html


class TestElServidorLosAplica:
    """La otra mitad: que el parámetro no se quede en el camino.

    Son tres saltos —plantilla, endpoint y servicio— y basta que uno falte
    para que el filtro no haga nada sin dar ningún error."""

    def test_el_endpoint_lee_la_provincia(self):
        assert 'provincia=request.args.get("provincia")' in ENDPOINT.read_text(
            encoding="utf-8"
        )

    def test_el_servicio_construye_la_condicion(self):
        py = SERVICIO.read_text(encoding="utf-8")

        assert "SituacionAprendizaje.provincia == provincia" in py

    def test_listar_y_contar_reciben_lo_mismo(self):
        """Comparten `_filtros_listado` justamente para no divergir. Si una
        aceptara provincia y la otra no, el total contaría más filas de las que
        se ven y el paginador prometería páginas vacías."""
        py = SERVICIO.read_text(encoding="utf-8")

        assert py.count("provincia: str | None = None") >= 3, (
            "provincia debe estar en _filtros_listado, listar y contar"
        )


class TestLaCondicionSeConstruyeDeVerdad:
    """Ejecutando el código, no leyéndolo.

    Los tests de arriba comprueban texto, y eso ya falló una vez esta misma
    sesión: un `assert "..." in fichero` dio por buena una línea que lanzaba
    NameError al ejecutarse."""

    @staticmethod
    def _filtros(**kwargs):
        from types import SimpleNamespace as NS

        from app.services.situacion_service import _filtros_listado

        base = dict(curso=None, materia=None, estado=None, q=None,
                    incluir_adaptaciones=True)
        return _filtros_listado(
            NS(es_administrador=False, id_usuario=1), **{**base, **kwargs}
        )

    def test_la_provincia_sola_anade_su_condicion(self):
        """EL CASO DEL FALLO: provincia y nada más."""
        sin = self._filtros()
        con = self._filtros(provincia="barcelona")

        assert len(con) == len(sin) + 1
        assert any("provincia" in str(c) for c in con)

    def test_no_sustituye_a_los_demas(self):
        con_dos = self._filtros(provincia="barcelona", curso="1º ESO")

        assert len(con_dos) == len(self._filtros()) + 2

    def test_una_provincia_vacia_no_filtra(self):
        """«Todas» manda cadena vacía, no ausencia. Si se tratara como valor,
        el listado saldría siempre vacío."""
        assert len(self._filtros(provincia="")) == len(self._filtros())
