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

#: La baja tiene dos modos y **un propósito distinto para cada uno**, en lugar
#: de un propósito único con el modo guardado dentro del token.
#:
#: Los dos servirían: el contenido del token también va firmado, así que nadie
#: puede cambiar el modo por el camino. Se eligen dos propósitos porque la
#: propiedad que importa —un enlace emitido para conservar el contenido no
#: puede acabar borrándolo todo— queda garantizada por el mismo mecanismo ya
#: probado que impide que un enlace de restablecimiento dé de baja una cuenta,
#: en vez de por una comprobación más que habría que acordarse de escribir.
PROPOSITO_BAJA_CONSERVANDO = "dar-de-baja-conservando"
PROPOSITO_BAJA_TOTAL = "dar-de-baja-total"

#: Confirmar un correo de respaldo, sea el primero o un cambio.
PROPOSITO_RESPALDO = "verificar-respaldo"

#: Aprobar desde el correo de respaldo la reclamación del contenido de una
#: cuenta dada de baja. Es el propósito **de la persona anterior**, no de quien
#: reclama: el enlace llega a su buzón personal.
PROPOSITO_RECLAMACION = "aprobar-reclamacion"

#: Una hora. Suficiente para ir al correo y volver, corto para que un enlace
#: olvidado en una bandeja compartida deje de servir pronto.
CADUCIDAD_RESTABLECER = 3600

#: Un día para confirmar el respaldo. Es más largo que los demás y no es un
#: descuido: aquí no hay nada destructivo que apurar —el respaldo no cambia
#: hasta que se confirma— y la dirección es una personal, que se mira con menos
#: frecuencia que la del trabajo. Una hora obligaría a repetir la petición a
#: quien lo pidiera un viernes por la tarde.
CADUCIDAD_RESPALDO = 86400

#: Una semana para aprobar una reclamación. Es con diferencia el plazo más
#: largo, y a propósito: el enlace llega a alguien que **ya no usa AWEBO** —se
#: dio de baja— y que por tanto no está pendiente de su bandeja por esto. Un
#: plazo corto obligaría a quien reclama a reintentarlo a ciegas, sin saber si
#: el anterior lo vio o no. Sigue habiendo tope porque el contenido se purga a
#: los 90 días de todos modos.
CADUCIDAD_RECLAMACION = 604800

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


def generar_baja(usuario, *, conservar_contenido: bool) -> str:
    """Token de un solo uso para confirmar la baja de ``usuario``.

    El modo va en el propósito, no en un parámetro que haya que volver a pasar
    al confirmar: así el enlace que llega al correo ya decide qué va a pasar, y
    no depende de lo que traiga la petición que lo abra.
    """
    return generar(
        usuario,
        PROPOSITO_BAJA_CONSERVANDO if conservar_contenido else PROPOSITO_BAJA_TOTAL,
    )


def leer_restablecimiento(token: str) -> int:
    """Atajo para el propósito de restablecimiento."""
    return leer(token, PROPOSITO_RESTABLECER, CADUCIDAD_RESTABLECER)


def generar_respaldo(usuario, correo_nuevo: str) -> str:
    """Token para confirmar ``correo_nuevo`` como respaldo de ``usuario``.

    LA DIRECCIÓN VA DENTRO DEL TOKEN
    ---------------------------------
    Y no en la base de datos esperando confirmación. Si se guardara antes de
    verificar, entre la petición y el clic habría un periodo en el que la
    cuenta tiene un respaldo a medias: ni sirve —no está verificado— ni se
    puede distinguir de uno bueno sin mirar dos columnas. Metida en el token,
    el respaldo **solo existe cuando ya está confirmado**, y no hay estado
    intermedio que alguien tenga que recordar tratar.

    Va firmada, así que quien reciba el enlace no puede cambiarla por otra.
    """
    return _serializador(PROPOSITO_RESPALDO).dumps({
        "id": usuario.id_usuario,
        "h": _huella(usuario),
        "c": correo_nuevo,
    })


def leer_respaldo(token: str) -> tuple[int, str]:
    """Devuelve ``(id_usuario, correo_a_confirmar)`` si el token vale."""
    from ..extensions import db
    from ..models import Usuario

    try:
        datos = _serializador(PROPOSITO_RESPALDO).loads(
            token, max_age=CADUCIDAD_RESPALDO
        )
    except SignatureExpired:
        raise TokenInvalido("caducado") from None
    except BadSignature:
        raise TokenInvalido("firma_invalida") from None

    if not isinstance(datos, dict) or not {"id", "h", "c"} <= set(datos):
        raise TokenInvalido("formato")

    usuario = db.session.get(Usuario, datos["id"])
    if usuario is None or usuario.esta_eliminado:
        raise TokenInvalido("usuario_inexistente")
    if not hmac.compare_digest(datos["h"], _huella(usuario)):
        raise TokenInvalido("ya_usado")
    return usuario.id_usuario, datos["c"]


def generar_reclamacion(usuario) -> str:
    """Token para que el dueño anterior apruebe la reclamación de su cuenta.

    Va ligado a la huella del hash **actual**, que es el de la persona
    anterior: si esa cuenta se recupera por otra vía —o le cambian la
    contraseña—, el enlace pendiente muere solo.
    """
    return generar(usuario, PROPOSITO_RECLAMACION)


def leer_reclamacion(token: str) -> int:
    """Como ``leer``, pero **aceptando cuentas con lápida**.

    No es un atajo a ``leer`` y no puede serlo. ``leer`` rechaza las cuentas
    dadas de baja, y con razón: restablecerle la contraseña a una cuenta con
    lápida no serviría de nada —el login la rechaza igual— y sería una forma de
    esquivar la reclamación de contenido.

    Aquí es al revés: **el sujeto del token es justamente una cuenta con
    lápida**. Reutilizar ``leer`` hacía que el enlace de aprobación fallara
    siempre con «usuario_inexistente», que es lo que pasó al escribirlo. La
    condición que allí protege, aquí impide lo único que se quiere hacer.

    Lo demás sí se comparte: firma, propósito, caducidad y la huella que mata
    el enlace si la contraseña de la cuenta anterior cambia.
    """
    from ..extensions import db
    from ..models import Usuario

    try:
        datos = _serializador(PROPOSITO_RECLAMACION).loads(
            token, max_age=CADUCIDAD_RECLAMACION
        )
    except SignatureExpired:
        raise TokenInvalido("caducado") from None
    except BadSignature:
        raise TokenInvalido("firma_invalida") from None

    if not isinstance(datos, dict) or "id" not in datos or "h" not in datos:
        raise TokenInvalido("formato")

    usuario = db.session.get(Usuario, datos["id"])
    if usuario is None:
        raise TokenInvalido("usuario_inexistente")
    if not hmac.compare_digest(datos["h"], _huella(usuario)):
        raise TokenInvalido("ya_usado")
    return usuario.id_usuario


def leer_baja(token: str) -> tuple[int, bool]:
    """Devuelve ``(id_usuario, conservar_contenido)`` si el token vale.

    Hay que probar los dos propósitos porque el enlace no dice cuál es —si lo
    dijera, se podría cambiar—. Se prueban en orden y solo se pasa al siguiente
    cuando el fallo es de **firma**, que es lo que significa «este token no era
    de este propósito».

    Un token caducado o ya usado se propaga tal cual en lugar de seguir
    probando: si se enmascarasen, un enlace caducado acabaría respondiendo
    «firma inválida», y ese mensaje manda a quien lo lea a buscar un problema
    que no existe.
    """
    modos = (
        (PROPOSITO_BAJA_CONSERVANDO, True),
        (PROPOSITO_BAJA_TOTAL, False),
    )
    for proposito, conservar in modos:
        try:
            return leer(token, proposito, CADUCIDAD_BAJA), conservar
        except TokenInvalido as exc:
            if exc.motivo != "firma_invalida":
                raise
    raise TokenInvalido("firma_invalida")


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
