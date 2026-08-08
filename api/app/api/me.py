"""Endpoints para el usuario autenticado (perfil propio)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..ai import catalogo
from .. import i18n
from ..extensions import db
from ..schemas import UsuarioOut, UsuarioUpdateIn


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
