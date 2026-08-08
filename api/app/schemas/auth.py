"""Schemas de entrada para los endpoints de autenticación."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    """Datos requeridos para registrar un nuevo usuario."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr
    contrasena: str = Field(min_length=8, max_length=128)
    nombre: str = Field(min_length=2, max_length=100)
    centro_educativo: str | None = Field(default=None, max_length=200)
    especialidad: str | None = Field(default=None, max_length=100)
    comunidad_autonoma: str | None = Field(default=None, max_length=50)

    # Confirmación de que el contenido de la cuenta anterior con este correo es
    # de quien se registra. Por defecto en falso: el primer intento siempre
    # rebota con «contenido_reclamable» y hay que reenviar el formulario con
    # esto a verdadero. Es un paso de más a cambio de no entregar el trabajo de
    # otra persona a quien haya heredado su dirección institucional.
    reclamar_contenido: bool = False

    @field_validator("contrasena")
    @classmethod
    def _password_complejidad(cls, v: str) -> str:
        # Delegado en el servicio: es la única copia de la política. Aquí sirve
        # para que el error salga como un 422 con mensaje legible.
        from ..services.auth_service import validar_contrasena

        return validar_contrasena(v)


class LoginIn(BaseModel):
    """Credenciales para iniciar sesión."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr
    contrasena: str = Field(min_length=1, max_length=128)


class ResetPasswordIn(BaseModel):
    """Datos para restablecer la contraseña directamente."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr
    nueva_contrasena: str = Field(min_length=8, max_length=128)

    @field_validator("nueva_contrasena")
    @classmethod
    def _password_complejidad(cls, v: str) -> str:
        # Delegado en el servicio: es la única copia de la política. Aquí sirve
        # para que el error salga como un 422 con mensaje legible.
        from ..services.auth_service import validar_contrasena

        return validar_contrasena(v)
