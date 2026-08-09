"""Que las variables de configuración lleguen de verdad a los contenedores.

EL FALLO QUE PUSO ESTE FICHERO (09/08/2026)
--------------------------------------------
Con ``CORREO_PROVEEDOR=smtp`` escrito en el ``.env``, la aplicación seguía
usando el proveedor de consola. La causa: ``docker-compose.yml`` enumera una
por una las variables que pasa a cada servicio, y esa no estaba en la lista.

El ``.env`` lo lee Compose para sustituir ``${...}`` **dentro de los ficheros
de compose**; no se inyecta en los contenedores. Una variable ausente de la
lista simplemente no existe dentro de la aplicación, y como ``config.py`` tiene
valor por defecto para todo, el síntoma es que el defecto se aplica en
silencio. No hay error, no hay aviso: solo un comportamiento que no es el que
pone en el fichero de configuración.

No era solo el correo. Cuando se midió, faltaban también ``LOG_LEVEL``,
``LOG_JSON``, ``RATELIMIT_ENABLED``, ``RATELIMIT_DEFAULT``,
``RATELIMIT_STORAGE_URI``, ``CORS_ORIGINS``, ``OPENAI_TIMEOUT`` y ``URL_BASE``.
Ninguna había dado la cara.

EL INVARIANTE
-------------
Toda variable que el ``.env.example`` promete **y** que ``config.py`` lee tiene
que aparecer en el entorno de ``api`` y de ``worker``.

Se toma el ``.env.example`` como fuente y no la lista de ``config.py`` entera
porque el ``.env.example`` es lo que se le enseña a quien despliega: lo que
figura ahí es una promesa de que ponerlo sirve para algo. Y se comprueba contra
los dos servicios porque hacen cosas distintas con la misma configuración —el
envío de correo ocurre en el worker, no en la api—, así que una variable puesta
solo en uno de los dos deja un agujero que además es intermitente.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Import normal y no `pytest.importorskip`. Con `importorskip`, la primera vez
# que se lanzó la batería en Docker el fichero entero se saltó —a la imagen le
# faltaba PyYAML, que aún no se había reconstruido— y en la salida solo quedó
# un discreto «1 skipped» sin nombre. Un test que puede desaparecer sin decir
# de cuál se trata no vigila nada: si falta la dependencia, que sea un error.
import yaml


#: Dónde se montan los ficheros del repositorio dentro del contenedor. Es
#: parámetro y no constante empotrada para poder ejercitar las dos ramas de
#: `_raiz()` desde un test: `/` no es escribible en un entorno normal, así que
#: sin esto la rama del contenedor solo se comprobaría ejecutando la batería
#: dentro de Docker, que es justo donde falló la primera versión.
MONTADOS = Path("/repo")

#: Lo único que se lee de `RAIZ`. Son los ficheros que NO forman parte de la
#: aplicación y que por tanto faltan dentro del contenedor, así que son
#: exactamente los que hay que montar. Cualquier cosa que se añada aquí hay
#: que añadirla también a los `volumes` del override y al paso de la CI.
FICHEROS_DEL_REPO = (
    "docker-compose.yml",
    "docker-compose.override.yml",
    ".env.example",
)


def _raiz(montados: Path | None = None) -> Path:
    """Dónde encontrar los ficheros de compose y el `.env.example`.

    Fuera de Docker es la raíz del repositorio: `tests/unit/x.py` → `tests/` →
    `api/` → raíz. Pero la batería se lanza normalmente **dentro** del
    contenedor, donde la aplicación vive en `/app` y esos ficheros no existen:
    la imagen solo copia `api/`, y subir a tres niveles desde `/app/tests/unit`
    da `/`. Por eso se montan de solo lectura en `/repo`, tanto en
    `docker-compose.override.yml` como en el workflow de la CI, que también
    monta únicamente `api/`.
    """
    # `MONTADOS` se consulta aquí dentro y no como valor por defecto del
    # parámetro: los valores por defecto se evalúan al DEFINIR la función, así
    # que `def _raiz(montados=MONTADOS)` congela la constante y reasignarla
    # después no tiene ningún efecto. Con esa versión, el arnés que escribí
    # para simular el contenedor no simulaba nada y daba verde igualmente.
    montados = MONTADOS if montados is None else montados

    if (montados / "docker-compose.yml").is_file():
        return montados
    return Path(__file__).resolve().parents[3]


RAIZ = _raiz()

#: Servicios que ejecutan la aplicación. `beat` queda fuera a propósito: solo
#: dispara tareas programadas y no lee configuración de negocio. Si algún día
#: una tarea programada manda correo, hay que añadirlo aquí.
SERVICIOS = ("api", "worker")


def _cargar(nombre: str) -> dict:
    ruta = RAIZ / nombre
    assert ruta.is_file(), (
        f"no está {ruta}. Si esto sale dentro de un contenedor, falta el "
        f"montaje de solo lectura en /repo: mira los `volumes` de "
        f"docker-compose.override.yml y el paso `pytest` de la CI."
    )
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def _entorno(servicio: str) -> dict:
    """Entorno efectivo del servicio: el base más lo que añade el override.

    Se fusionan a mano en vez de llamar a `docker compose config` porque los
    tests corren en CI sin Docker.
    """
    base = _cargar("docker-compose.yml")["services"][servicio].get("environment") or {}
    extra = (_cargar("docker-compose.override.yml")["services"]
             .get(servicio, {}).get("environment") or {})
    assert isinstance(base, dict) and isinstance(extra, dict), (
        "los dos ficheros deben usar la sintaxis de mapa para `environment`. "
        "Mezclar mapa y lista hace que Compose sustituya en lugar de fusionar, "
        "y entonces el override borraría variables del fichero base."
    )
    return {**base, **extra}


def _variables_del_ejemplo() -> set[str]:
    texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
    return {m.group(1) for m in re.finditer(r"^([A-Z0-9_]+)=", texto, re.M)}


def _variables_que_lee_config() -> set[str]:
    """Las variables de entorno que `app/config.py` consulta.

    Se localiza importando el módulo, no componiendo una ruta desde `RAIZ`.
    `config.py` es parte de la aplicación y por tanto está siempre donde esté
    la aplicación: en el repositorio si se lanza fuera, en `/app` dentro del
    contenedor. Construir `RAIZ / "api" / "app" / "config.py"` daba
    `/repo/api/app/config.py`, que no existe: bajo `/repo` solo hay los tres
    ficheros del repositorio que sí faltan en la imagen.

    Es la distinción que costó tres intentos: `RAIZ` sirve para lo que NO
    forma parte de la aplicación, y para nada más.
    """
    from app import config as modulo

    texto = Path(modulo.__file__).read_text(encoding="utf-8")
    return set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z0-9_]+)["\']', texto))


@pytest.mark.parametrize("servicio", SERVICIOS)
def test_lo_que_promete_el_env_example_llega_al_contenedor(servicio):
    """El test que habría ahorrado la tarde del buzón de correo."""
    prometidas = _variables_del_ejemplo() & _variables_que_lee_config()
    assert prometidas, "el detector no encontró ninguna variable: revísalo"

    faltan = sorted(prometidas - set(_entorno(servicio)))
    assert not faltan, (
        f"{servicio} no recibe {faltan}. Están en .env.example y config.py las "
        f"lee, pero docker-compose.yml no las reenvía: dentro del contenedor "
        f"se usará el valor por defecto sin decir nada."
    )


def test_estan_los_ficheros_del_repositorio():
    """Un fallo claro en vez de tres `FileNotFoundError` sueltos.

    Cuando faltaba el montaje, el error salía dentro de cada test y señalaba
    un fichero distinto cada vez, lo que hacía parecer tres problemas donde
    había uno. Esto lo dice una sola vez y con la solución.
    """
    faltan = [f for f in FICHEROS_DEL_REPO if not (RAIZ / f).is_file()]
    assert not faltan, (
        f"no se encuentran {faltan} bajo {RAIZ}. Dentro de un contenedor se "
        f"montan en /repo: revisa los `volumes` de "
        f"docker-compose.override.yml y el paso `pytest` de la CI."
    )


def test_se_prefieren_los_ficheros_montados_cuando_existen(tmp_path):
    """Las dos ramas de `_raiz()`, ejercitadas.

    La primera versión de este fichero subía tres niveles y ya está. Fuera de
    Docker daba la raíz del repositorio y todo pasaba; dentro del contenedor la
    aplicación vive en `/app`, tres niveles arriba es `/`, y los tres tests
    reventaron con `FileNotFoundError: '/.env.example'`. La rama que fallaba
    era justo la que no se había ejecutado nunca.
    """
    montados = tmp_path / "repo"
    montados.mkdir()
    (montados / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    assert _raiz(montados) == montados

    # Y sin ellos, se cae a la raíz del repositorio.
    assert _raiz(tmp_path / "no-existe") == Path(__file__).resolve().parents[3]


def test_config_lee_el_correo_donde_se_envia():
    """El envío ocurre en el worker, no en la api.

    Configurarlo solo en la api deja el buzón vacío y el fallo únicamente en el
    log del worker, que no es donde se mira primero.
    """
    for variable in ("CORREO_PROVEEDOR", "SMTP_HOST"):
        assert variable in _entorno("worker"), (
            f"{variable} no llega al worker, que es quien manda el correo"
        )


def test_el_puerto_vacio_no_tumba_el_arranque():
    """`SMTP_PORT=` en el .env es una variable declarada y vacía.

    `os.environ.get("SMTP_PORT", "587")` devuelve `""` en ese caso —el valor
    por defecto solo se usa si la variable NO existe—, e `int("")` revienta con
    un ValueError que no menciona el .env por ningún lado.
    """
    import os
    from importlib import reload

    from app import config as modulo

    previo = os.environ.get("SMTP_PORT")
    os.environ["SMTP_PORT"] = ""
    try:
        reload(modulo)
        assert modulo.Config.SMTP_PORT == 587
    finally:
        if previo is None:
            os.environ.pop("SMTP_PORT", None)
        else:
            os.environ["SMTP_PORT"] = previo
        reload(modulo)
