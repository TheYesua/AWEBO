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


class SolicitarRestablecimientoIn(BaseModel):
    """Solo el correo. No lleva contraseña a propósito.

    Quien pide el enlace todavía no elige nada: elegir contraseña ocurre
    después, ya con el token en la mano. Aceptar aquí una contraseña sería
    volver al modelo anterior con un paso más de decorado.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    correo: EmailStr


class RestablecerConTokenIn(BaseModel):
    """El token del enlace y la contraseña nueva.

    Ya no se pide el correo: el token dice a quién pertenece. Pedirlo además
    sería redundante y abriría la puerta a usar un token válido contra otra
    cuenta si algún día alguien programa mal la comprobación.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str = Field(min_length=10, max_length=1024)
    nueva_contrasena: str = Field(min_length=8, max_length=128)


class SolicitarBajaIn(BaseModel):
    """Petición de baja desde el perfil: contraseña actual y modo.

    ``conservar_contenido`` **no tiene valor por defecto** a propósito. Los dos
    modos hacen cosas muy distintas —uno se puede deshacer durante 90 días y el
    otro no—, así que un cuerpo que se olvide del campo debe rebotar en vez de
    elegir por su cuenta. Cualquier defecto que pusiéramos sería el equivocado
    la mitad de las veces, y en la mitad irreversible.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    contrasena: str = Field(min_length=1, max_length=128)
    conservar_contenido: bool


class ConfirmarBajaIn(BaseModel):
    """Solo el token del enlace.

    El modo no se pide: viaja firmado dentro del token. Aceptarlo aquí
    permitiría que quien pidió conservar su contenido acabara borrándolo todo
    por manipular la petición.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: str = Field(min_length=10, max_length=1024)
