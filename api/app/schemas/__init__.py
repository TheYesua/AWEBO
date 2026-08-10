"""Schemas Pydantic v2 para validación y serialización de la API."""
from .auth import (
    ConfirmarBajaIn,
    LoginIn,
    RegisterIn,
    RestablecerConTokenIn,
    ResetPasswordIn,
    SolicitarBajaIn,
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
    "ConfirmarBajaIn",
    "LoginIn",
    "SolicitarBajaIn",
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
