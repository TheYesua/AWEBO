"""El proceso no arranca con un secreto que cualquiera puede leer.

EL FALLO QUE PUSO ESTO, QUE NO NECESITABA NINGÚN ATAQUE
--------------------------------------------------------
Hasta el 21/09/2026, `config.py` decía::

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    FLASK_ENV  = os.environ.get("FLASK_ENV", "production")

Las dos líneas por separado parecen razonables. Juntas significan que
**olvidar una variable de entorno arranca el servidor en silencio** firmando
con una clave escrita en un repositorio AGPL público.

Y esa clave firma dos cosas, no una: la cookie de sesión —se falsifica la
sesión de cualquiera— y, en `services/tokens.py`, los enlaces de restablecer
contraseña y verificar correo, emitidos con la misma clave y un `salt` por
propósito. Con ella se emite un enlace válido de cambio de contraseña para
cualquier cuenta.

POR QUÉ LOS TESTS VAN EN DOS NIVELES
-------------------------------------
Los de `TestLaComprobacion` llaman a la función con un diccionario: son
baratos y cubren cada caso. Pero una función perfecta que nadie llama no
protege de nada, y ese es justo el tipo de fallo que este proyecto se ha
encontrado ya —una columna que se guardaba y no pintaba nadie—. Por eso
`TestQueDeVerasEstaCableada` levanta la aplicación de verdad y exige que
`create_app` se niegue.
"""
from __future__ import annotations

import pytest

from app import create_app
from app.config import Config
from app.secretos import (
    CLAVES_PUBLICADAS,
    CREDENCIALES_BD_PUBLICADAS,
    LONGITUD_MINIMA_SECRET_KEY,
    ConfiguracionInsegura,
    comprobar_configuracion,
)

#: Una clave que pasa todas las comprobaciones, para aislar el caso de cada
#: test. Se deriva del mínimo en vez de escribirse con una longitud fija: si
#: algún día sube el mínimo, esta sube con él en vez de romper los tests por
#: un motivo que no tiene nada que ver con lo que miden.
CLAVE_BUENA = "a" * LONGITUD_MINIMA_SECRET_KEY


def _config(**cambios):
    """Configuración de producción válida, con los cambios que pida el test."""
    base = {
        "TESTING": False,
        "FLASK_ENV": "production",
        "SECRET_KEY": CLAVE_BUENA,
        "SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://real:secreta@postgres:5432/awebo",
    }
    base.update(cambios)
    return base


class TestLaComprobacion:
    def test_una_configuracion_buena_pasa(self):
        """El control negativo. Sin él, un test que exige excepciones pasaría
        también con una función que lanza siempre."""
        comprobar_configuracion(_config())

    def test_sin_secret_key_no_arranca(self):
        with pytest.raises(ConfiguracionInsegura) as exc:
            comprobar_configuracion(_config(SECRET_KEY=""))

        assert "SECRET_KEY" in str(exc.value)

    @pytest.mark.parametrize("clave", sorted(CLAVES_PUBLICADAS))
    def test_las_claves_publicadas_no_arrancan(self, clave):
        """Parametrizado sobre la propia lista: el día que se añada un valor
        conocido, su test aparece solo."""
        with pytest.raises(ConfiguracionInsegura):
            comprobar_configuracion(_config(SECRET_KEY=clave))

    def test_una_clave_corta_no_arranca(self):
        corta = "a" * (LONGITUD_MINIMA_SECRET_KEY - 1)

        with pytest.raises(ConfiguracionInsegura) as exc:
            comprobar_configuracion(_config(SECRET_KEY=corta))

        assert str(LONGITUD_MINIMA_SECRET_KEY) in str(exc.value)

    def test_la_del_ejemplo_esta_en_la_lista(self):
        """`.env.example` es lo que copia quien despliega por primera vez, así
        que su marcador de posición es un valor que llega a producción de
        verdad. Se comprueba aquí para que quitarlo de la lista sin quitarlo
        del fichero ponga el test en rojo."""
        assert "cambia-esto-por-una-clave-aleatoria-larga" in CLAVES_PUBLICADAS

    def test_el_valor_que_estuvo_en_config_sigue_vigilado(self):
        """El que causó todo esto. Está aquí por su nombre para que nadie lo
        borre de la lista pensando que ya no existe: precisamente porque ya no
        está en el código, es el que alguien podría reponer «temporalmente»."""
        assert "dev-key-change-me" in CLAVES_PUBLICADAS

    @pytest.mark.parametrize("credencial", CREDENCIALES_BD_PUBLICADAS)
    def test_las_credenciales_de_ejemplo_de_la_bd_no_arrancan(self, credencial):
        uri = f"postgresql+psycopg://{credencial}@postgres:5432/awebo"

        with pytest.raises(ConfiguracionInsegura):
            comprobar_configuracion(_config(SQLALCHEMY_DATABASE_URI=uri))


class TestDondeLaComprobacionSeCalla:
    """Dos salidas, y las dos son deliberadas."""

    def test_en_los_tests_no_estorba(self):
        """`TestConfig` fija su propia clave y lo que se prueba no es el
        despliegue."""
        comprobar_configuracion(_config(TESTING=True, SECRET_KEY="corta"))

    def test_en_desarrollo_no_estorba(self):
        """Levantar el stack en local no puede exigir ceremonia, o se acaba
        desactivando la guarda entera."""
        comprobar_configuracion(
            _config(FLASK_ENV="development", SECRET_KEY="dev-key-change-me")
        )


class TestQueDeVerasEstaCableada:
    """Que `create_app` la llame, y no solo que la función exista.

    No hacen falta ni base de datos ni Redis: la comprobación va justo después
    de cargar la configuración, así que revienta antes de que se construya
    nada. Si algún día alguien la mueve más abajo, estos tests empezarán a
    pedir servicios y se notará — que es la señal que se quiere.
    """

    def test_create_app_se_niega_con_una_clave_publicada(self):
        class ConfigMala(Config):
            TESTING = False
            FLASK_ENV = "production"
            SECRET_KEY = "dev-key-change-me"

        with pytest.raises(ConfiguracionInsegura):
            create_app(ConfigMala)

    def test_create_app_se_niega_sin_clave(self):
        class ConfigSinClave(Config):
            TESTING = False
            FLASK_ENV = "production"
            SECRET_KEY = ""

        with pytest.raises(ConfiguracionInsegura):
            create_app(ConfigSinClave)


class TestElCodigoYaNoLlevaLaClave:
    def test_config_no_trae_ninguna_clave_por_defecto(self):
        """La medida de seguridad es la **ausencia** del valor por defecto, no
        solo la comprobación. Mientras `Config` traiga una clave usable, basta
        con que alguien mueva o desactive la guarda para volver al punto de
        partida."""
        por_defecto = Config.SECRET_KEY

        # Puede traer la del entorno de quien lanza la batería, que es legítima
        # y no se conoce aquí. Lo que no puede traer es una publicada.
        assert por_defecto not in CLAVES_PUBLICADAS
