"""Servicio de autenticación y registro de usuarios."""
from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
import structlog
from sqlalchemy import select

from ..extensions import db
from ..models import Rol, Usuario


log = structlog.get_logger(__name__)


class AuthError(Exception):
    """Error de autenticación / registro con tipo discriminado."""

    def __init__(self, code: str, message: str = "", **datos) -> None:
        super().__init__(message or code)
        self.code = code
        #: Contexto adicional para la respuesta. Lo usa
        #: ``contenido_reclamable`` para decir cuántas situaciones hay en
        #: juego: pedir a alguien que confirme que un contenido es suyo sin
        #: decirle de cuánto se trata es pedirle que confirme a ciegas.
        self.datos = datos


#: Longitud mínima. El mismo valor que declaran los esquemas Pydantic.
LONGITUD_MINIMA_CONTRASENA = 8


def validar_contrasena(valor: str) -> str:
    """Comprueba la política de contraseñas. Lanza ``ValueError`` si no cumple.

    Vive aquí y no en los esquemas porque un esquema solo protege el camino que
    pasa por él. La política estuvo duplicada en tres validadores Pydantic
    —``RegisterIn``, ``ResetPasswordIn`` y ``CrearUsuarioIn``— y ninguno cubría
    el comando ``flask usuarios crear-admin``, que creaba administradores con
    la contraseña que fuera. Un comentario en el CLI llegó a afirmar lo
    contrario; era falso.

    Los esquemas siguen llamándola, para que el error salga como un 422 con
    mensaje en vez de reventar más adentro, pero ``registrar_usuario`` la
    aplica igualmente: así ningún camino nuevo puede saltársela por descuido.
    """
    if len(valor) < LONGITUD_MINIMA_CONTRASENA:
        raise ValueError(
            f"La contraseña debe tener al menos {LONGITUD_MINIMA_CONTRASENA} caracteres"
        )
    if not any(c.isalpha() for c in valor):
        raise ValueError("La contraseña debe contener al menos una letra")
    if not any(c.isdigit() for c in valor):
        raise ValueError("La contraseña debe contener al menos un dígito")
    return valor


def registrar_usuario(
    *,
    correo: str,
    contrasena: str,
    nombre: str,
    centro_educativo: str | None = None,
    especialidad: str | None = None,
    comunidad_autonoma: str | None = None,
    provincia: str | None = None,
    rol_nombre: str = Rol.DOCENTE,
    reclamar_contenido: bool = False,
    correo_respaldo: str | None = None,
) -> Usuario:
    """Crea un nuevo usuario con el rol indicado (por defecto, docente).

    Si el correo pertenece a una cuenta con lápida **nunca crea ni revive
    nada**: registra una solicitud que un administrador debe aprobar. Ver
    ``_reclamar`` para el porqué.

    Si se da ``correo_respaldo`` **no se guarda**: se manda a esa dirección el
    enlace de confirmación, igual que si se pusiera desde el perfil. Guardarlo
    sin verificar sería peor que no tenerlo, porque cualquiera podría apuntar
    la dirección de otra persona al registrarse.

    Lanza ``AuthError`` con código ``correo_duplicado``, ``rol_inexistente``,
    ``contenido_reclamable`` (falta confirmar), ``reclamacion_pendiente``
    (solicitud registrada, a la espera de aprobación) o
    ``respaldo_igual_al_principal``.
    """
    correo_normalizado = correo.lower().strip()

    # Antes de tocar la base de datos: crear una cuenta con una contraseña que
    # no cumple y avisar después no sirve de nada.
    try:
        validar_contrasena(contrasena)
    except ValueError as exc:
        raise AuthError("contrasena_debil", str(exc)) from exc

    existente = db.session.scalar(
        select(Usuario).where(Usuario.correo == correo_normalizado)
    )
    if existente is not None and not existente.esta_eliminado:
        raise AuthError("correo_duplicado", "Ya existe un usuario con ese correo")

    rol = db.session.scalar(select(Rol).where(Rol.nombre == rol_nombre))
    if rol is None:
        raise AuthError("rol_inexistente", f"No existe el rol {rol_nombre!r}")

    # Se comprueba ANTES de crear nada. `respaldo.solicitar` rechaza igual esta
    # dirección, pero lo haría con la cuenta ya creada y confirmada: el
    # registro habría salido bien, el respaldo no, y nadie se enteraría hasta
    # buscar en el buzón un correo que nunca se envió.
    respaldo_normalizado = (correo_respaldo or "").strip().lower()
    if respaldo_normalizado and respaldo_normalizado == correo_normalizado:
        raise AuthError(
            "respaldo_igual_al_principal",
            "El correo de respaldo tiene que ser distinto del de la cuenta: si "
            "fuera el mismo no serviría para recuperarla.",
        )

    if existente is not None:
        # Lanza siempre: nunca devuelve un usuario con el que iniciar sesión.
        _reclamar(
            existente,
            rol=rol,
            contrasena=contrasena,
            nombre=nombre,
            centro_educativo=centro_educativo,
            especialidad=especialidad,
            comunidad_autonoma=comunidad_autonoma,
            confirmado=reclamar_contenido,
        )

    usuario = Usuario(
        id_rol=rol.id_rol,
        correo=correo_normalizado,
        nombre=nombre,
        centro_educativo=centro_educativo,
        especialidad=especialidad,
        comunidad_autonoma=comunidad_autonoma,
    )
    usuario.set_password(contrasena)

    # La provincia manda sobre la comunidad: si se da, se recalcula. Es lo que
    # permite que el formulario mande solo la provincia y no tenga que saber a
    # qué comunidad pertenece.
    if provincia:
        from . import geografia

        geografia.fijar_provincia(usuario, provincia)

    db.session.add(usuario)
    db.session.commit()

    # Atributo transitorio, no columna: vale solo para esta respuesta. Lo mira
    # el endpoint para decidir si manda a la persona a su buzón, y tiene que
    # decir lo que de verdad pasó, no lo que se pidió.
    usuario.respaldo_enviado = False

    if respaldo_normalizado:
        # Se hace después del commit y **sin deshacer el registro si falla**.
        # La cuenta ya es válida sin respaldo; tumbar un alta correcta porque
        # el correo no salió dejaría a la persona sin cuenta y sin entender por
        # qué. Si no llega, siempre puede añadirlo desde su perfil.
        #
        # Se capturan todas las excepciones y no solo `RespaldoError`, y eso lo
        # enseñó un test: con la cola caída saltaba un `RuntimeError` que se
        # llevaba por delante la petición entera. La cuenta quedaba creada, la
        # respuesta era un 500, y al reintentar salía «correo_duplicado». Es
        # decir, exactamente el desastre que este bloque decía evitar mientras
        # solo capturaba el error bonito.
        from . import respaldo as svc_respaldo

        try:
            svc_respaldo.solicitar(usuario, respaldo_normalizado)
            usuario.respaldo_enviado = True
        except Exception:
            log.warning(
                "respaldo_en_registro_no_enviado",
                id_usuario=usuario.id_usuario,
                exc_info=True,
            )

    return usuario


def _reclamar(
    usuario: Usuario,
    *,
    rol: Rol,
    contrasena: str,
    nombre: str,
    centro_educativo: str | None,
    especialidad: str | None,
    comunidad_autonoma: str | None,
    confirmado: bool,
) -> None:
    """Registra una **solicitud** de recuperar una cuenta con lápida.

    No devuelve nada ni deja entrar a nadie: lanza siempre ``AuthError``. La
    reclamación queda a la espera de que un administrador la apruebe desde el
    panel, y hasta entonces la cuenta sigue con su lápida.

    **Por qué no basta con que lo confirme quien se registra.** Ligar contenido
    por coincidencia de correo da por hecho que el correo identifica a una
    persona, y en centros educativos eso no siempre se cumple: una dirección
    como ``jlopez@iesejemplo.es`` puede reasignarse a otro Juan López cuando el
    primero se traslada. Una casilla de confirmación frena la reclamación
    accidental, pero no la deliberada — y quien hereda la dirección la marcaría
    igual, con toda la buena fe del mundo, creyendo que el contenido es suyo.

    El administrador es quien está en condiciones de saberlo: conoce el centro,
    puede preguntar. Por eso la aprobación es suya y no de quien reclama.

    Una versión anterior aplicaba los datos nuevos y levantaba la lápida en
    cuanto llegaba la confirmación. Se cambió por esto.
    """
    if not confirmado:
        raise AuthError(
            "contenido_reclamable",
            "Existe contenido de una cuenta anterior con este correo. "
            "Puedes solicitar recuperarlo; lo revisará un administrador.",
            situaciones=len(usuario.situaciones),
            dado_de_baja_el=(
                usuario.eliminado_en.isoformat() if usuario.eliminado_en else None
            ),
        )

    # Los datos se guardan SIN aplicarse. Aplicarlos ya y deshacerlo al
    # rechazar no es posible: el nombre y la contraseña anteriores se habrían
    # perdido, y son de la persona a la que se está protegiendo.
    #
    # Se guarda el hash, nunca la contraseña. Esta fila puede acabar en un
    # volcado de la base de datos o en el panel de administración.
    hash_temporal = bcrypt.hashpw(
        contrasena.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    usuario.reclamacion_pendiente = {
        "solicitada_en": datetime.now(timezone.utc).isoformat(),
        "nombre": nombre,
        "centro_educativo": centro_educativo,
        "especialidad": especialidad,
        "comunidad_autonoma": comunidad_autonoma,
        "contrasena_hash": hash_temporal,
        # El rol solicitado se fija aquí y NO se hereda del que tuviera la
        # cuenta. Si la anterior era administradora, heredarlo convertiría el
        # formulario público de registro en una escalada de privilegios:
        # bastaría con saber el correo de un administrador dado de baja.
        "rol": rol.nombre,
    }
    db.session.commit()

    log.info(
        "reclamacion_solicitada",
        correo=usuario.correo,
        situaciones=len(usuario.situaciones),
    )

    # Si la persona anterior dejó correo de respaldo, se le pregunta a ella:
    # es la única prueba de identidad que sobrevive al reciclaje de una
    # dirección institucional. El administrador queda como último recurso.
    from . import reclamacion as svc_reclamacion

    avisado = svc_reclamacion.avisar_al_respaldo(usuario)

    raise AuthError(
        "reclamacion_pendiente",
        (
            "Solicitud registrada. Hemos escrito a la persona que dio de baja "
            "esta cuenta para que lo autorice; si eres tú, revisa tu correo "
            "personal."
            if avisado else
            "Solicitud registrada. Un administrador debe aprobarla antes de "
            "que puedas acceder a la cuenta y a su contenido."
        ),
        situaciones=len(usuario.situaciones),
        # No se dice **a qué dirección** se ha escrito: sería contarle a quien
        # reclama cuál es el correo personal de otra persona.
        avisado_al_respaldo=bool(avisado),
    )


def resetear_contrasena(*, correo: str, nueva_contrasena: str) -> Usuario:
    """Cambia la contraseña de un usuario identificado por correo.

    Lanza ``AuthError`` con código ``usuario_no_encontrado`` si el correo
    no existe en la base de datos.
    """
    correo_normalizado = correo.lower().strip()
    usuario = db.session.scalar(
        select(Usuario).where(Usuario.correo == correo_normalizado)
    )
    if usuario is None or usuario.esta_eliminado:
        # La cuenta con lápida se trata como inexistente: cambiarle la
        # contraseña no serviría de nada —el login la rechaza igual— y daría
        # la impresión de haberla recuperado. El camino para volver es el
        # registro, con reclamación explícita del contenido.
        raise AuthError("usuario_no_encontrado", "No existe ningún usuario con ese correo")

    usuario.set_password(nueva_contrasena)
    db.session.commit()
    return usuario


def autenticar(correo: str, contrasena: str) -> Usuario:
    """Devuelve el usuario si las credenciales son válidas, si no ``AuthError``.

    Por seguridad, devolvemos el mismo error tanto si el correo no existe como
    si la contraseña es incorrecta (evita enumeración de cuentas).
    """
    correo_normalizado = correo.lower().strip()

    usuario = db.session.scalar(
        select(Usuario).where(Usuario.correo == correo_normalizado)
    )
    if usuario is None or not usuario.check_password(contrasena):
        raise AuthError("credenciales_invalidas", "Correo o contraseña incorrectos")

    if usuario.esta_eliminado:
        # Aquí sí se dice lo que pasa, en lugar del error genérico de arriba.
        # Aquel existe para no revelar qué correos están registrados; este no
        # revela nada nuevo, porque el registro ya responde «correo_duplicado»
        # ante un correo existente. A cambio, evita que alguien dado de baja se
        # pase media tarde probando contraseñas que son correctas.
        raise AuthError(
            "cuenta_eliminada",
            "Esta cuenta fue dada de baja. Puedes volver a registrarte con este correo.",
        )

    return usuario
