"""Las cabeceras de seguridad, y que la CSP no sea decorativa.

QUÉ PROTEGE CADA UNA, EN UNA LÍNEA
-----------------------------------
* `script-src` sin `'unsafe-inline'` es **la que de verdad para un XSS**: un
  `<script>` inyectado no lleva el `nonce` de esta petición y no se ejecuta.
* `frame-ancestors 'none'` impide el clickjacking.
* `base-uri 'self'` impide que un `<base>` inyectado desvíe todas las rutas
  relativas —incluidas las de los scripts propios— a otro servidor.
* `form-action 'self'` impide que un formulario inyectado mande los datos del
  docente a un tercero.
* `X-Content-Type-Options: nosniff` impide que el navegador ejecute como script
  algo que se sirvió como texto.

EL FALLO QUE ESTOS TESTS PERSIGUEN
-----------------------------------
Una CSP mal casada no rompe nada visible en el servidor: la cabecera sale, el
navegador bloquea los scripts, y la aplicación deja de funcionar **solo en el
navegador**. Al revés también: basta un `'unsafe-inline'` de más para que la
cabecera siga ahí, la web funcione, y no proteja de nada.

Por eso lo que se comprueba no es que exista la cabecera, sino que **el `nonce`
de la cabecera es el mismo que el de los `<script>` de la página**. Es el par
que se desincroniza en silencio.
"""
from __future__ import annotations

import re

import pytest

# `RAIZ` y no `parents[3]`. Este fichero nació con `parents[3]`, que fuera de
# Docker da la raíz del repositorio y dentro del contenedor da `/`: los tres
# tests de configuración de abajo reventaron con `FileNotFoundError:
# '/docker-compose.yml'`.
#
# Lo que duele es que la solución llevaba escrita en `test_configuracion.py`
# desde antes, con su docstring contando este mismo fallo palabra por palabra
# — y es un fichero que edité ese mismo día. No había que inventar nada, solo
# mirar si el problema ya estaba resuelto.
from tests.unit.test_configuracion import RAIZ

#: Las que se ponen en toda respuesta, con su valor exacto.
CABECERAS_FIJAS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
}


def _directiva(csp: str, nombre: str) -> str:
    for trozo in csp.split(";"):
        trozo = trozo.strip()
        if trozo.startswith(nombre + " ") or trozo == nombre:
            return trozo
    return ""


class TestLasCabecerasFijas:
    @pytest.mark.parametrize("nombre,valor", sorted(CABECERAS_FIJAS.items()))
    def test_van_en_la_respuesta(self, client, nombre, valor):
        respuesta = client.get("/ayuda")

        assert respuesta.headers.get(nombre) == valor

    def test_tambien_en_las_respuestas_de_error(self, client):
        """Una página de error es HTML servido por la misma aplicación, así que
        necesita las mismas defensas. Se comprueba porque los manejadores de
        error son un camino aparte, fácil de dejar fuera."""
        respuesta = client.get("/una-ruta-que-no-existe")

        assert respuesta.status_code == 404
        assert respuesta.headers.get("Content-Security-Policy")
        assert respuesta.headers.get("X-Frame-Options") == "DENY"


class TestLaPoliticaDeContenidos:
    def test_va_en_la_respuesta(self, client):
        assert client.get("/ayuda").headers.get("Content-Security-Policy")

    def test_los_scripts_no_admiten_nada_en_linea(self):
        """La directiva que hace el trabajo. Con `'unsafe-inline'` la cabecera
        seguiría ahí, la web funcionaría igual, y un XSS pasaría entero."""
        from app.middleware import _CSP

        assert "'unsafe-inline'" not in _directiva(_CSP, "script-src")

    @pytest.mark.parametrize(
        "directiva",
        ["default-src", "object-src", "base-uri", "form-action", "frame-ancestors"],
    )
    def test_estan_las_directivas_que_cierran_puertas(self, directiva):
        from app.middleware import _CSP

        assert _directiva(_CSP, directiva), f"falta {directiva}"

    def test_los_estilos_en_linea_se_admiten_a_sabiendas(self):
        """No es un descuido: hay 22 atributos `style=` por las plantillas y un
        estilo en línea no ejecuta código. El test existe para que la concesión
        sea explícita y no se confunda con un olvido — y para que quien la
        quite algún día vea que estaba decidida."""
        from app.middleware import _CSP

        assert "'unsafe-inline'" in _directiva(_CSP, "style-src")


class TestElNonceCasaConLaPagina:
    """El par que se rompe en silencio.

    Si el `nonce` de la cabecera y el de los `<script>` dejan de coincidir, el
    servidor responde 200 tan tranquilo y el navegador no ejecuta una sola
    línea de JavaScript. Ningún test que solo mire la cabecera lo vería.
    """

    def test_el_de_la_cabecera_es_el_de_los_scripts(self, client):
        respuesta = client.get("/ayuda")
        html = respuesta.get_data(as_text=True)

        csp = respuesta.headers["Content-Security-Policy"]
        en_cabecera = re.search(r"'nonce-([^']+)'", csp)
        assert en_cabecera, "la CSP no lleva nonce"

        en_html = set(re.findall(r'<script nonce="([^"]+)"', html))
        assert en_html, "la página no tiene ningún <script> con nonce"
        assert en_html == {en_cabecera.group(1)}

    def test_cambia_en_cada_peticion(self, client):
        """Un `nonce` reutilizado no sirve para nada: bastaría con leer el de
        una página para firmar un script inyectado en la siguiente."""
        primero = client.get("/ayuda").headers["Content-Security-Policy"]
        segundo = client.get("/ayuda").headers["Content-Security-Policy"]

        assert primero != segundo

    def test_ningun_script_en_linea_se_queda_sin_nonce(self):
        """Uno que se olvide no da error en el servidor: deja de ejecutarse en
        el navegador, que es de las cosas más caras de diagnosticar."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2] / "app" / "templates"
        culpables = [
            str(f.relative_to(raiz))
            for f in raiz.rglob("*.html")
            # El del PDF no lo sirve un navegador: lo pinta WeasyPrint.
            if "exportacion" not in str(f) and "<script>" in f.read_text(encoding="utf-8")
        ]

        assert not culpables, f"<script> sin nonce en {culpables}"


class TestNingunAtributoDeEvento:
    def test_no_queda_ningun_on_algo_en_las_plantillas(self):
        """Una CSP con `nonce` prohíbe los atributos de evento en línea, porque
        no hay forma de firmar el código que vive dentro de un atributo.

        Había uno solo en toda la aplicación —`onchange="this.form.submit()"`
        en el selector de idioma— y se mudó a un `addEventListener` en
        `app.js`. Este test impide que vuelva a aparecer otro, que es la clase
        de cosa que se escribe sin pensar y rompe el selector sin avisar.
        """
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2] / "app" / "templates"
        # Los `on*` de HTML son atributos de una etiqueta, así que van
        # precedidos de un espacio y seguidos de `="`.
        patron = re.compile(r'\son[a-z]+\s*=\s*"')
        culpables = [
            str(f.relative_to(raiz))
            for f in raiz.rglob("*.html")
            if patron.search(f.read_text(encoding="utf-8"))
        ]

        assert not culpables, (
            f"atributos de evento en línea en {culpables}: la CSP los bloquea. "
            "Conéctalo con addEventListener en un fichero .js."
        )


class TestLosPuertosNoSalenAInternet:
    """Postgres y Adminer, atados a loopback.

    `5433:5432` en un `docker-compose` publica el puerto en **todas** las
    interfaces, así que en un servidor público deja la base de datos escuchando
    en Internet. Y Adminer es un panel de administración de esa base de datos
    sin autenticación propia: publicarlo es publicarla a ella.
    """

    @pytest.mark.parametrize("servicio", ["POSTGRES_PORT", "ADMINER_PORT"])
    def test_van_atados_a_127_0_0_1(self, servicio):
        compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")

        publicaciones = re.findall(rf'"([^"]*\$\{{{servicio}[^"]*)"', compose)
        assert publicaciones, f"no se encuentra la publicación de {servicio}"
        for p in publicaciones:
            assert p.startswith("127.0.0.1:"), (
                f"{servicio} se publica como «{p}», en todas las interfaces"
            )


class TestNginxNoSeAnuncia:
    def test_server_tokens_esta_apagado(self):
        """Por sí solo no para nada —quien quiera atacar prueba los exploits
        igual—, pero evita salir en los buscadores de servidores vulnerables el
        día que se publique un fallo de esta versión, que es por donde llega la
        mayoría del tráfico automatizado."""
        conf = (RAIZ / "nginx" / "nginx.conf").read_text(encoding="utf-8")

        assert re.search(r"^\s*server_tokens\s+off\s*;", conf, re.M)
