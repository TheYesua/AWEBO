"""Los JSON del currículo caben en las columnas que los van a guardar.

EL FALLO QUE ESTO EVITA
------------------------
Cargando el País Vasco, el `seed` abortó a mitad con
`StringDataRightTruncation: value too long for type character varying(50)`:
cuatro materias del Decreto 77/2023 pasan de 50 caracteres y la más larga
llega a 57. En las otras cuatro comunidades el máximo era 46, así que el límite
nunca se había rozado.

Lo que hace que merezca un test propio no es el caso —ya está arreglado con la
migración `c9e4f2a10b73`— sino **cuándo se detectó**. El extractor daba 43 JSON
válidos, los 42 tests del extractor estaban en verde y los 1138 de la batería
también: nada podía saberlo, porque el límite no vive en el JSON sino en el
esquema. Solo se supo al ejecutar el `seed` contra una base real, que es un
paso manual y tardío.

Esta comprobación cruza las dos cosas **sin base de datos**: lee los límites
declarados en los modelos y mide los valores de los ficheros. Si mañana una
comunidad nueva trae un nombre largo, falla aquí y no a mitad de una carga.

POR QUÉ SE LEEN LOS LÍMITES DEL MODELO Y NO SE ESCRIBEN AQUÍ
--------------------------------------------------------------
Copiarlos sería crear una segunda fuente que se desincroniza en cuanto alguien
cambie una columna, y el test seguiría en verde diciendo que todo cabe. Se
preguntan a `__table__.columns`, que es lo que Alembic usa para generar las
migraciones.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.curriculo import Competencia, CriterioEvaluacion, SaberBasico


#: `curriculo/` se monta en `/curriculo` dentro del contenedor, no colgando de
#: la raíz —que ahí es `/repo` y solo tiene cuatro ficheros sueltos—.
_RAIZ = Path(__file__).resolve().parents[3]
_CURRICULO = (Path("/curriculo") if Path("/curriculo").is_dir()
              else _RAIZ / "curriculo")

#: Todas las salidas de extractor que hay. Se descubren en vez de listarse para
#: que una comunidad nueva quede cubierta el día que se genere, sin que nadie
#: tenga que acordarse de añadirla aquí.
_SALIDAS = sorted(p for p in _CURRICULO.glob("salida*") if p.is_dir())


def _limite(modelo, columna: str) -> int:
    return modelo.__table__.columns[columna].type.length


def _ficheros() -> list[Path]:
    return [f for d in _SALIDAS for f in sorted(d.glob("*.json"))]


#: (clave del JSON, modelo, columna). El nombre en el fichero y el de la
#: columna no siempre coinciden: en el JSON la materia va como `materia` y el
#: nombre oficial como `materia_oficial`, y los dos acaban en la misma columna
#: según qué extractor.
_CAMPOS = (
    ("materia", Competencia, "materia"),
    ("materia_oficial", Competencia, "materia"),
    ("comunidad", Competencia, "comunidad"),
    ("idioma", Competencia, "idioma"),
)


@pytest.mark.skipif(not _SALIDAS, reason="no hay ninguna salida generada")
class TestLosNombresCaben:

    @pytest.mark.parametrize("clave, modelo, columna", _CAMPOS)
    def test_el_campo_cabe_en_su_columna(self, clave, modelo, columna):
        tope = _limite(modelo, columna)
        largos = []
        for f in _ficheros():
            j = json.loads(f.read_text(encoding="utf-8"))
            v = j.get(clave) or ""
            if len(v) > tope:
                largos.append(f"{f.parent.name}/{f.name}: {len(v)} > {tope} · {v}")
        assert not largos, (
            f"«{clave}» no cabe en {modelo.__tablename__}.{columna} "
            f"({tope}):\n" + "\n".join(largos[:10])
        )

    def test_los_codigos_caben(self):
        """`codigo` es corto en todas partes y por eso conviene vigilarlo: un
        extractor que se equivoque y meta el texto entero en el código no da
        error hasta que alguien carga."""
        topes = {
            "competencias_especificas": _limite(Competencia, "codigo"),
            "criterios_evaluacion": _limite(CriterioEvaluacion, "codigo"),
        }
        largos = []
        for f in _ficheros():
            j = json.loads(f.read_text(encoding="utf-8"))
            for seccion, tope in topes.items():
                for e in j.get(seccion, []):
                    if len(e.get("codigo") or "") > tope:
                        largos.append(f"{f.name}: {e['codigo']!r} > {tope}")
        assert not largos, "códigos demasiado largos:\n" + "\n".join(largos[:10])

    def test_el_titulo_del_bloque_cabe(self):
        tope = _limite(SaberBasico, "bloque")
        largos = []
        for f in _ficheros():
            j = json.loads(f.read_text(encoding="utf-8"))
            for b in j.get("saberes_basicos", []):
                if len(b.get("bloque") or "") > tope:
                    largos.append(f"{f.name}: {len(b['bloque'])} > {tope}")
        assert not largos, "bloques demasiado largos:\n" + "\n".join(largos[:10])

    def test_hay_margen_de_sobra_y_no_justo(self):
        """Un límite que se cumple por un carácter es el siguiente en saltar.

        No es una comprobación de corrección sino un aviso: cuando el nombre
        más largo del catálogo se acerque al tope, conviene ampliarlo antes de
        que lo haga por nosotros una carga a medias."""
        tope = _limite(Competencia, "materia")
        mayor = max(
            (len(json.loads(f.read_text(encoding="utf-8")).get(c) or "")
             for f in _ficheros() for c in ("materia", "materia_oficial")),
            default=0,
        )
        assert mayor <= tope * 0.9, (
            f"el nombre más largo mide {mayor} y la columna admite {tope}: "
            "queda menos del 10 % de margen"
        )
