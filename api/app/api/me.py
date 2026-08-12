"""Endpoints para el usuario autenticado (perfil propio)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..ai import catalogo
from .. import i18n
from ..extensions import db, limiter
from ..schemas import PonerRespaldoIn, QuitarRespaldoIn, UsuarioOut, UsuarioUpdateIn
from ..services import respaldo as svc_respaldo
from ..services.respaldo import RespaldoError


bp = Blueprint("me", __name__, url_prefix="/me")


@bp.get("")
@login_required
def obtener_perfil():
    """Devuelve los datos del usuario actualmente autenticado (CU-09)."""
    return jsonify(UsuarioOut.from_model(current_user).model_dump(mode="json")), 200


@bp.put("")
@login_required
def actualizar_perfil():
    """Actualiza los campos editables del propio perfil (CU-09)."""
    data = UsuarioUpdateIn.model_validate(request.get_json(silent=True) or {})
    cambios = data.model_dump(exclude_unset=True)

    # La preferencia de IA se sanea contra el catálogo antes de guardarla: los
    # proveedores válidos dependen de la configuración del despliegue, así que
    # no se pueden fijar en el esquema Pydantic. Una elección inválida no tiene
    # por qué ser culpa del usuario —el proveedor puede haber dejado de estar
    # disponible—, así que se guarda como «usar el del sistema» en lugar de
    # devolver un 400 por algo que él no puede arreglar.
    if "proveedor_ia" in cambios or "modelo_ia" in cambios:
        proveedor, modelo = catalogo.validar(
            cambios.get("proveedor_ia", current_user.proveedor_ia),
            cambios.get("modelo_ia", current_user.modelo_ia),
        )
        cambios["proveedor_ia"] = proveedor
        cambios["modelo_ia"] = modelo

    # Un idioma que no se ofrece se guarda como NULL, que significa
    # «deducirlo del navegador». Igual que con el proveedor de IA: si mañana
    # se retira un idioma del catálogo, la cuenta de quien lo tuviera elegido
    # vuelve al comportamiento por defecto en vez de quedarse rota.
    if "idioma_interfaz" in cambios:
        valor = (cambios["idioma_interfaz"] or "").strip().lower()
        cambios["idioma_interfaz"] = valor if valor in i18n.IDIOMAS else None

    for atributo, valor in cambios.items():
        setattr(current_user, atributo, valor)

    db.session.commit()
    return jsonify(UsuarioOut.from_model(current_user).model_dump(mode="json")), 200


@bp.get("/ia/catalogo")
@login_required
def catalogo_ia():
    """Proveedores y modelos que este despliegue permite elegir.

    Lo consume el selector del perfil. Se sirve desde el servidor, y no como
    lista fija en el JavaScript, porque depende de qué claves haya
    configuradas: ofrecer un proveedor sin clave llevaría al usuario a elegir
    algo que caería en silencio al proveedor simulado.
    """
    proveedor_sistema, modelo_sistema = catalogo.por_defecto()
    return (
        jsonify(
            {
                "proveedores": [p.to_dict() for p in catalogo.disponibles()],
                "sistema": {
                    "proveedor": proveedor_sistema,
                    "modelo": modelo_sistema,
                    "etiqueta": catalogo.ETIQUETAS.get(
                        proveedor_sistema, proveedor_sistema
                    ),
                },
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Correo de respaldo
#
# Vive bajo `/me` y no bajo `/auth` porque son operaciones sobre la propia
# cuenta, con sesión iniciada, como cambiar el nombre o el idioma. La única
# pieza que está en `/auth` es confirmar el enlace, y por el motivo de siempre:
# ese enlace se abre desde el buzón, muchas veces en otro navegador.
# ---------------------------------------------------------------------------


@bp.get("/correo-de-respaldo")
@login_required
def ver_respaldo():
    """Qué respaldo tiene la cuenta, enmascarado y con su estado.

    No forma parte de `UsuarioOut` a propósito. Ese esquema se sirve en varios
    sitios —incluido el panel de administración—, y meter ahí una dirección
    personal la repartiría por todos ellos de golpe. Un endpoint propio deja
    claro quién la pide y para qué.
    """
    return (
        jsonify(
            {
                "correo": svc_respaldo.enmascarar(current_user.correo_respaldo),
                "verificado": current_user.tiene_respaldo,
                "verificado_en": (
                    current_user.correo_respaldo_verificado_en.isoformat()
                    if current_user.correo_respaldo_verificado_en
                    else None
                ),
            }
        ),
        200,
    )


@bp.post("/correo-de-respaldo")
@login_required
@limiter.limit("10 per hour")
def poner_respaldo():
    """Pide el enlace de confirmación para poner o cambiar el respaldo.

    Devuelve **a qué dirección se ha enviado**, enmascarada. Importa porque al
    cambiarlo el enlace no va al buzón nuevo sino al anterior: sin decirlo, la
    persona estaría esperando un correo que no va a llegar donde mira.
    """
    data = PonerRespaldoIn.model_validate(request.get_json(silent=True) or {})
    try:
        destino = svc_respaldo.solicitar(current_user, data.correo)
    except RespaldoError as exc:
        return jsonify({"error": exc.code, "mensaje": exc.message}), 409

    return (
        jsonify(
            {
                "resultado": "pendiente",
                "enviado_a": svc_respaldo.enmascarar(destino),
                "era_cambio": destino != data.correo,
            }
        ),
        202,
    )


@bp.post("/correo-de-respaldo/quitar")
@login_required
@limiter.limit("10 per hour")
def quitar_respaldo():
    """Deja la cuenta sin respaldo. Basta la contraseña actual."""
    data = QuitarRespaldoIn.model_validate(request.get_json(silent=True) or {})
    try:
        svc_respaldo.quitar(current_user, data.contrasena)
    except RespaldoError as exc:
        return jsonify({"error": exc.code, "mensaje": exc.message}), 409

    return jsonify({"resultado": "ok"}), 200
