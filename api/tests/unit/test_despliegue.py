"""La configuración de producción: TLS, y que no se separe de la de desarrollo.

QUÉ VIGILA ESTO Y QUÉ NO
-------------------------
No comprueba que un servidor esté bien desplegado —eso no se puede hacer desde
aquí, y para eso está la lista de `DESPLIEGUE.md`—. Comprueba la clase de
fallo que sí se puede atrapar leyendo ficheros: **que la configuración de
producción prometa algo que no cumple**.

Y hay una razón concreta para insistir: la configuración de producción no la
ejercita nadie. La batería corre contra el stack de desarrollo, la CI también,
y `nginx/prod.conf.template` solo se estrena el día del despliegue. Un fallo
ahí no se descubre hasta que hay usuarios delante.

EL RIESGO DE TENER DOS FICHEROS DE NGINX
-----------------------------------------
`nginx.conf` (desarrollo, HTTP) y `prod.conf.template` (producción, TLS) están
separados porque nginx no arranca si un `ssl_certificate` apunta a un fichero
que no existe, y en local no hay certificado. El precio de esa separación es
que pueden divergir, así que aquí se exige que lo que comparten esté en los
dos.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.unit.test_configuracion import RAIZ

NGINX_DEV = RAIZ / "nginx" / "nginx.conf"
NGINX_PROD = RAIZ / "nginx" / "prod.conf.template"
COMPOSE_PROD = RAIZ / "docker-compose.prod.yml"
#: En la raiz del repositorio PUBLICO y no en `docs/`, que es el privado.
#: Se escribio alli primero y habria roto la CI sin decir por que:
#: `actions/checkout` solo trae el repositorio publico, asi que `docs/` no
#: existe en ese entorno y estos tests no habrian encontrado el fichero.
#:
#: Ademas es el sitio que le corresponde: una guia de despliegue de un
#: proyecto AGPL no tiene nada que ocultar —los secretos van como marcadores de
#: posicion— y es justo lo que alguien espera encontrar en el repositorio.
DESPLIEGUE = RAIZ / "DESPLIEGUE.md"


def _prod() -> str:
    return NGINX_PROD.read_text(encoding="utf-8")


def _compose_prod() -> dict:
    return yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))


class TestLoQueCompartenLosDosNginx:
    @pytest.mark.parametrize("regla", ["server_tokens off"])
    def test_esta_en_los_dos_ficheros(self, regla):
        """Lo que se pone en uno y se olvida en el otro es el modo de fallo de
        tener dos configuraciones."""
        for fichero in (NGINX_DEV, NGINX_PROD):
            texto = fichero.read_text(encoding="utf-8")
            assert re.search(rf"^\s*{re.escape(regla)}\s*;", texto, re.M), (
                f"falta «{regla}» en {fichero.name}"
            )

    def test_los_dos_pasan_x_forwarded_proto(self):
        """Sin esta cabecera la aplicación cree que la conexión es HTTP, y con
        `ProxyFix` puesto eso afecta a cómo se construyen las URL."""
        for fichero in (NGINX_DEV, NGINX_PROD):
            assert "X-Forwarded-Proto" in fichero.read_text(encoding="utf-8")


class TestElTLS:
    def test_el_puerto_80_redirige(self):
        assert re.search(r"return\s+301\s+https://", _prod())

    def test_el_desafio_de_certbot_no_se_redirige(self):
        """La renovación viaja por HTTP. Si el 80 redirige **todo**, falla —y no
        el día que se configura, sino a los 60, que es cuando ya nadie lo
        relaciona con esto."""
        prod = _prod()
        acme = prod.find("/.well-known/acme-challenge/")
        redireccion = prod.find("return 301")

        assert acme != -1, "no hay location para el desafío ACME"
        assert acme < redireccion, (
            "el desafío ACME tiene que ir ANTES de la redirección, o nginx "
            "resolverá primero el `location /` y la renovación fallará"
        )

    def test_solo_tls_moderno(self):
        assert re.search(r"ssl_protocols\s+TLSv1\.2\s+TLSv1\.3\s*;", _prod())
        for viejo in ("TLSv1;", "TLSv1.1", "SSLv3"):
            assert viejo not in _prod()


class TestHSTS:
    def test_va_con_always(self):
        """Sin `always`, nginx no la pone en las respuestas de error — que son
        justo las que un atacante puede provocar."""
        assert re.search(
            r"add_header\s+Strict-Transport-Security[^;]*always\s*;", _prod()
        )

    def test_no_esta_en_la_configuracion_de_desarrollo(self):
        """Sobre HTTP el navegador la ignora, así que ponerla ahí solo sirve
        para que el día que haya certificado nadie recuerde por qué está."""
        assert "Strict-Transport-Security" not in NGINX_DEV.read_text(encoding="utf-8")

    def test_empieza_con_un_plazo_corto(self):
        """HSTS **no se puede deshacer desde el servidor**: quien la recibió la
        respeta hasta que caduque, y si el certificado se rompe esos visitantes
        no pueden entrar.

        Por eso sale con `max-age=300` y se sube a mano cuando lleve unos días
        funcionando. Este test se cambia **a la vez** que la plantilla, y ese es
        el punto: que subirlo sea una decisión y no un descuido."""
        plazo = re.search(r"max-age=(\d+)", _prod())

        assert plazo, "la cabecera HSTS no lleva max-age"
        assert int(plazo.group(1)) <= 300, (
            "el plazo ha subido. Si es a propósito —y el sitio lleva días con "
            "el certificado estable—, actualiza también este test; si no, "
            "revisa DESPLIEGUE.md § 6 antes de dejarlo."
        )

    def test_sin_preload_ni_subdominios(self):
        """`preload` entra en una lista compilada dentro de los navegadores y
        es prácticamente irreversible; `includeSubDomains` obliga a que todos
        los subdominios tengan HTTPS para siempre. Ninguna de las dos se pone
        sin decidirlo."""
        # El VALOR entrecomillado, no `[^;]*`. La primera versión cortaba en el
        # primer `;` y `preload` va justo detrás de uno —«max-age=…; preload»—,
        # así que el test pasaba con la cabecera que pretendía prohibir.
        # Comprobado: reponiendo `preload` ahora sale en rojo.
        valor = re.search(
            r'add_header\s+Strict-Transport-Security\s+"([^"]*)"', _prod()
        )

        assert valor, "no se reconoce la cabecera HSTS"
        assert "preload" not in valor.group(1)
        assert "includeSubDomains" not in valor.group(1)


class TestElComposeDeProduccion:
    def test_adminer_no_arranca(self):
        """Adminer es un panel de administración de la base de datos **sin
        autenticación propia**: quien llega a él, llega a la base de datos."""
        adminer = _compose_prod()["services"]["adminer"]

        assert adminer.get("profiles"), (
            "adminer tiene que quedar detrás de un perfil que nadie active. "
            "Borrar el servicio no vale: Compose fusiona y no sustituye."
        )

    def test_nginx_publica_los_dos_puertos_estandar(self):
        puertos = _compose_prod()["services"]["nginx"]["ports"]

        assert "80:80" in puertos and "443:443" in puertos

    def test_ningun_otro_servicio_publica_puertos(self):
        """Lo único que debe verse desde fuera es nginx."""
        culpables = [
            nombre
            for nombre, servicio in _compose_prod()["services"].items()
            if nombre != "nginx" and servicio.get("ports")
        ]

        assert not culpables, f"{culpables} publican puertos en producción"

    def test_el_codigo_no_se_monta_desde_el_disco(self):
        """En desarrollo se monta `./api:/app` para recargar en caliente. En
        producción eso significaría servir lo que haya en el disco del servidor
        en vez de lo que se construyó y se probó."""
        for nombre in ("api", "worker", "beat"):
            montajes = _compose_prod()["services"][nombre].get("volumes") or []
            assert not any(str(m).startswith("./api:") for m in montajes), (
                f"{nombre} monta el código desde el disco"
            )

    def test_la_api_declara_que_hay_un_proxy_delante(self):
        """Sin esto, los límites por IP de los endpoints anónimos se comparten
        entre todos los visitantes: cinco intentos fallidos de cualquiera
        dejarían sin entrar a todo el mundo."""
        entorno = _compose_prod()["services"]["api"]["environment"]

        assert str(entorno.get("PROXIES_DELANTE")) == "1"


def _fuente(modulo) -> str:
    """El código de un módulo de la aplicación, localizado por el módulo.

    Y no componiendo una ruta desde `RAIZ`, que es la trampa que
    `test_configuracion.py` ya deja escrita: **`RAIZ` sirve para lo que NO
    forma parte de la aplicación, y para nada más**. `app/__init__.py` sí
    forma parte, así que está donde esté la aplicación —en el repositorio
    fuera de Docker, en `/app` dentro—, y `RAIZ / "api" / "app"` daría
    `/repo/api/app`, que no existe.
    """
    return Path(modulo.__file__).read_text(encoding="utf-8")


class TestElProxyFix:
    def test_por_defecto_no_se_confia_en_ningun_proxy(self):
        """El riesgo no es simétrico. Olvidarlo detrás de un proxy degrada el
        límite a un cubo compartido —molesto pero acotado—; ponerlo cuando NO
        hay proxy deja que cualquiera mande su propia `X-Forwarded-For` y se
        salte los límites inventándose una IP por petición.

        Se mira el **valor por defecto en el código** y no `Config.PROXIES_DELANTE`,
        porque eso último trae lo que diga el entorno de quien lanza la
        batería: en el contenedor de desarrollo vale 1, y el test pasaría o no
        según dónde se ejecute.
        """
        from app import config as modulo

        defecto = re.search(
            r'PROXIES_DELANTE[^=]*=\s*int\(os\.environ\.get\("PROXIES_DELANTE"\)\s*or\s*(\d+)\)',
            _fuente(modulo),
        )

        assert defecto, "no se reconoce cómo se lee PROXIES_DELANTE en config.py"
        assert defecto.group(1) == "0"

    def test_no_se_confia_en_el_host_que_manda_el_cliente(self):
        """`X-Forwarded-Host` lo usa Flask para construir URL absolutas, y
        aceptarlo de fuera abre envenenamiento de enlaces: el de restablecer
        contraseña saldría apuntando al servidor del atacante."""
        import app as modulo

        codigo = _fuente(modulo)

        assert "x_host=0" in codigo and "x_prefix=0" in codigo


class TestElDocumentoDeDespliegue:
    def test_existe(self):
        """Sin él no hay forma de comprobar que el servidor quedó como se
        quería, que es el hueco por el que se cuela un `SECRET_KEY` sin
        definir."""
        assert DESPLIEGUE.is_file()

    def test_avisa_de_que_hay_que_nombrar_los_dos_ficheros(self):
        """Compose carga el override de desarrollo si no se nombra ninguno. En
        el servidor eso es levantar el stack de desarrollo contra la base de
        datos de producción."""
        texto = DESPLIEGUE.read_text(encoding="utf-8")

        assert "-f docker-compose.yml -f docker-compose.prod.yml" in texto

    def test_lleva_lista_de_comprobacion(self):
        texto = DESPLIEGUE.read_text(encoding="utf-8")

        assert texto.count("- [ ]") >= 10, (
            "la lista de comprobación es la parte que de verdad hace falta"
        )
