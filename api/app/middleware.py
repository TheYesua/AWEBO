"""Middlewares de aplicación: request-id, headers de seguridad."""
from __future__ import annotations

import secrets
import uuid

import structlog
from flask import Flask, g, request

#: La política de contenidos, con un hueco para el `nonce` de cada petición.
#:
#: POR QUÉ ESTO NO ESTÁ EN NGINX, QUE ES DONDE SE ESPERARÍA
#: ---------------------------------------------------------
#: Porque lleva `nonce`, y un `nonce` tiene que valer una sola vez: el valor
#: que va en la cabecera y el que va en el atributo de cada `<script>` son el
#: mismo y cambian en cada petición. Nginx puede poner cabeceras fijas, pero no
#: inyectar nada en el HTML que sirve el backend, así que la única forma de
#: casarlos es generarlos donde se renderiza la página.
#:
#: LO QUE CADA DIRECTIVA IMPIDE
#: -----------------------------
#: * `script-src` sin `'unsafe-inline'` es **la que de verdad para un XSS**:
#:   un `<script>` inyectado no lleva el `nonce` de esta petición y no corre.
#: * `object-src 'none'` quita Flash y compañía, que son vías de ejecución.
#: * `frame-ancestors 'none'` impide el clickjacking: nadie puede meter AWEBO
#:   dentro de un iframe suyo y engañar al docente sobre dónde está pulsando.
#: * `base-uri 'self'` impide que un `<base>` inyectado redirija todas las
#:   rutas relativas —incluidas las de los scripts propios— a otro servidor.
#: * `form-action 'self'` impide que un formulario inyectado mande los datos
#:   del docente a un tercero.
#:
#: `style-src` sí admite `'unsafe-inline'`, y es una concesión consciente: hay
#: 22 atributos `style=` repartidos por las plantillas, y un estilo en línea no
#: ejecuta código. Quitarla obligaría a revisarlos uno a uno a cambio de muy
#: poco.
#:
#: Los tres orígenes externos son los que la aplicación usa de verdad: unpkg
#: para los iconos de Lucide, y las dos mitades de Google Fonts —la hoja de
#: estilos viene de `fonts.googleapis.com` y los ficheros de fuente de
#: `fonts.gstatic.com`—.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}' https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def csp_nonce() -> str:
    """El `nonce` de esta petición, para que las plantillas lo pongan."""
    return g.get("csp_nonce", "")


def register_middlewares(app: Flask) -> None:
    """Registra before/after_request globales."""

    app.jinja_env.globals["csp_nonce"] = csp_nonce

    @app.before_request
    def _generar_nonce() -> None:
        # Uno nuevo por petición. Si se reutilizara, dejaría de servir para
        # nada: bastaría con leer el de una página para firmar un script
        # inyectado en la siguiente.
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.before_request
    def _inject_request_id() -> None:
        # Prioridad: cabecera del cliente (para trazabilidad de proxies
        # o frontends) → auto-generado si no llega.
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = rid
        # Enlaza el request_id en los contextvars de structlog: a partir
        # de aquí, CUALQUIER log emitido durante la petición incluirá la
        # clave ``request_id`` sin tener que pasarla a mano.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)

    @app.after_request
    def _add_response_headers(response):
        # Siempre devolvemos el request-id para que el cliente pueda
        # correlacionar logs o errores con el servidor.
        response.headers["X-Request-ID"] = g.get("request_id", "")
        # Seguridad adicional
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = _CSP.format(
            nonce=g.get("csp_nonce", "")
        )
        # Redundante con `frame-ancestors 'none'` de la CSP, y se pone igual:
        # los navegadores que no entienden `frame-ancestors` sí entienden esto,
        # y una cabecera de más no cuesta nada.
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.teardown_request
    def _clear_log_context(_exc):
        # Evita que el request_id de una petición se filtre a la siguiente
        # si el worker WSGI reutiliza el hilo (raro pero documentado).
        structlog.contextvars.clear_contextvars()
