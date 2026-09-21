"""Protección contra CSRF: un secreto que el navegador ajeno no puede leer.

QUÉ ATAQUE PARA Y CUÁL NO
--------------------------
Un sitio cualquiera puede hacer que el navegador de un docente que tiene la
sesión abierta envíe una petición a AWEBO, y el navegador **adjunta la cookie
de sesión solo**, porque las cookies viajan por destino y no por procedencia.
Bastaría un formulario oculto para borrar una SdA ajena.

Lo que un sitio ajeno **no** puede hacer es leer una respuesta de AWEBO: se lo
impide la política del mismo origen. De ahí la defensa: se exige en cada
petición que cambia estado un valor que solo se obtiene leyendo una página de
AWEBO.

LO QUE YA HABÍA, Y POR QUÉ NO BASTA
------------------------------------
La cookie va con ``SameSite=Lax``, que ya impide al navegador mandarla en un
POST venido de otro sitio. Es buena defensa y se queda. No basta sola por dos
motivos: depende por entero de que el navegador la respete —y la aplicación no
controla con qué navegan los docentes—, y no cubre un subdominio ajeno, que
para «same-site» cuenta como propio. Dos defensas independientes, y ninguna
que dependa de la otra.

POR QUÉ NO SE USA FLASK-WTF, QUE ES LO HABITUAL
------------------------------------------------
Porque su parte valiosa es la integración con WTForms, y aquí no hay WTForms:
la validación es de pydantic. Lo que quedaría es lo de abajo con una
dependencia más. Y el trabajo de verdad —hacer que las 40 llamadas `fetch` de
las plantillas manden la cabecera— no lo ahorra ninguna biblioteca; eso se
resuelve en `static/js/app.js`, envolviendo `window.fetch` una sola vez.

EL TOKEN VIVE EN LA SESIÓN
---------------------------
Y no en una cookie firmada aparte —el patrón de «doble envío»—, porque atarlo
a la sesión es lo que impide que un subdominio ajeno fabrique un par
cookie+cabecera coherente. El precio es que una petición que cambia estado
necesita sesión; en esta aplicación todas la tienen, porque hasta la de
`/idioma` la crea al renderizar la página.

LO QUE NO HACE, DICHO PARA QUE NO SE DÉ POR HECHO
--------------------------------------------------
**No rota el token al iniciar sesión.** Sería una capa más contra la fijación
de sesión, y no se pone aquí porque de eso se ocupa Flask-Login con su propio
identificador; añadirlo obligaría además a que la página recargara tras entrar
—cosa que hoy hace, pero que dejaría de ser un detalle y pasaría a ser un
requisito—. Si algún día el acceso deja de recargar la página, esto hay que
revisarlo.
"""
from __future__ import annotations

import secrets

from flask import Flask, abort, request, session

#: Dónde se guarda. El prefijo con guion bajo sigue la convención de Flask
#: para las claves internas de la sesión.
CLAVE_SESION = "_csrf_token"

#: Cómo lo manda el navegador. La cabecera es la vía normal —la usa el
#: envoltorio de `fetch`—; el campo oculto existe por el único formulario HTML
#: de verdad que queda, el selector de idioma, que tiene que funcionar también
#: sin JavaScript.
NOMBRE_CABECERA = "X-CSRF-Token"
NOMBRE_CAMPO = "_csrf"

#: Los métodos que no cambian estado no se comprueban. Es la lista de RFC 9110,
#: no una elección: si algún día un GET cambiara algo, el fallo sería ese GET y
#: no esta lista.
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def token() -> str:
    """El token de esta sesión, creándolo la primera vez.

    32 bytes de `secrets`, que es el generador criptográfico de la biblioteca
    estándar. `random` no vale aquí: es predecible a partir de unas cuantas
    salidas, y todo esto se sostiene sobre que el atacante no pueda adivinarlo.
    """
    if CLAVE_SESION not in session:
        session[CLAVE_SESION] = secrets.token_urlsafe(32)
    return session[CLAVE_SESION]


def _enviado() -> str:
    """Lo que trae la petición, mire donde mire."""
    de_cabecera = request.headers.get(NOMBRE_CABECERA)
    if de_cabecera:
        return de_cabecera
    # `.form` solo se consulta si el cuerpo es un formulario: tocarlo en una
    # petición JSON haría que Flask leyera y descartara el cuerpo.
    if request.mimetype in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        return request.form.get(NOMBRE_CAMPO, "")
    return ""


def init_app(app: Flask) -> None:
    """Exige el token en todo lo que cambie estado, y lo ofrece a las plantillas."""

    # Disponible como `{{ csrf_token() }}` en cualquier plantilla. Es una
    # función y no un valor porque llamarla es lo que crea el token: así, una
    # página que no lo use no escribe en la sesión.
    app.jinja_env.globals["csrf_token"] = token

    @app.before_request
    def _exigir_token():
        if not app.config.get("CSRF_ENABLED", True):
            return None
        if request.method in METODOS_SEGUROS:
            return None

        esperado = session.get(CLAVE_SESION)
        recibido = _enviado()

        # `compare_digest` y no `==`: comparar cadenas con `==` se detiene en
        # el primer carácter distinto, y ese tiempo distinto es medible. Cuesta
        # lo mismo hacerlo bien.
        if not esperado or not recibido or not secrets.compare_digest(recibido, esperado):
            abort(403, description="Token CSRF ausente o inválido.")
        return None
