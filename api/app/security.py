"""Utilidades de seguridad y autorización: decoradores de roles y permisos."""
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import abort, jsonify, redirect, request, url_for
from flask_login import current_user


def permisos_de(usuario) -> frozenset[str]:
    """Permisos efectivos de ``usuario``, o vacío si no tiene rol.

    ``Rol.permisos`` es JSONB y está tipado como ``list | dict``. Los seeds
    escriben una lista, pero el tipo admite las dos formas y un JSONB puede
    acabar conteniendo cualquier cosa si alguien lo edita a mano contra la base
    de datos. Se contemplan ambas en vez de suponer una: equivocarse aquí no
    da error, solo deja pasar o deja fuera a quien no toca.
    """
    rol = getattr(usuario, "rol", None)
    if rol is None:
        return frozenset()
    permisos = rol.permisos
    if isinstance(permisos, dict):
        # Forma {"usuario:crear": true}: cuentan los que estén a verdadero.
        return frozenset(clave for clave, valor in permisos.items() if valor)
    if isinstance(permisos, (list, tuple, set)):
        return frozenset(str(p) for p in permisos)
    return frozenset()


def _rechazar_json(codigo: int, error: str):
    return jsonify({"error": error}), codigo


def _rechazar_pagina(codigo: int, error: str):
    """Rechazo para una ruta que sirve HTML.

    Devolver ``{"error": "no_autenticado"}`` en el cuerpo de una página deja a
    la persona mirando un JSON suelto en el navegador.

    Sin sesión se manda al login, con la ruta actual para volver después. Con
    sesión pero sin permiso se corta con 403 y su plantilla: mandar al login a
    quien ya ha iniciado sesión monta un bucle de «entra» → «ya estás
    dentro» → «no puedes pasar».
    """
    if codigo == 401:
        # ``login_page``, no ``login``: el endpoint se llama como la función de
        # la vista, no como la ruta. Escribirlo de memoria costó un 500 —
        # ``url_for`` no avisa al importar, solo revienta cuando alguien sin
        # sesión abre la página.
        return redirect(url_for("pages.login_page", siguiente=request.path))
    abort(403)


def role_required(*roles: str) -> Callable:
    """Restringe el acceso a usuarios con uno de los roles indicados.

    Comprueba el **nombre** del rol y responde siempre en JSON.

    Para código nuevo es preferible ``permiso_requerido``: encaja con el
    modelo de permisos que los roles ya llevan dentro, y así repartir de otra
    manera lo que puede hacer cada rol no obliga a tocar ningún endpoint.
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return _rechazar_json(401, "no_autenticado")
            if current_user.rol is None or current_user.rol.nombre not in roles:
                return _rechazar_json(403, "permiso_denegado")
            return view(*args, **kwargs)

        return wrapper

    return decorator


def permiso_requerido(*permisos: str, pagina: bool = False) -> Callable:
    """Exige **todos** los permisos indicados sobre el rol del usuario.

    Todos y no alguno: un endpoint que da de baja a un docente y borra su
    contenido necesita permiso sobre las dos cosas, y con la semántica
    «alguno» bastaría tener uno para hacer ambas. Cuando de verdad valga
    cualquiera de dos, se comprueba dentro de la vista y se ve que es adrede.

    ``pagina=True`` en las rutas que sirven HTML: cambia el rechazo de JSON a
    redirección o página de error. Va explícito en cada llamada en vez de
    deducirse del path, porque adivinar el formato de salida a partir de la
    URL es justo el tipo de regla que se rompe en silencio al añadir una ruta
    que no encaja en el patrón.

    Los permisos ya se sembraban en ``seed_roles`` desde el TFG, pero ningún
    endpoint los miraba: la autorización real la hacía ``role_required``, por
    nombre de rol. Esto los pone en uso.
    """
    exigidos = frozenset(permisos)
    rechazar = _rechazar_pagina if pagina else _rechazar_json

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return rechazar(401, "no_autenticado")
            if not exigidos <= permisos_de(current_user):
                return rechazar(403, "permiso_denegado")
            return view(*args, **kwargs)

        return wrapper

    return decorator
