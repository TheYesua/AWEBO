"""Schemas Pydantic relacionados con la entidad Usuario."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UsuarioOut(BaseModel):
    """Representación pública del usuario (no expone hash de contraseña)."""

    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    correo: EmailStr
    nombre: str
    centro_educativo: str | None = None
    especialidad: str | None = None
    comunidad_autonoma: str | None = None
    proveedor_ia: str | None = None
    modelo_ia: str | None = None
    idioma_interfaz: str | None = None
    fecha_registro: datetime
    ultima_sesion: datetime | None = None
    rol: str = Field(description="Nombre del rol del usuario")

    @classmethod
    def from_model(cls, usuario) -> "UsuarioOut":
        """Construye desde un objeto SQLAlchemy ``Usuario`` aplanando el rol."""
        return cls(
            id_usuario=usuario.id_usuario,
            correo=usuario.correo,
            nombre=usuario.nombre,
            centro_educativo=usuario.centro_educativo,
            especialidad=usuario.especialidad,
            comunidad_autonoma=usuario.comunidad_autonoma,
            proveedor_ia=usuario.proveedor_ia,
            modelo_ia=usuario.modelo_ia,
            idioma_interfaz=usuario.idioma_interfaz,
            fecha_registro=usuario.fecha_registro,
            ultima_sesion=usuario.ultima_sesion,
            rol=usuario.rol.nombre,
        )


class UsuarioUpdateIn(BaseModel):
    """Campos editables por el propio usuario en su perfil."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    centro_educativo: str | None = Field(default=None, max_length=200)
    especialidad: str | None = Field(default=None, max_length=100)
    comunidad_autonoma: str | None = Field(default=None, max_length=50)

    # Preferencia de IA. Cadena vacía o null = «usar el del sistema».
    # No se restringen aquí con un Literal: el conjunto de proveedores válidos
    # depende de la configuración del despliegue, así que la validación real
    # la hace ``app.ai.catalogo.validar`` contra lo que haya disponible.
    proveedor_ia: str | None = Field(default=None, max_length=20)
    modelo_ia: str | None = Field(default=None, max_length=80)

    # Idioma de la interfaz. Se valida contra IDIOMAS en el endpoint y no con
    # un Literal aquí, para que la lista de idiomas ofrecidos viva en un solo
    # sitio (app/i18n.py) y no haya que tocar dos ficheros al añadir uno.
    idioma_interfaz: str | None = Field(default=None, max_length=5)
