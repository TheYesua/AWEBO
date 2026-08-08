"""Tests de la resolución del tema visual y del contraste de las paletas.

Dos bloques con propósitos distintos:

* ``TestResolucion`` fija el contrato del servidor: al HTML llega siempre un
  tema concreto, nunca ``auto``. De eso depende que el CSS defina la paleta
  oscura una sola vez y que no haya destello al navegar.
* ``TestContraste`` lee ``styles.css`` y comprueba los ratios reales. Es la
  única forma de que la promesa de WCAG 2.1 AA siga siendo cierta cuando
  alguien retoque un tono dentro de seis meses.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.temas import (
    COOKIE_TEMA,
    COOKIE_TEMA_SISTEMA,
    resolver_tema,
    tema_elegido,
)


CSS = Path(__file__).resolve().parents[2] / "app" / "static" / "css" / "styles.css"


# ---------------------------------------------------------------------------
# Resolución en servidor
# ---------------------------------------------------------------------------


class TestResolucion:
    @pytest.mark.parametrize(
        "cookies, esperado",
        [
            ({}, "claro"),                                          # primera visita
            ({COOKIE_TEMA: "claro"}, "claro"),
            ({COOKIE_TEMA: "oscuro"}, "oscuro"),
            # "auto" delega en lo que informó el navegador
            ({COOKIE_TEMA: "auto", COOKIE_TEMA_SISTEMA: "oscuro"}, "oscuro"),
            ({COOKIE_TEMA: "auto", COOKIE_TEMA_SISTEMA: "claro"}, "claro"),
            # auto sin dato del sistema (sin JS): se comporta como claro
            ({COOKIE_TEMA: "auto"}, "claro"),
            # una elección explícita ignora la preferencia del sistema
            ({COOKIE_TEMA: "claro", COOKIE_TEMA_SISTEMA: "oscuro"}, "claro"),
            ({COOKIE_TEMA: "oscuro", COOKIE_TEMA_SISTEMA: "claro"}, "oscuro"),
            # valores corruptos o manipulados no deben romper nada
            ({COOKIE_TEMA: "<script>"}, "claro"),
            ({COOKIE_TEMA: "auto", COOKIE_TEMA_SISTEMA: "morado"}, "claro"),
            ({COOKIE_TEMA: ""}, "claro"),
        ],
    )
    def test_resolucion(self, app, cookies, esperado):
        with app.test_request_context("/", headers={
            "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())
        }):
            assert resolver_tema() == esperado

    def test_nunca_devuelve_auto(self, app):
        """El contrato del que depende todo lo demás."""
        for valor in ("auto", "claro", "oscuro", "basura", ""):
            with app.test_request_context("/", headers={"Cookie": f"tema={valor}"}):
                assert resolver_tema() in ("claro", "oscuro")

    def test_el_selector_si_distingue_auto(self, app):
        """El HTML recibe el tema resuelto, pero el selector marca la elección."""
        with app.test_request_context("/", headers={"Cookie": "tema=auto"}):
            assert tema_elegido() == "auto"


class TestPlantilla:
    """Comprobaciones de extremo a extremo sobre el HTML renderizado.

    Las cookies se ponen con ``client.set_cookie`` y no con una cabecera
    ``Cookie`` manual: el cliente de pruebas de Werkzeug mantiene su propio
    tarro de cookies y genera esa cabecera él mismo, así que una puesta a mano
    se pierde silenciosamente — la petición sale sin cookies y el test pasa o
    falla por el motivo equivocado.
    """

    def test_el_html_lleva_el_tema_resuelto(self, client, db):
        client.set_cookie("tema", "oscuro")
        res = client.get("/login")
        assert b'data-tema="oscuro"' in res.data

    def test_sin_cookies_el_html_es_claro(self, client, db):
        res = client.get("/login")
        assert b'data-tema="claro"' in res.data

    def test_auto_se_resuelve_antes_de_renderizar(self, client, db):
        """Si 'auto' llegara al HTML, el CSS no sabría qué paleta aplicar."""
        client.set_cookie("tema", "auto")
        client.set_cookie("tema_sistema", "oscuro")
        res = client.get("/login")
        assert b'data-tema="oscuro"' in res.data
        assert b'data-tema="auto"' not in res.data

    def test_la_eleccion_explicita_gana_a_la_del_sistema(self, client, db):
        client.set_cookie("tema", "claro")
        client.set_cookie("tema_sistema", "oscuro")
        res = client.get("/login")
        assert b'data-tema="claro"' in res.data

    @pytest.mark.parametrize("elegido", ["claro", "oscuro", "auto"])
    def test_el_selector_marca_la_opcion_elegida(self, client, db, elegido):
        """'auto' debe verse pulsado aunque el HTML resuelto diga 'claro'."""
        client.set_cookie("tema", elegido)
        html = client.get("/login").data.decode("utf-8")

        # Se acota a la etiqueta <button …> de cada opción, para no leer por
        # error el aria-pressed del botón de al lado.
        botones = {
            m.group("valor"): m.group(0)
            for m in re.finditer(
                r"<button[^>]*data-tema-valor=\"(?P<valor>[a-z]+)\"[^>]*>", html
            )
        }
        assert set(botones) == {"claro", "oscuro", "auto"}
        for valor, etiqueta in botones.items():
            esperado = "true" if valor == elegido else "false"
            assert f'aria-pressed="{esperado}"' in etiqueta, (
                f"con tema={elegido}, el botón {valor} debería tener "
                f'aria-pressed="{esperado}"'
            )


# ---------------------------------------------------------------------------
# Contraste de las paletas
# ---------------------------------------------------------------------------


def _luminancia(hexa: str) -> float:
    h = hexa.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    canales = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    canales = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2]


def _ratio(a: str, b: str) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    claro, oscuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (oscuro + 0.05)


def _paletas() -> tuple[dict[str, str], dict[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)

    def bloque(patron: str) -> dict[str, str]:
        m = re.search(patron, css, re.S)
        assert m, f"no encuentro el bloque {patron!r} en styles.css"
        return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(1)))

    return (
        bloque(r":root\s*\{(.*?)\n\}"),
        bloque(r':root\[data-tema="oscuro"\]\s*\{(.*?)\n\}'),
    )


def _resolver(token: str, paleta: dict[str, str], base: dict[str, str]) -> str:
    """Sigue las cadenas ``var(--x)`` como haría el navegador."""
    valor = paleta.get(token, base.get(token, ""))
    for _ in range(6):
        m = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", valor.strip())
        if not m:
            break
        t = m.group(1)
        valor = paleta.get(t, base.get(t, ""))
    return valor.strip()


#: (descripción, token de texto, token de fondo, ratio mínimo).
#: 4.5 para texto (WCAG 2.1 SC 1.4.3); 3.0 para contornos de control (SC 1.4.11).
PARES = [
    ("cuerpo", "--color-text", "--color-bg", 4.5),
    ("texto sobre tarjeta", "--color-text", "--color-surface", 4.5),
    ("texto atenuado", "--color-text-muted", "--color-surface", 4.5),
    ("texto atenuado sobre fondo", "--color-text-muted", "--color-bg", 4.5),
    ("enlace inline", "--color-link", "--color-surface", 4.5),
    ("enlace sobre fondo", "--color-link", "--color-bg", 4.5),
    ("cabecera", "--color-topbar-fg", "--color-topbar-bg", 4.5),
    ("botón primario", "--color-on-primary", "--color-primary", 4.5),
    ("botón secundario", "--color-on-secondary", "--color-secondary", 4.5),
    ("skip-link", "--color-on-link", "--color-link", 4.5),
    ("badge neutro", "--color-text", "--color-surface-3", 4.5),
    ("chip neutro", "--color-text-muted", "--color-surface-3", 4.5),
    ("badge ok", "--color-success-strong", "--color-success-soft", 4.5),
    ("badge aviso", "--color-warning-strong", "--color-warning-soft", 4.5),
    ("badge error", "--color-danger-strong", "--color-danger-soft", 4.5),
    ("chip competencia", "--color-info-strong", "--color-info-soft", 4.5),
    ("chip fase", "--color-accent-strong", "--color-accent-soft", 4.5),
    ("bloque JSON", "--color-inverse-text", "--color-inverse-bg", 4.5),
    ("callout primario", "--color-text-muted", "--color-primary-soft", 4.5),
    ("callout secundario", "--color-text-muted", "--color-secondary-soft", 4.5),
    ("código inline", "--color-text", "--color-code-bg", 4.5),
    ("borde de campo sobre tarjeta", "--color-border-strong", "--color-surface", 3.0),
    ("borde de campo sobre fondo", "--color-border-strong", "--color-bg", 3.0),
]


class TestContraste:
    @pytest.mark.parametrize("tema", ["claro", "oscuro"])
    @pytest.mark.parametrize("desc,tok_fg,tok_bg,minimo", PARES)
    def test_par_cumple_wcag(self, tema, desc, tok_fg, tok_bg, minimo):
        base, oscuro = _paletas()
        paleta = base if tema == "claro" else oscuro
        fg = _resolver(tok_fg, paleta, base)
        bg = _resolver(tok_bg, paleta, base)
        assert fg.startswith("#") and bg.startswith("#"), (
            f"[{tema}] {desc}: tokens sin resolver ({fg!r} / {bg!r})"
        )
        r = _ratio(fg, bg)
        assert r >= minimo, (
            f"[{tema}] {desc}: {fg} sobre {bg} da {r:.2f}:1, por debajo de {minimo}:1"
        )


class TestSinLiteralesSueltos:
    """Un color literal fuera de :root ignoraría el cambio de tema.

    Es exactamente lo que había antes de esta tarea: 44 colores repartidos por
    reglas concretas que se habrían quedado en claro sobre fondo oscuro.
    """

    def test_no_hay_colores_fuera_de_los_bloques_de_tokens(self):
        css = CSS.read_text(encoding="utf-8")
        # Fuera comentarios, conservando el número de línea.
        css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), css, flags=re.S)

        culpables = []
        for i, linea in enumerate(css.split("\n"), 1):
            if re.match(r"\s*--[a-z0-9-]+\s*:", linea):
                continue  # definición de token: ahí es donde deben vivir
            for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", linea):
                culpables.append(f"  línea {i}: {m.group(0)}  |  {linea.strip()[:70]}")

        assert not culpables, (
            "colores literales fuera de los bloques de tokens; no responderán "
            "al cambio de tema:\n" + "\n".join(culpables)
        )
