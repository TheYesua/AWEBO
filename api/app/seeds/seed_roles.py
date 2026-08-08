"""Carga los roles del sistema."""
from __future__ import annotations

from sqlalchemy import select

from ..extensions import db
from ..models import Rol


ROLES_INICIALES: list[dict] = [
    {
        "nombre": Rol.DOCENTE,
        "descripcion": "Profesional docente que crea y gestiona sus propias situaciones de aprendizaje.",
        "permisos": [
            "situacion:crear",
            "situacion:editar_propia",
            "situacion:eliminar_propia",
            "situacion:exportar_propia",
            "perfil:editar",
        ],
    },
    {
        "nombre": Rol.ADMINISTRADOR,
        "descripcion": "Administrador del sistema. Acceso completo a usuarios y contenido.",
        "permisos": [
            "usuario:listar",
            "usuario:crear",
            "usuario:editar",
            "usuario:eliminar",
            "rol:gestionar",
            "situacion:listar_todas",
            "situacion:eliminar_cualquiera",
        ],
    },
]


def seed_roles() -> dict[str, int]:
    """Inserta los roles iniciales si no existen ya. Idempotente."""
    creados = 0
    actualizados = 0
    for data in ROLES_INICIALES:
        rol = db.session.scalar(select(Rol).where(Rol.nombre == data["nombre"]))
        if rol is None:
            rol = Rol(**data)
            db.session.add(rol)
            creados += 1
        else:
            # Actualizamos descripción y permisos si cambiaron en el código fuente.
            rol.descripcion = data["descripcion"]
            rol.permisos = data["permisos"]
            actualizados += 1
    db.session.commit()
    return {"creados": creados, "actualizados": actualizados}
