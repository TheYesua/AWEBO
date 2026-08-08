"""Endpoints del panel de administración.

Todo cuelga de ``/admin``: la página en ``/admin`` y la API en ``/admin/api/…``.
Separarlas por prefijo permite que el rechazo por falta de permiso sea el
adecuado en cada caso —redirección al login en la página, JSON en la API— sin
tener que adivinarlo.

La autorización se apoya en los permisos que ``seed_roles`` ya sembraba desde
el TFG y que hasta ahora no miraba nadie. Cada endpoint exige el suyo, no
«ser administrador»: así, repartir de otra manera lo que puede hacer cada rol
es cambiar el seed, no recorrer los endpoints.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..models import Rol
from ..security import permiso_requerido
from ..services import admin_service as svc
from ..services.auth_service import AuthError, registrar_usuario, validar_contrasena


bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Esquemas
# ---------------------------------------------------------------------------


class CrearUsuarioIn(BaseModel):
    """Alta de una cuenta desde el panel."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr
    contrasena: str = Field(min_length=8, max_length=128)
    nombre: str = Field(min_length=2, max_length=100)
    centro_educativo: str | None = Field(default=None, max_length=200)
    especialidad: str | None = Field(default=None, max_length=100)
    comunidad_autonoma: str | None = Field(default=None, max_length=50)
    rol: str = Field(default=Rol.DOCENTE)

    @field_validator("contrasena")
    @classmethod
    def _complejidad(cls, v: str) -> str:
        # Delegado en el servicio: es la única copia de la política. Aquí sirve
        # para que el error salga como un 422 con mensaje legible.
        return validar_contrasena(v)

    @field_validator("rol")
    @classmethod
    def _rol_conocido(cls, v: str) -> str:
        if v not in {Rol.DOCENTE, Rol.ADMINISTRADOR}:
            raise ValueError(f"Rol desconocido: {v!r}")
        return v


class EditarUsuarioIn(BaseModel):
    """Edición parcial: solo se toca lo que venga.

    ``exclude_unset`` al volcarlo es lo que hace que ausente y ``null``
    signifiquen cosas distintas. Ausente es «no lo toques»; ``null`` es
    «bórralo». Sin esa distinción, un formulario que solo manda el nombre
    vaciaría el centro educativo y la especialidad.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    centro_educativo: str | None = Field(default=None, max_length=200)
    especialidad: str | None = Field(default=None, max_length=100)
    comunidad_autonoma: str | None = Field(default=None, max_length=50)
    rol: str | None = None

    @field_validator("rol")
    @classmethod
    def _rol_conocido(cls, v: str | None) -> str | None:
        if v is not None and v not in {Rol.DOCENTE, Rol.ADMINISTRADOR}:
            raise ValueError(f"Rol desconocido: {v!r}")
        return v


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


@bp.get("/")
@permiso_requerido("usuario:listar", pagina=True)
def panel():
    return render_template("admin/panel.html")


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------


@bp.get("/api/estadisticas")
@permiso_requerido("usuario:listar", "situacion:listar_todas")
def estadisticas():
    return jsonify(svc.estadisticas_globales()), 200


@bp.get("/api/usuarios")
@permiso_requerido("usuario:listar", "situacion:listar_todas")
def usuarios():
    """Cuentas con sus métricas, paginadas.

    Es el listado y las estadísticas por usuario a la vez, porque el panel
    siempre las muestra juntas y separarlo obligaría a la interfaz a cruzar dos
    respuestas por identificador.
    """
    return jsonify(
        svc.estadisticas_por_usuario(
            limite=request.args.get("limite", default=svc.POR_PAGINA, type=int),
            desplazamiento=request.args.get("desplazamiento", default=0, type=int),
        )
    ), 200


@bp.get("/api/usuarios/indice")
@permiso_requerido("usuario:listar")
def indice_usuarios():
    """Solo id y correo, sin paginar: alimenta el desplegable de filtro.

    Si ese desplegable se rellenara con la página visible del listado, solo se
    podría filtrar por las diez cuentas que ya se están viendo.
    """
    return jsonify({"usuarios": svc.indice_usuarios()}), 200


# ---------------------------------------------------------------------------
# Gestión de cuentas
# ---------------------------------------------------------------------------


@bp.post("/api/usuarios")
@permiso_requerido("usuario:crear")
def crear_usuario():
    datos = CrearUsuarioIn.model_validate(request.get_json(silent=True) or {})
    try:
        usuario = registrar_usuario(
            correo=datos.correo,
            contrasena=datos.contrasena,
            nombre=datos.nombre,
            centro_educativo=datos.centro_educativo,
            especialidad=datos.especialidad,
            comunidad_autonoma=datos.comunidad_autonoma,
            rol_nombre=datos.rol,
        )
    except AuthError as exc:
        return jsonify({"error": exc.code, "mensaje": str(exc), **exc.datos}), 409
    return jsonify(svc.usuario_publico(usuario)), 201


@bp.patch("/api/usuarios/<int:id_usuario>")
@permiso_requerido("usuario:editar")
def editar_usuario(id_usuario: int):
    datos = EditarUsuarioIn.model_validate(request.get_json(silent=True) or {})
    try:
        return jsonify(
            svc.editar_usuario(
                id_usuario, por=current_user, **datos.model_dump(exclude_unset=True)
            )
        ), 200
    except svc.AdminError as exc:
        return jsonify({"error": exc.code, "mensaje": str(exc)}), _codigo(exc)


@bp.delete("/api/usuarios/<int:id_usuario>")
@permiso_requerido("usuario:eliminar")
def eliminar_usuario(id_usuario: int):
    """Baja en uno de los dos modos.

    El modo va en el cuerpo y **no tiene valor por defecto seguro**: se exige
    que venga. Un defecto tácito aquí significa que quien llame mal borra
    contenido sin querer o lo conserva sin querer, y ninguna de las dos es una
    equivocación de la que se salga fácil.
    """
    cuerpo = request.get_json(silent=True) or {}
    if "conservar_contenido" not in cuerpo:
        return jsonify(
            {
                "error": "modo_no_indicado",
                "mensaje": "Indica conservar_contenido: true (lápida) o false (borrado total)",
            }
        ), 400

    try:
        return jsonify(
            svc.eliminar_usuario(
                id_usuario,
                por=current_user,
                conservar_contenido=bool(cuerpo["conservar_contenido"]),
            )
        ), 200
    except svc.AdminError as exc:
        return jsonify({"error": exc.code, "mensaje": str(exc)}), _codigo(exc)


@bp.post("/api/usuarios/<int:id_usuario>/reclamacion")
@permiso_requerido("usuario:editar", "usuario:eliminar")
def resolver_reclamacion(id_usuario: int):
    """Aprueba o rechaza una solicitud de recuperar una cuenta dada de baja.

    Exige los dos permisos: aprobar entrega el contenido de una cuenta a quien
    la reclama, y equivocarse tiene el mismo alcance que un borrado. Quien
    puede hacer esto debería poder hacer ambas cosas.

    Como en la baja, el sentido va en el cuerpo y sin valor por defecto.
    """
    cuerpo = request.get_json(silent=True) or {}
    if "aprobar" not in cuerpo:
        return jsonify(
            {
                "error": "decision_no_indicada",
                "mensaje": "Indica aprobar: true o false",
            }
        ), 400
    try:
        return jsonify(
            svc.resolver_reclamacion(
                id_usuario, por=current_user, aprobar=bool(cuerpo["aprobar"])
            )
        ), 200
    except svc.AdminError as exc:
        return jsonify({"error": exc.code, "mensaje": str(exc)}), _codigo(exc)


# ---------------------------------------------------------------------------
# Gestión de contenido
# ---------------------------------------------------------------------------


@bp.get("/api/situaciones")
@permiso_requerido("situacion:listar_todas")
def situaciones():
    return jsonify(
        svc.listar_situaciones(
            id_usuario=request.args.get("id_usuario", type=int),
            estado=request.args.get("estado", type=str),
            limite=request.args.get("limite", default=svc.POR_PAGINA, type=int),
            desplazamiento=request.args.get("desplazamiento", default=0, type=int),
        )
    ), 200


@bp.delete("/api/situaciones/<int:id_situacion>")
@permiso_requerido("situacion:eliminar_cualquiera")
def eliminar_situacion(id_situacion: int):
    try:
        return jsonify(svc.eliminar_situacion(id_situacion, por=current_user)), 200
    except svc.AdminError as exc:
        return jsonify({"error": exc.code, "mensaje": str(exc)}), _codigo(exc)


def _codigo(exc: svc.AdminError) -> int:
    """Código HTTP para cada tipo de error del panel.

    Un diccionario y no una cadena de ``if``: cuando aparezca un error nuevo,
    olvidarse de asignarle código da 400, que es un fallo visible, y no un 200
    con cuerpo de error, que es el que se cuela.
    """
    return {
        "usuario_no_encontrado": 404,
        "situacion_no_encontrada": 404,
        "rol_inexistente": 422,
        "no_puedes_eliminarte": 409,
        "no_puedes_degradarte": 409,
        "sin_reclamacion": 409,
    }.get(exc.code, 400)
