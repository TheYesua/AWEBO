"""Blueprint de autenticación: registro, login y logout."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db, limiter
from ..schemas import (
    ConfirmarBajaIn,
    LoginIn,
    RegisterIn,
    RestablecerConTokenIn,
    ResetPasswordIn,
    SolicitarBajaIn,
    SolicitarRestablecimientoIn,
    UsuarioOut,
)
from ..services.auth_service import (
    AuthError,
    autenticar,
    registrar_usuario,
    resetear_contrasena,
)
from ..services.baja import BajaError
from ..services.baja import confirmar as confirmar_baja_servicio
from ..services.baja import solicitar as solicitar_baja_servicio
from ..services.restablecimiento import TokenInvalido, restablecer, solicitar


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


@bp.post("/solicitar-restablecimiento")
@limiter.limit("5 per hour")
def solicitar_restablecimiento():
    """Envía un enlace de restablecimiento si la dirección está registrada.

    **Responde siempre 202 y siempre lo mismo**, exista la cuenta o no. Si
    distinguiera los dos casos, este formulario sería una herramienta para
    averiguar qué direcciones tienen cuenta en AWEBO — el paso previo a probar
    contraseñas contra ellas.

    Por eso tampoco hay rama de error aquí: ``solicitar`` no lanza nunca.
    """
    data = SolicitarRestablecimientoIn.model_validate(request.get_json(silent=True) or {})
    solicitar(data.correo)
    return (
        jsonify(
            {
                "resultado": "ok",
                "mensaje": "Si esa dirección tiene cuenta, recibirás un correo con un enlace.",
            }
        ),
        202,
    )


@bp.post("/reset-password")
@limiter.limit("5 per hour")
def reset_password():
    """Cambia la contraseña presentando el token que llegó por correo.

    Hasta el 09/08/2026 esta ruta cambiaba la contraseña de cualquier cuenta
    **sabiendo solo su correo**: sin sesión, sin token y sin confirmar nada.
    Ahora exige el token, que caduca en una hora y solo sirve una vez.

    El token inválido devuelve 400 con un código genérico. No se distingue
    entre caducado, manipulado y ya usado: contarlo le diría a quien prueba
    tokens si va por buen camino.
    """
    data = RestablecerConTokenIn.model_validate(request.get_json(silent=True) or {})
    try:
        restablecer(token=data.token, nueva_contrasena=data.nueva_contrasena)
    except TokenInvalido:
        return (
            jsonify(
                {
                    "error": "token_invalido",
                    "mensaje": "El enlace no es válido o ha caducado. Pide uno nuevo.",
                }
            ),
            400,
        )
    except AuthError as exc:
        # Aquí sí se explica el problema: la contraseña es débil y quien la
        # escribe necesita saber qué le falta para corregirla.
        return jsonify({"error": exc.code, "mensaje": str(exc)}), 400
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


@bp.post("/solicitar-baja")
@login_required
@limiter.limit("5 per hour")
def solicitar_baja():
    """Primer paso de la baja: comprueba la contraseña y manda el enlace.

    **Aquí sí se explica el error**, al contrario que en el restablecimiento.
    Allí callar el motivo evita que el formulario sirva para averiguar qué
    direcciones tienen cuenta; aquí hay sesión iniciada y se está hablando de
    la cuenta propia, así que no hay nada que ocultar y sí hay algo que
    explicar: si la contraseña está mal, quien la teclea necesita saberlo.
    """
    data = SolicitarBajaIn.model_validate(request.get_json(silent=True) or {})
    try:
        solicitar_baja_servicio(
            current_user,
            data.contrasena,
            conservar_contenido=data.conservar_contenido,
        )
    except BajaError as exc:
        return jsonify({"error": exc.code, "mensaje": exc.message}), 400
    return (
        jsonify(
            {
                "resultado": "ok",
                "mensaje": "Te hemos enviado un correo para confirmar la baja.",
            }
        ),
        202,
    )


@bp.post("/confirmar-baja")
@limiter.limit("10 per hour")
def confirmar_baja():
    """Segundo paso: aplica la baja del modo que diga el enlace.

    **Sin ``@login_required`` a propósito.** El enlace llega al correo y se
    abre donde esté abierto el buzón, que muchas veces es otro navegador u otro
    dispositivo. Exigir sesión obligaría a iniciarla justo para darse de baja, y
    no añadiría seguridad: el token ya identifica a su dueño, va firmado, sirve
    una vez y caduca en media hora.
    """
    data = ConfirmarBajaIn.model_validate(request.get_json(silent=True) or {})
    try:
        resumen = confirmar_baja_servicio(data.token)
    except TokenInvalido:
        return (
            jsonify(
                {
                    "error": "token_invalido",
                    "mensaje": "El enlace no es válido o ha caducado. Pide uno nuevo.",
                }
            ),
            400,
        )
    except BajaError as exc:
        # El caso real: entre pedir la baja y confirmarla, esta cuenta se quedó
        # como única administradora.
        return jsonify({"error": exc.code, "mensaje": exc.message}), 409

    # Cerrar la sesión de quien está confirmando, si la tiene.
    #
    # Escribí aquí que esto «no era imprescindible porque ``load_user`` ya
    # rechaza una fila borrada o con lápida». Al sabotearlo se vio lo
    # contrario: quitando esta línea, los dos tests de sesión fallan. La
    # segunda red existe, pero es la siguiente petición quien la aplica, y
    # hasta entonces la respuesta a **esta** petición sigue llevando una cookie
    # de sesión válida. Cerrarla aquí es lo único que la mata en el acto.
    if current_user.is_authenticated:
        logout_user()

    return jsonify({"resultado": "ok", **resumen}), 200


@bp.post("/logout")
@login_required
def logout():
    """Cierra la sesión actual e invalida la cookie (CU-08)."""
    logout_user()
    return jsonify({"resultado": "ok"}), 200
