"""Schemas Pydantic v2 para validación y serialización de la API."""
from .auth import (
    LoginIn,
    RegisterIn,
    RestablecerConTokenIn,
    ResetPasswordIn,
    SolicitarRestablecimientoIn,
)
from .situacion import (
    AdaptacionCreateIn,
    DuplicarIn,
    SituacionCreateIn,
    SituacionListItemOut,
    SituacionOut,
    SituacionUpdateIn,
    VersionOut,
)
from .sugerencia import PropuestaOut, SugerenciaIn, SugerenciaOut
from .usuario import UsuarioOut, UsuarioUpdateIn

__all__ = [
    "AdaptacionCreateIn",
    "LoginIn",
    "RegisterIn",
    "ResetPasswordIn",
    "RestablecerConTokenIn",
    "SolicitarRestablecimientoIn",
    "UsuarioOut",
    "UsuarioUpdateIn",
    "SituacionCreateIn",
    "SituacionUpdateIn",
    "SituacionOut",
    "SituacionListItemOut",
    "VersionOut",
    "DuplicarIn",
    "SugerenciaIn",
    "SugerenciaOut",
    "PropuestaOut",
]
