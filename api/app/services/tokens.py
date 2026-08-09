"""Tokens firmados para acciones que llegan por correo.

Dos acciones lo usan: restablecer la contraseña y darse de baja. Cada una con
su propósito y su caducidad; el propósito entra en la firma, así que un enlace
emitido para una **no vale** para la otra.

POR QUÉ FIRMADOS Y NO GUARDADOS EN LA BASE DE DATOS
---------------------------------------------------
Un token firmado lleva dentro lo que necesita —a quién pertenece y cuándo se
emitió— y la firma garantiza que nadie lo ha tocado. No hace falta una tabla,
ni limpiar los caducados, ni una consulta más en cada intento.

El precio habitual de esa decisión es que un token firmado **no se puede
invalidar**: sigue valiendo hasta que caduca, aunque ya se haya usado. Aquí
eso se resuelve sin estado, metiendo en el token una huella del hash actual de
la contraseña. Al restablecerla, el hash cambia, la huella deja de coincidir y
el token queda muerto en el mismo instante en que se usa. Es de un solo uso sin
guardar nada.

Ese mismo detalle da otra propiedad gratis: si alguien pide dos enlaces
seguidos, el primero que se use invalida el otro.
"""
from __future__ import annotations

import hashlib
import hmac

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


#: Distingue para qué sirve cada token. Sin esto, un token de restablecimiento
#: valdría para dar de baja la cuenta y al revés: la firma es la misma. El
#: propósito entra en la firma como «sal», así que un token emitido para una
#: acción no verifica contra la otra.
PROPOSITO_RESTABLECER = "restablecer-contrasena"
PROPOSITO_BAJA = "dar-de-baja"

#: Una hora. Suficiente para ir al correo y volver, corto para que un enlace
#: olvidado en una bandeja compartida deje de servir pronto.
CADUCIDAD_RESTABLECER = 3600

#: Media hora para la baja, y no una como el restablecimiento. Es la acción
#: más destructiva que un usuario puede pedir: cuanto menos tiempo ande el
#: enlace por un buzón, mejor. Quien se lo piense más de media hora, que vuelva
#: a pedirlo — el coste de repetirlo es un clic.
CADUCIDAD_BAJA = 1800


class TokenInvalido(Exception):
    """El token no es válido: caducado, manipulado o ya usado.

    Un solo error para los tres casos **a propósito**: distinguirlos le diría
    a quien prueba tokens al azar si va por buen camino.
    """

    def __init__(self, motivo: str = "token_invalido") -> None:
        self.motivo = motivo
        super().__init__(motivo)


def _serializador(proposito: str) -> URLSafeTimedSerializer:
    # La clave sale de SECRET_KEY: si se rota, todos los enlaces pendientes
    # dejan de valer, que es el comportamiento deseado.
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt=proposito
    )


def _huella(usuario) -> str:
    """Huella corta del hash de la contraseña actual.

    No es el hash: es un resumen de 16 caracteres. El token viaja por correo y
    acaba en registros de servidores intermedios, así que no debe llevar
    material derivado de la contraseña en forma reutilizable. Con 16 caracteres
    hexadecimales hay de sobra para detectar que el hash cambió, que es lo
    único que se pregunta.
    """
    return hashlib.sha256(usuario.contrasena_hash.encode("utf-8")).hexdigest()[:16]


def generar(usuario, proposito: str) -> str:
    """Token de un solo uso para ``usuario`` y una acción concreta."""
    return _serializador(proposito).dumps(
        {"id": usuario.id_usuario, "h": _huella(usuario)}
    )


def generar_restablecimiento(usuario) -> str:
    """Token de un solo uso para restablecer la contraseña de ``usuario``."""
    return generar(usuario, PROPOSITO_RESTABLECER)


def generar_baja(usuario) -> str:
    """Token de un solo uso para confirmar la baja de ``usuario``."""
    return generar(usuario, PROPOSITO_BAJA)


def leer_restablecimiento(token: str) -> int:
    """Atajo para el propósito de restablecimiento."""
    return leer(token, PROPOSITO_RESTABLECER, CADUCIDAD_RESTABLECER)


def leer_baja(token: str) -> int:
    """Atajo para el propósito de baja."""
    return leer(token, PROPOSITO_BAJA, CADUCIDAD_BAJA)


def leer(token: str, proposito: str, caducidad: int) -> int:
    """Devuelve el id del usuario si el token vale; si no, ``TokenInvalido``.

    Comprueba cuatro cosas, y las cuatro importan:

    * que la firma sea nuestra —descarta tokens inventados—;
    * que sea del propósito que se pide: un enlace de restablecimiento no
      puede dar de baja una cuenta;
    * que no haya pasado la caducidad;
    * que la huella siga coincidiendo con el hash actual, que es lo que hace
      que el token muera al usarse.
    """
    # Importes tardíos: a nivel de módulo crearían un ciclo con ``models``.
    from ..extensions import db
    from ..models import Usuario

    try:
        datos = _serializador(proposito).loads(token, max_age=caducidad)
    except SignatureExpired:
        raise TokenInvalido("caducado") from None
    except BadSignature:
        raise TokenInvalido("firma_invalida") from None

    if not isinstance(datos, dict) or "id" not in datos or "h" not in datos:
        raise TokenInvalido("formato")

    usuario = db.session.get(Usuario, datos["id"])
    if usuario is None or usuario.esta_eliminado:
        # La cuenta con lápida se trata como inexistente, igual que en
        # ``resetear_contrasena``: restablecerle la contraseña no serviría de
        # nada —el login la rechaza igual— y sería una forma de esquivar la
        # reclamación de contenido.
        raise TokenInvalido("usuario_inexistente")

    # Comparación en tiempo constante: la huella no es secreta, pero compararla
    # con `==` filtra por tiempo cuántos caracteres coinciden, y no cuesta nada
    # no filtrarlo.
    if not hmac.compare_digest(datos["h"], _huella(usuario)):
        raise TokenInvalido("ya_usado")

    return usuario.id_usuario
