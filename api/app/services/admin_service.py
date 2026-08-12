"""Servicio del panel de administración.

**Principio rector: gestión sin lectura.** Nada de lo que hay aquí devuelve el
campo ``contenido`` de una SA, ni sus versiones, ni sus adaptaciones. El panel
permite gestionar —contar, filtrar, borrar— sin pasar por lo que las docentes
han escrito.

Conviene ser preciso sobre qué es esto y qué no. **No es una barrera de
seguridad**: ``situacion_service._verificar_propietario`` deja pasar a los
administradores, así que quien administra puede abrir cualquier SA desde la
aplicación normal. Se probó a cerrarlo y se descartó —dejaba a quien administra
sin poder reproducir un problema reportado—, y está anotado en el README.

Lo que hace este módulo es que la gestión **rutinaria** no obligue a pasar por
el contenido de nadie: borrar una cuenta inactiva o revisar cuántas SA hay no
tiene por qué implicar leer a nadie. La diferencia entre «no puede» y «no le
hace falta» es real, y aquí se sostiene lo segundo.

De lo que sí devuelve, el caso discutido fue el **título**. Se decidió
incluirlo: sin él, identificar una SA concreta para borrarla obliga a trabajar
con números de identificador, y en la práctica eso lleva a borrar la que no
era. La contrapartida es real —el título lo escribe la docente y puede ser
revelador— y por eso queda anotado: si algún día molesta, quitarlo es cambiar
una línea de ``_metadatos_sa``.
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import func, select

from ..extensions import db
from ..models import Rol, SituacionAprendizaje, Usuario


log = structlog.get_logger(__name__)


class AdminError(Exception):
    """Error de una operación del panel, con tipo discriminado."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


#: Alias de la definición canónica del modelo. Antes esta tupla repetía los
#: cinco estados uno a uno, lo que es exactamente lo que el comentario decía
#: estar evitando.
ESTADOS = SituacionAprendizaje.ESTADOS


def _conteo_por_estado(filtro=None) -> dict[str, int]:
    """Cuenta SA agrupadas por estado, opcionalmente acotado.

    Se parte de un diccionario con todos los estados a cero y se rellena con lo
    que devuelve el GROUP BY. Sin ese relleno previo, un estado sin ninguna SA
    no aparecería en el resultado y la interfaz mostraría huecos en lugar de
    ceros — que no es lo mismo: un hueco parece un fallo de carga.
    """
    consulta = select(
        SituacionAprendizaje.estado, func.count(SituacionAprendizaje.id_situacion)
    ).group_by(SituacionAprendizaje.estado)
    if filtro is not None:
        consulta = consulta.where(filtro)

    conteos = dict.fromkeys(ESTADOS, 0)
    for estado, cuantas in db.session.execute(consulta):
        # Un estado que no esté en ESTADOS solo puede venir de datos escritos
        # a mano contra la base de datos. Se cuenta igual, para que el total
        # cuadre con lo que hay de verdad.
        conteos[estado] = cuantas
    return conteos


def estadisticas_globales() -> dict[str, Any]:
    """Métricas de toda la plataforma."""
    por_estado = _conteo_por_estado()
    usuarios_vivos = db.session.scalar(
        select(func.count(Usuario.id_usuario)).where(Usuario.eliminado_en.is_(None))
    )
    usuarios_con_lapida = db.session.scalar(
        select(func.count(Usuario.id_usuario)).where(Usuario.eliminado_en.is_not(None))
    )
    return {
        "situaciones": {"total": sum(por_estado.values()), "por_estado": por_estado},
        "usuarios": {
            "activos": usuarios_vivos or 0,
            "dados_de_baja": usuarios_con_lapida or 0,
        },
    }


#: Cuántas filas devuelve una página por defecto, y el tope que se acepta.
#: Diez es lo que cabe en pantalla sin desplazarse; el tope existe para que un
#: ``?limite=999999`` no convierta un endpoint paginado en uno que no lo está.
POR_PAGINA = 10
LIMITE_MAXIMO = 100


def _acotar(limite: int) -> int:
    return max(1, min(limite, LIMITE_MAXIMO))


def estadisticas_por_usuario(
    *, limite: int = POR_PAGINA, desplazamiento: int = 0
) -> dict[str, Any]:
    """Las mismas métricas acotadas a cada docente, sin una consulta por cuenta.

    Los conteos se calculan en una **subconsulta** agrupada por propietario, y
    esa subconsulta se une por fuera al listado de cuentas. La versión obvia
    —``select(Usuario, *conteos).group_by(...)``— no funciona: ``Usuario.rol``
    es ``lazy="joined"``, así que seleccionar la entidad arrastra un JOIN con
    ``rol`` cuyas columnas Postgres exige en el GROUP BY. Agrupar primero y
    unir después deja la consulta externa sin GROUP BY, y la carga anticipada
    del rol vuelve a ser inofensiva.

    El ``outerjoin`` es lo que hace aparecer también a quien no tiene ninguna
    SA, que es justo a quien interesa ver para saber qué cuentas no se usan.

    Paginado: el total se devuelve aparte para que la interfaz sepa cuántas
    páginas hay.
    """
    conteos = (
        select(
            SituacionAprendizaje.id_usuario.label("id_usuario"),
            func.count(SituacionAprendizaje.id_situacion).label("total"),
            *[
                func.count(SituacionAprendizaje.id_situacion)
                .filter(SituacionAprendizaje.estado == estado)
                .label(estado)
                for estado in ESTADOS
            ],
        )
        .group_by(SituacionAprendizaje.id_usuario)
        .subquery()
    )

    total = db.session.scalar(select(func.count(Usuario.id_usuario))) or 0

    filas = db.session.execute(
        select(Usuario, conteos)
        .outerjoin(conteos, conteos.c.id_usuario == Usuario.id_usuario)
        # Las solicitudes de reclamación primero: son lo único del panel que
        # espera una decisión, y enterrarlas en la página 7 equivale a no
        # mostrarlas. Después, por correo, que da un orden estable — sin un
        # criterio determinista, dos páginas consecutivas pueden repetir y
        # omitir filas.
        .order_by(Usuario.reclamacion_pendiente.is_(None), Usuario.correo)
        .limit(_acotar(limite))
        .offset(max(0, desplazamiento))
    ).all()

    return {
        "total": total,
        "usuarios": [
            {
                **usuario_publico(fila[0]),
                "situaciones": {
                    # Sin ninguna SA no hay fila en la subconsulta y el LEFT
                    # JOIN deja NULL, no cero. La interfaz espera números.
                    "total": fila.total or 0,
                    "por_estado": {
                        estado: getattr(fila, estado) or 0 for estado in ESTADOS
                    },
                },
            }
            for fila in filas
        ],
    }


def indice_usuarios() -> list[dict[str, Any]]:
    """Pares id/correo de todas las cuentas, para el desplegable de filtro.

    Va aparte del listado paginado a propósito: si el filtro se rellenara con
    la página visible, solo se podría filtrar por las diez cuentas que se están
    viendo — que es justo lo contrario de para lo que sirve un filtro. La
    respuesta es ligera aunque haya miles de cuentas.
    """
    filas = db.session.execute(
        select(Usuario.id_usuario, Usuario.correo).order_by(Usuario.correo)
    ).all()
    return [{"id_usuario": f.id_usuario, "correo": f.correo} for f in filas]


def usuario_publico(usuario: Usuario) -> dict[str, Any]:
    """Datos de gestión de una cuenta. Sin hash de contraseña, obviamente."""
    return {
        "id_usuario": usuario.id_usuario,
        "correo": usuario.correo,
        "nombre": usuario.nombre,
        "centro_educativo": usuario.centro_educativo,
        "especialidad": usuario.especialidad,
        "comunidad_autonoma": usuario.comunidad_autonoma,
        "rol": usuario.rol.nombre if usuario.rol else None,
        "fecha_registro": usuario.fecha_registro.isoformat()
        if usuario.fecha_registro
        else None,
        "ultima_sesion": usuario.ultima_sesion.isoformat()
        if usuario.ultima_sesion
        else None,
        "eliminado_en": usuario.eliminado_en.isoformat()
        if usuario.eliminado_en
        else None,
        "gracia_vencida": usuario.gracia_vencida,
        # Se expone la solicitud SIN el hash de la contraseña. El panel
        # necesita saber quién reclama y desde cuándo para decidir; el hash es
        # un detalle de implementación que no pinta nada en una respuesta HTTP.
        "reclamacion_pendiente": _reclamacion_publica(usuario.reclamacion_pendiente),
    }


def _reclamacion_publica(solicitud: dict | None) -> dict | None:
    if not solicitud:
        return None
    return {
        clave: valor
        for clave, valor in solicitud.items()
        if clave != "contrasena_hash"
    }


def _metadatos_sa(sa: SituacionAprendizaje) -> dict[str, Any]:
    """Lo justo para identificar una SA y decidir si se borra.

    Deliberadamente **no** incluye ``contenido``, ``descripcion``,
    ``perfil_aula`` ni ``materiales_contexto``: los tres últimos son texto
    libre de la docente sobre su aula y su alumnado, que es exactamente lo que
    el panel no debe mostrar.
    """
    return {
        "id_situacion": sa.id_situacion,
        "titulo": sa.titulo,
        "materia": sa.materia,
        "curso": sa.curso,
        "estado": sa.estado,
        "id_usuario": sa.id_usuario,
        "correo_usuario": sa.usuario.correo if sa.usuario else None,
        "fecha_creacion": sa.fecha_creacion.isoformat() if sa.fecha_creacion else None,
        "fecha_modificacion": sa.fecha_modificacion.isoformat()
        if sa.fecha_modificacion
        else None,
    }


# ---------------------------------------------------------------------------
# Listado de contenido
# ---------------------------------------------------------------------------


def listar_situaciones(
    *, id_usuario: int | None = None, estado: str | None = None,
    limite: int = POR_PAGINA, desplazamiento: int = 0,
) -> dict[str, Any]:
    """Metadatos de SA, con filtros y paginación.

    Paginado desde el principio y no «cuando haga falta»: este listado no tiene
    cota natural —crece con cada SA de cada docente— y una consulta sin LIMIT
    sobre una tabla que crece sola es una bomba de relojería con temporizador
    largo. El total se devuelve aparte para que la interfaz pueda paginar.
    """
    condiciones = []
    if id_usuario is not None:
        condiciones.append(SituacionAprendizaje.id_usuario == id_usuario)
    if estado is not None:
        condiciones.append(SituacionAprendizaje.estado == estado)

    base = select(SituacionAprendizaje)
    if condiciones:
        base = base.where(*condiciones)

    total = db.session.scalar(
        select(func.count(SituacionAprendizaje.id_situacion)).where(*condiciones)
        if condiciones
        else select(func.count(SituacionAprendizaje.id_situacion))
    )

    filas = db.session.scalars(
        base.order_by(
            SituacionAprendizaje.fecha_modificacion.desc(),
            SituacionAprendizaje.id_situacion.desc(),
        )
        .limit(_acotar(limite))
        .offset(max(0, desplazamiento))
    ).all()

    return {"total": total or 0, "situaciones": [_metadatos_sa(sa) for sa in filas]}


def eliminar_situacion(id_situacion: int, *, por: Usuario) -> dict[str, Any]:
    """Borra una SA de cualquier usuario. No la lee.

    Se devuelven sus metadatos para que quien llama pueda decir qué se borró
    sin tener que consultarlo antes.
    """
    sa = db.session.get(SituacionAprendizaje, id_situacion)
    if sa is None:
        raise AdminError("situacion_no_encontrada", "No existe esa situación")

    datos = _metadatos_sa(sa)
    from . import audio as almacen_audio

    db.session.delete(sa)
    db.session.commit()
    # El audio no está en la base de datos: ningún cascade se lo lleva.
    almacen_audio.borrar_los_de(id_situacion)

    log.info(
        "admin_situacion_eliminada",
        actor=por.correo,
        id_situacion=id_situacion,
        propietario=datos["correo_usuario"],
    )
    return datos


# ---------------------------------------------------------------------------
# Gestión de cuentas
# ---------------------------------------------------------------------------


def editar_usuario(id_usuario: int, *, por: Usuario, **campos) -> dict[str, Any]:
    """Actualiza el perfil y, si se pide, el rol de una cuenta.

    Solo se tocan los campos presentes en ``campos``: mandar ``None`` en uno
    ausente borraría el valor que hubiera, y el formulario del panel no siempre
    envía todos.
    """
    usuario = db.session.get(Usuario, id_usuario)
    if usuario is None:
        raise AdminError("usuario_no_encontrado", "No existe esa cuenta")

    for atributo in ("nombre", "centro_educativo", "especialidad", "comunidad_autonoma"):
        if atributo in campos:
            setattr(usuario, atributo, campos[atributo])

    if "rol" in campos and campos["rol"]:
        rol = db.session.scalar(select(Rol).where(Rol.nombre == campos["rol"]))
        if rol is None:
            raise AdminError("rol_inexistente", f"No existe el rol {campos['rol']!r}")
        # Quitarse a uno mismo el rol de administrador deja la plataforma sin
        # nadie que pueda gestionarla si era el último. Se comprueba antes de
        # asignar, no después.
        if usuario.id_usuario == por.id_usuario and rol.nombre != Rol.ADMINISTRADOR:
            raise AdminError(
                "no_puedes_degradarte",
                "No puedes quitarte a ti mismo el rol de administrador",
            )
        usuario.id_rol = rol.id_rol

    db.session.commit()
    log.info("admin_usuario_editado", actor=por.correo, objetivo=usuario.correo)
    return usuario_publico(usuario)


def eliminar_usuario(
    id_usuario: int, *, por: Usuario, conservar_contenido: bool
) -> dict[str, Any]:
    """Da de baja una cuenta, en uno de los dos modos decididos.

    ``conservar_contenido=True`` pone la lápida: la cuenta deja de poder entrar
    y su contenido queda reclamable durante el plazo de gracia.
    ``False`` borra la fila, y el CASCADE se lleva el contenido de inmediato.

    Cuál usar no es indiferente en lo legal: si es la propia persona quien
    ejerce su derecho de supresión, conservar su contenido tres meses es
    difícil de justificar y el modo correcto es el borrado total. Conservar
    tiene sentido para la limpieza que inicia el administrador — una cuenta
    inactiva, un traslado— donde el trabajo hecho sí conviene no perderlo.
    """
    usuario = db.session.get(Usuario, id_usuario)
    if usuario is None:
        raise AdminError("usuario_no_encontrado", "No existe esa cuenta")

    # Sin esta guarda, un administrador puede dejar la plataforma sin acceso
    # de administración con dos clics y sin manera de deshacerlo desde la web.
    if usuario.id_usuario == por.id_usuario:
        raise AdminError(
            "no_puedes_eliminarte", "No puedes eliminar tu propia cuenta"
        )

    resumen = {
        "id_usuario": usuario.id_usuario,
        "correo": usuario.correo,
        "situaciones": len(usuario.situaciones),
        "modo": "lapida" if conservar_contenido else "total",
    }

    if conservar_contenido:
        usuario.marcar_eliminado()
        db.session.commit()
    else:
        # Igual que en `baja.confirmar`: los ids antes de borrar, y el audio
        # después. El volumen no lo alcanza ningún cascade.
        from . import audio as almacen_audio

        ids = [sa.id_situacion for sa in usuario.situaciones]
        db.session.delete(usuario)
        db.session.commit()
        for id_situacion in ids:
            almacen_audio.borrar_los_de(id_situacion)

    log.info("admin_usuario_eliminado", actor=por.correo, **resumen)
    return resumen


# ---------------------------------------------------------------------------
# Reclamaciones de contenido
# ---------------------------------------------------------------------------


def resolver_reclamacion(
    id_usuario: int, *, por: Usuario, aprobar: bool
) -> dict[str, Any]:
    """Aprueba o rechaza la solicitud de recuperar una cuenta con lápida.

    Es el punto donde una persona recupera el trabajo de una cuenta anterior,
    así que es también el punto donde se le podría entregar el de otra. La
    decisión es del administrador precisamente porque es quien puede
    comprobarlo: conoce el centro y puede preguntar. Quien reclama siempre
    creerá de buena fe que el contenido es suyo.

    Aprobar aplica los datos guardados y levanta la lápida. Rechazar solo borra
    la solicitud: el contenido sigue donde estaba, con su lápida, hasta que
    venza el plazo y lo purgue la tarea periódica.
    """
    usuario = db.session.get(Usuario, id_usuario)
    if usuario is None:
        raise AdminError("usuario_no_encontrado", "No existe esa cuenta")
    if not usuario.reclamacion_pendiente:
        raise AdminError(
            "sin_reclamacion", "Esa cuenta no tiene ninguna solicitud pendiente"
        )

    solicitud = usuario.reclamacion_pendiente
    resumen = {
        "id_usuario": usuario.id_usuario,
        "correo": usuario.correo,
        "situaciones": len(usuario.situaciones),
        "resultado": "aprobada" if aprobar else "rechazada",
    }

    # La aplicación vive en `services/reclamacion.py` porque ahora hay **dos**
    # vías que acaban aquí —el administrador y el correo de respaldo de la
    # persona anterior—, y dos copias de la asignación de campos acabarían
    # divergiendo. Ya pasó con la regla de `es_adaptacion`.
    from . import reclamacion as svc_reclamacion

    if aprobar:
        svc_reclamacion.aplicar(usuario)
    else:
        svc_reclamacion.descartar(usuario)
    db.session.commit()

    log.info("admin_reclamacion_resuelta", actor=por.correo, **resumen)
    return resumen
