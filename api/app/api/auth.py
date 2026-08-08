"""Blueprint de autenticación: registro, login y logout."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..schemas import LoginIn, RegisterIn, ResetPasswordIn, UsuarioOut
from ..services.auth_service import AuthError, autenticar, registrar_usuario, resetear_contrasena


bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.post("/register")
@limiter.limit("5 per hour; 20 per day")
def register():
    """Registra un nuevo usuario con rol ``docente`` por defecto (CU-01)."""
    data = RegisterIn.model_validate(request.get_json(silent=True) or {})
    try:
        usuario = registrar_usuario(**data.model_dump())
    except AuthError as exc:
        # 202 y no 409 cuando la solicitud de reclamación queda registrada: la
        # petición ha hecho lo que pedía, solo que el efecto llega más tarde y
        # a través de otra persona. Devolver un conflicto haría que un cliente
        # que solo mire el código lo tratase como un fallo y reintentase.
        codigo = 202 if exc.code == "reclamacion_pendiente" else 409
        return jsonify({"error": exc.code, "mensaje": str(exc), **exc.datos}), codigo

    # Auto-login tras registro para mejorar UX
    login_user(usuario, remember=False)
    usuario.touch_last_seen()
    db.session.commit()

    return jsonify(UsuarioOut.from_model(usuario).model_dump(mode="json")), 201


@bp.post("/login")
@limiter.limit("10 per minute; 50 per hour")
def login():
    """Inicia sesión y crea la cookie de sesión server-side (CU-02)."""
    if current_user.is_authenticated:
        return jsonify({"error": "ya_autenticado"}), 400

    data = LoginIn.model_validate(request.get_json(silent=True) or {})
    try:
        usuario = autenticar(data.correo, data.contrasena)
    except AuthError as exc:
        return jsonify({"error": exc.code, "mensaje": str(exc)}), 401

    login_user(usuario, remember=False)
    usuario.touch_last_seen()
    db.session.commit()

    return jsonify(UsuarioOut.from_model(usuario).model_dump(mode="json")), 200


@bp.post("/reset-password")
@limiter.limit("5 per hour")
def reset_password():
    """Restablece la contraseña de un usuario dado su correo (CU-03)."""
    data = ResetPasswordIn.model_validate(request.get_json(silent=True) or {})
    try:
        resetear_contrasena(correo=data.correo, nueva_contrasena=data.nueva_contrasena)
    except AuthError as exc:
        return jsonify({"error": exc.code, "mensaje": str(exc)}), 404
    return jsonify({"resultado": "ok"}), 200


@bp.post("/cambiar-contrasena")
@login_required
def cambiar_contrasena():
    """Cambia la contraseña del usuario autenticado desde su perfil."""
    body = request.get_json(silent=True) or {}
    contrasena_actual = body.get("contrasena_actual", "")
    nueva_contrasena = body.get("nueva_contrasena", "")

    if not current_user.check_password(contrasena_actual):
        return jsonify({"error": "contrasena_incorrecta", "mensaje": "La contraseña actual no es correcta"}), 400

    try:
        data = ResetPasswordIn(correo=current_user.correo, nueva_contrasena=nueva_contrasena)
    except Exception as exc:
        return jsonify({"error": "validacion", "mensaje": str(exc)}), 422

    current_user.set_password(data.nueva_contrasena)
    db.session.commit()
    return jsonify({"resultado": "ok"}), 200


@bp.post("/logout")
@login_required
def logout():
    """Cierra la sesión actual e invalida la cookie (CU-08)."""
    logout_user()
    return jsonify({"resultado": "ok"}), 200
