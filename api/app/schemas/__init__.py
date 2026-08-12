"""Schemas Pydantic v2 para validación y serialización de la API."""
from .auth import (
    AprobarReclamacionIn,
    ConfirmarBajaIn,
    ConfirmarRespaldoIn,
    PonerRespaldoIn,
    QuitarRespaldoIn,
    LoginIn,
    RegisterIn,
    RestablecerConTokenIn,
    ResetPasswordIn,
    SolicitarBajaIn,
    SolicitarRestablecimientoIn,
)
from .situacion import (
    AdaptacionCreateIn,
    AudioIn,
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
    "AudioIn",
    "AprobarReclamacionIn",
    "ConfirmarBajaIn",
    "ConfirmarRespaldoIn",
    "PonerRespaldoIn",
    "QuitarRespaldoIn",
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
