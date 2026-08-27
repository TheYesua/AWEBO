"""Lo que la documentación afirma tiene que ser verdad.

POR QUÉ EXISTE ESTE FICHERO
----------------------------
Porque el README y la hoja de ruta han afirmado cosas falsas tres veces, y las
tres se descubrieron por casualidad:

1. «Los correos se redactan siempre en castellano» — llevaban días saliendo en
   el idioma de la interfaz, con once tests vigilándolo. Estaba escrito como
   pendiente en tres sitios de la hoja de ruta mientras un cuarto ya decía lo
   contrario.
2. «Licencia: pendiente de definir antes de la publicación del repositorio» —
   el repositorio llevaba un mes publicado **y el fichero `LICENSE` existía**.
   Preguntar qué licencia poner sin comprobarlo acabó sobrescribiendo una
   GPL-3.0 por una AGPL-3.0.
3. Cifras: «998 tests» cuando eran 1039, «452 cadenas» cuando eran 593, «21
   materias» cuando el catálogo tenía tres comunidades.

El patrón es siempre el mismo: **la documentación se actualizaba de memoria, o
contra otro documento, en vez de contra el código**. Un documento que se
escribe leyendo otro documento hereda sus errores y añade los suyos.

QUÉ SE COMPRUEBA, Y QUÉ NO
---------------------------
Solo lo que tiene una fuente de verdad automática: cifras que se pueden contar
y ficheros que se pueden abrir. No se comprueba la prosa — eso no lo puede
hacer un test, y fingir que sí daría una falsa sensación de seguridad.

Cuando uno de estos falle, **la documentación es lo que hay que corregir**, no
el test: el test lee la realidad.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


#: Dónde se montan dentro del contenedor los ficheros que no son de la
#: aplicación. Mismo mecanismo que `test_configuracion.py`, y por el mismo
#: motivo: **la imagen solo copia `api/`**, así que dentro no hay README, ni
#: LICENSE, ni `.gitignore`. Subir tres niveles desde `/app/tests/unit` da `/`.
#:
#: La primera versión de este fichero no lo tuvo en cuenta y los nueve tests
#: que leen la raíz fallaron con `FileNotFoundError: '/README.md'` — fuera de
#: Docker pasaban todos. Es exactamente el fallo que `test_configuracion.py`
#: ya documentaba en su docstring, y que no busqué antes de escribir esto.
MONTADOS = Path("/repo")

#: Ficheros del repositorio que este test necesita leer. **Añadir uno aquí
#: obliga a añadirlo también** a los `volumes` de `docker-compose.override.yml`
#: y al paso `pytest` de `.github/workflows/verificar.yml`.
FICHEROS_DEL_REPO = ("README.md", "LICENSE", "LICENSE-DOCS", ".gitignore")


def _raiz(montados: Path | None = None) -> Path:
    """La raíz del repositorio, esté donde esté.

    Recibe `montados` como parámetro —y lo consulta dentro, no como valor por
    defecto— para poder ejercitar **las dos ramas** desde un test. Es la misma
    solución que `test_configuracion.py`, cuyo comentario explica el matiz: un
    valor por defecto se evalúa al definir la función, así que
    `def _raiz(montados=MONTADOS)` congelaría la constante y reasignarla en un
    test no tendría ningún efecto.

    Importa porque **la rama del contenedor es la que falló**: fuera de Docker
    pasaban los catorce y dentro reventaban nueve.
    """
    montados = MONTADOS if montados is None else montados
    if (montados / "README.md").is_file():
        return montados
    return Path(__file__).resolve().parents[3]


RAIZ = _raiz()
README = RAIZ / "README.md"
HOJA = RAIZ / "docs" / "HOJA_DE_RUTA.md"

#: El árbol de tests, que SÍ está siempre: es parte de la aplicación. Se
#: deriva de `__file__` y no de `RAIZ`, porque dentro del contenedor la raíz
#: es `/repo` —cuatro ficheros sueltos— y la aplicación vive en `/app`.
TESTS = Path(__file__).resolve().parents[1]

#: `curriculo/` sí está dentro del contenedor, pero en su propio punto de
#: montaje (`/curriculo`), no colgando de la raíz.
CURRICULO = Path("/curriculo") if Path("/curriculo").is_dir() else RAIZ / "curriculo"
README_CURRICULO = CURRICULO / "README.md"


def _texto(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _saltar_si_no_esta(p: Path) -> None:
    """No todo está en todas partes, y eso no es un fallo.

    `docs/` vive en un repositorio privado aparte: quien clone solo el público
    no lo tiene. Y dentro del contenedor, lo que no esté montado tampoco. En
    los dos casos se salta con el motivo dicho, en vez de fallar por el
    entorno."""
    if not p.exists():
        pytest.skip(
            f"{p.name} no está en {p.parent}. Si esto sale dentro de un "
            f"contenedor, falta el montaje de solo lectura en /repo: mira los "
            f"`volumes` de docker-compose.override.yml y el paso `pytest` de "
            f"la CI. Si sale fuera, es que vive en el repositorio privado."
        )


# ---------------------------------------------------------------------------
# Cifras que se pueden contar
# ---------------------------------------------------------------------------


class TestElNumeroDeTests:
    def test_el_readme_dice_cuantos_hay(self):
        """«998 tests cubren todo lo anterior» cuando ya eran 1039. La cifra
        envejece con cada tanda, así que o se comprueba o miente."""
        _saltar_si_no_esta(README)
        declarado = re.search(r"\*\*(\d{3,5}) tests\*\* cubren", _texto(README))

        assert declarado, "el README ya no dice cuántos tests hay"
        assert int(declarado.group(1)) == _tests_reales(), (
            f"el README dice {declarado.group(1)} y hay {_tests_reales()}"
        )


def _tests_reales() -> int:
    """Los que cuenta **pytest**, preguntándoselo a pytest.

    El primer intento contaba `def test_` con expresiones regulares y daba
    **861 frente a 1039**: no ve las parametrizaciones ni los tests heredados
    de una clase base. Contar código leyéndolo con regex es aproximar, y aquí
    la cifra tiene que ser exacta porque se compara con una igualdad.
    """
    import subprocess
    import sys

    salida = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", str(TESTS)],
        capture_output=True, text=True, cwd=str(TESTS.parent), timeout=300,
    ).stdout
    encontrado = re.search(r"(\d+) tests? collected", salida)
    if not encontrado:
        pytest.skip("pytest no pudo recolectar (¿falta la base de datos?)")
    return int(encontrado.group(1))


class TestLosRecuentosDelCurriculo:
    """Las tablas de `curriculo/README.md` salen de contar los JSON."""

    @pytest.fixture(scope="class")
    def reales(self) -> dict[str, dict[str, int]]:
        import json

        datos = {}
        for carpeta in ("salida", "salida_cataluna", "salida_andalucia",
                        "salida_galicia", "salida_pais_vasco"):
            ruta = CURRICULO / carpeta
            if not ruta.exists():
                continue
            materias, criterios, saberes, ficheros = set(), 0, 0, 0
            for f in ruta.glob("*.json"):
                j = json.loads(f.read_text(encoding="utf-8"))
                materias.add(j["materia"])
                criterios += len(j["criterios_evaluacion"])
                saberes += sum(len(b["items"]) for b in j["saberes_basicos"])
                ficheros += 1
            datos[carpeta] = {
                "materias": len(materias), "bloques": ficheros,
                "criterios": criterios, "saberes": saberes,
            }
        return datos

    @pytest.mark.parametrize("carpeta, fila", [
        ("salida", "Ceuta y Melilla"),
        ("salida_cataluna", "Cataluña"),
        ("salida_andalucia", "Andalucía"),
        ("salida_galicia", "Galicia"),
        ("salida_pais_vasco", "País Vasco"),
    ])
    def test_la_tabla_cuadra_con_los_ficheros(self, reales, carpeta, fila):
        """Puse estas cifras de memoria la primera vez y tres de las cuatro de
        Ceuta estaban mal: 19 materias en vez de 22, 737 criterios en vez de
        752."""
        _saltar_si_no_esta(README_CURRICULO)
        if carpeta not in reales:
            pytest.skip(f"{carpeta} no está generada")

        linea = next(
            (l for l in _texto(README_CURRICULO).splitlines() if l.startswith(f"| {fila}")),
            None,
        )
        assert linea, f"no hay fila para {fila} en curriculo/README.md"

        numeros = [int(n) for n in re.findall(r"\|\s*(\d+)\s*(?=\|)", linea)]
        esperado = reales[carpeta]

        assert numeros == [
            esperado["materias"], esperado["bloques"],
            esperado["criterios"], esperado["saberes"],
        ], f"{fila}: el README dice {numeros} y los JSON dan {list(esperado.values())}"


class TestLasCadenasTraducidas:
    def test_el_readme_dice_cuantas_hay(self):
        _saltar_si_no_esta(README)
        # Desde `TESTS`, no desde `RAIZ`: los catálogos son parte de la
        # aplicación y viven en `/app/app/translations` dentro del contenedor.
        # Con `RAIZ / "api" / …` la ruta no existía allí y el test **se saltaba
        # en silencio**, así que la comprobación no se hacía nunca donde se
        # ejecuta la batería de verdad. Cuarta vez que este mismo despiste
        # rompe algo solo dentro de Docker.
        catalogo = TESTS.parent / "app" / "translations" / "es" / "LC_MESSAGES" / "messages.po"
        if not catalogo.exists():
            pytest.skip(f"no hay catálogos compilados en {catalogo.parent}")

        # Menos la cabecera, que es un `msgid ""` técnico.
        reales = _texto(catalogo).count("\nmsgid ") - 1
        declarado = re.search(r"(\d{3,4}) cadenas", _texto(README))

        assert declarado, "el README ya no dice cuántas cadenas hay"
        assert abs(int(declarado.group(1)) - reales) <= 1, (
            f"el README dice {declarado.group(1)} cadenas y el catálogo tiene {reales}"
        )


# ---------------------------------------------------------------------------
# Afirmaciones sobre ficheros que existen o no
# ---------------------------------------------------------------------------


class TestLaLicencia:
    """El caso que costó más caro: el README dijo un mes que estaba pendiente."""

    def test_existe_el_fichero_que_el_readme_anuncia(self):
        _saltar_si_no_esta(README)
        assert (RAIZ / "LICENSE").exists(), "el README enlaza un LICENSE que no está"
        assert (RAIZ / "LICENSE-DOCS").exists()

    def test_el_readme_nombra_la_licencia_que_hay(self):
        _saltar_si_no_esta(RAIZ / "LICENSE")
        cabecera = (RAIZ / "LICENSE").read_text(encoding="utf-8")[:200].upper()
        texto = _texto(README)

        if "AFFERO" in cabecera:
            assert "AGPL" in texto, "el LICENSE es AGPL y el README no lo dice"
        else:
            assert "AGPL" not in texto, "el README dice AGPL y el LICENSE no lo es"

    def test_la_hoja_de_ruta_dice_la_misma(self):
        """Estuvo diciendo GPL en tres sitios mientras el fichero era AGPL.

        SE SALTA DENTRO DEL CONTENEDOR, y es correcto: `docs/` vive en el
        repositorio privado `awebo_docs` y no se monta. **No se monta a
        propósito**: quien clone solo el repositorio público no lo tiene, y un
        volumen que apunta a un fichero inexistente hace que Docker cree un
        directorio vacío en su lugar — el test fallaría con un error
        desconcertante en vez de saltarse con un motivo.

        Así que esta comprobación corre fuera de Docker, donde `docs/` está al
        lado. Es el único de este fichero que no se ejecuta en la batería
        principal, y conviene tenerlo presente."""
        _saltar_si_no_esta(HOJA)
        cabecera = (RAIZ / "LICENSE").read_text(encoding="utf-8")[:200].upper()
        if "AFFERO" not in cabecera:
            pytest.skip("el LICENSE no es AGPL")

        # Una línea puede nombrar la GPL legítimamente si además cuenta el
        # cambio —«decidida GPL el 08/08 y cambiada a AGPL el 15/08»—. Lo que
        # no puede es afirmar GPL a secas, que es lo que decía en tres sitios
        # mientras el fichero era AGPL.
        sueltas = [
            l.strip() for l in _texto(HOJA).splitlines()
            if re.search(r"(?<!A)GPL-3\.0", l) and "AGPL" not in l
        ]

        assert sueltas == [], (
            "la hoja de ruta dice GPL-3.0 sin mencionar el cambio a AGPL:\n"
            + "\n".join(s[:120] for s in sueltas)
        )


class TestLoQueElReadmeDiceQueNoEsta:
    """Si algún día se versionan, el README deja de ser cierto."""

    def test_los_pdf_de_las_fuentes_siguen_fuera(self):
        _saltar_si_no_esta(RAIZ / ".gitignore")
        gitignore = _texto(RAIZ / ".gitignore")

        assert "/curriculo/fuentes/**/*.pdf" in gitignore

    def test_la_salida_del_extractor_si_esta(self):
        """Se decidió versionarla el 15/08 porque sin ella el repositorio no es
        reproducible: las fuentes no están."""
        _saltar_si_no_esta(RAIZ / ".gitignore")
        # `CURRICULO` y no `RAIZ / "curriculo"`: dentro del contenedor la raíz
        # es `/repo` —cuatro ficheros sueltos— y el currículo tiene su propio
        # punto de montaje. La constante existe justo para esto y en este test
        # se me pasó usarla; es la tercera vez que el mismo despiste rompe algo
        # solo dentro de Docker.
        assert (CURRICULO / "salida").exists()
        assert not re.search(r"^/curriculo/salida\*/\s*$", _texto(RAIZ / ".gitignore"), re.M)


class TestLosComandosQueDocumenta:
    """Un comando mal escrito en el README rompe la puesta en marcha ajena, y
    no lo detecta ningún test de la aplicación. Ya pasó: decía
    `flask --app app seed-roles`, que no existe."""

    @pytest.mark.parametrize("comando", ["seed all", "seed curriculo", "db upgrade"])
    def test_el_comando_del_readme_existe(self, comando):
        _saltar_si_no_esta(README)
        texto = _texto(README)
        assert f"flask {comando}" in texto, f"el README ya no documenta «flask {comando}»"

    def test_no_quedan_comandos_con_la_forma_vieja(self):
        """`flask --app app seed-roles` y compañía: la CLI usa grupos
        (`flask seed roles`), no comandos con guion."""
        _saltar_si_no_esta(README)
        malos = re.findall(r"flask (?:--app app )?seed-\w+", _texto(README))

        assert malos == [], f"comandos inexistentes en el README: {malos}"


class TestEsteFicheroFuncionaDentroDeDocker:
    """La batería se lanza con `docker compose exec api pytest`, y ahí dentro
    la raíz del repositorio **no existe**: la imagen solo copia `api/`.

    La primera versión de este fichero lo ignoró y nueve de sus catorce tests
    fallaron con `FileNotFoundError: '/README.md'` — habiendo pasado los
    catorce fuera. `test_configuracion.py` ya documentaba exactamente este
    problema en su docstring desde hacía días.
    """

    def test_sin_montaje_sube_desde_el_fichero(self, tmp_path):
        """Sin montaje se usa `parents[3]`: `tests/unit/x.py` → `tests/` →
        `api/` → raíz.

        **Fuera** de Docker eso es la raíz del repositorio y tiene un `api/`
        dentro. **Dentro** da `/`, que no tiene nada — y precisamente por eso
        existe el montaje en `/repo`. La primera versión de este test afirmaba
        lo primero sin más y fallaba en el contenedor: comprobaba que la rama
        de respaldo diera algo útil, cuando lo que hace es dar algo inútil, que
        es el motivo de que haya una alternativa."""
        raiz = _raiz(montados=tmp_path / "no-existe")

        assert raiz == Path(__file__).resolve().parents[3]
        if (raiz / "api").is_dir():
            # Fuera del contenedor se puede afinar más.
            assert (raiz / "api" / "tests").is_dir()

    def test_con_montaje_usa_el_montaje(self, tmp_path):
        """Dentro: los ficheros del repositorio están en `/repo`, y subir tres
        niveles desde `/app/tests/unit` daría `/`."""
        (tmp_path / "README.md").write_text("**1 tests** cubren", encoding="utf-8")

        assert _raiz(montados=tmp_path) == tmp_path

    def test_nadie_cuelga_de_la_raiz_lo_que_no_esta_ahi(self):
        """El despiste que rompió este fichero tres veces seguidas.

        Dentro del contenedor `RAIZ` es `/repo` —cuatro ficheros sueltos— y el
        currículo está en su propio punto de montaje. Escribir
        `RAIZ / "curriculo"` funciona fuera de Docker y falla dentro, que es el
        peor de los dos mundos: pasa cuando lo pruebas y falla cuando lo
        entregas.

        Para eso está `CURRICULO`. Este test comprueba que se use, porque
        acordarse no ha bastado.

        Se mira el **árbol sintáctico** y no el texto: la primera versión
        buscaba la cadena con `in` y se cazaba a sí misma, porque el patrón
        aparece en este docstring y en su propio filtro. Buscar código leyendo
        texto vuelve a fallar por lo mismo de siempre."""
        import ast

        # `curriculo` y `api` son los dos que no cuelgan de la raíz dentro del
        # contenedor. La primera versión solo miraba `curriculo`, y por eso no
        # vio que `RAIZ / "api" / "app" / "translations"` hacía que el test de
        # las cadenas traducidas se saltara siempre en Docker: media red no
        # atrapa la mitad de los casos, atrapa los que se le ocurrieron a quien
        # la puso.
        FUERA_DE_LA_RAIZ = {"curriculo", "api"}

        arbol = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        usos = [
            n.lineno for n in ast.walk(arbol)
            if isinstance(n, ast.BinOp)
            and isinstance(n.op, ast.Div)
            and isinstance(n.left, ast.Name) and n.left.id == "RAIZ"
            and isinstance(n.right, ast.Constant)
            and n.right.value in FUERA_DE_LA_RAIZ
        ]
        # La definición de `CURRICULO` sí puede nombrarlo: es su alternativa.
        definicion = next(
            n.lineno for n in ast.walk(arbol)
            if isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") == "CURRICULO" for t in n.targets)
        )

        assert [l for l in usos if l != definicion] == [], (
            f"líneas que usan RAIZ / 'curriculo' en vez de CURRICULO: "
            f"{[l for l in usos if l != definicion]}"
        )

    @pytest.mark.parametrize("fichero", FICHEROS_DEL_REPO)
    def test_cada_fichero_que_hace_falta_esta_montado(self, fichero):
        """Cada entrada de `FICHEROS_DEL_REPO` tiene que estar en los `volumes`
        del override **y** en el paso `pytest` de la CI. Si se añade uno aquí y
        se olvida allí, el test que lo use se saltará en silencio dentro del
        contenedor y nadie se enterará de que dejó de comprobarse."""
        override = MONTADOS / "docker-compose.override.yml"
        if not override.is_file():
            pytest.skip("fuera del contenedor no hay nada que comprobar")

        texto = override.read_text(encoding="utf-8")
        assert f"/repo/{fichero}:ro" in texto, (
            f"{fichero} se lee en este test pero no se monta en /repo"
        )
