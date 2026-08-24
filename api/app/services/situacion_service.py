"""Servicio de aplicación para Situaciones de Aprendizaje.

Aísla la lógica de negocio (autorización, versionado, duplicación) de la capa
HTTP. Los blueprints solo orquestan: validan entrada, llaman al servicio y
serializan la salida.
"""
from __future__ import annotations

import copy
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Query

from ..extensions import db
from . import enlaces_curriculares as svc_enlaces
from . import geografia
from ..curriculo import provincias as cat_provincias
from ..models import (
    Competencia,
    CriterioEvaluacion,
    EleccionPropuesta,
    SaberBasico,
    SituacionAprendizaje,
    Usuario,
    Version,
)


log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Errores propios
# ---------------------------------------------------------------------------


class SituacionError(Exception):
    """Error de dominio para operaciones sobre situaciones de aprendizaje."""

    def __init__(self, code: str, message: str = "", http_status: int = 400) -> None:
        super().__init__(message or code)
        self.code = code
        self.http_status = http_status


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


# Campos que se incluyen en el snapshot de versión (toda la "carga" del SA).
_CAMPOS_VERSIONABLES = (
    "titulo",
    "curso",
    "materia",
    "comunidad_autonoma",
    # Va con la comunidad, y por el mismo motivo que en todas partes: si solo
    # se guardara una de las dos, el historial mostraría un cambio de comunidad
    # sin decir de dónde salió. Hoy nada restaura la SdA campo a campo —solo se
    # devuelve `contenido`—, así que esto es para que la versión CUENTE lo que
    # pasó, que es lo único para lo que se mira.
    "provincia",
    "descripcion",
    "metodologia",
    "num_sesiones",
    "duracion_sesion_minutos",
    "idioma",
    "perfil_aula",
    "materiales_contexto",
    "contenido",
    "estado",
    "tipo_adaptacion",
    "perfil_alumnado",
)


def _snapshot(sa: SituacionAprendizaje) -> dict[str, Any]:
    """Devuelve un dict serializable con el estado actual del SA."""
    return {campo: copy.deepcopy(getattr(sa, campo)) for campo in _CAMPOS_VERSIONABLES}


def _verificar_propietario(sa: SituacionAprendizaje, usuario: Usuario) -> None:
    """El dueño, o cualquier administrador.

    **Decisión tomada y revisada dos veces**, así que conviene dejar claro el
    porqué. Se probó a cerrarlo —que un administrador no pudiera abrir la SA de
    otra persona— y el resultado fue peor de lo que parecía sobre el papel:
    quien administra deja de poder reproducir un problema que le reportan, y en
    una plataforma que administra su propia autora eso es fricción sin
    contrapartida real.

    Lo que **no** se hace es prometer lo contrario. El README dice que los
    administradores acceden al contenido, y el panel es lo que es: una
    herramienta de gestión que muestra metadatos, no una barrera. Ver el
    docstring de ``admin_service``.
    """
    if usuario.es_administrador:
        if sa.id_usuario != usuario.id_usuario:
            # LA TRAZA DE LECTURA, y va aquí por un motivo concreto.
            #
            # Este es el único punto por el que pasa un administrador para
            # tocar contenido ajeno: abrirlo, editarlo, exportarlo, generar
            # audio. Ponerlo en `obtener` habría dejado fuera todo lo demás, y
            # ponerlo en cada endpoint habría durado hasta el siguiente
            # endpoint. Un cuello de botella no se puede olvidar.
            #
            # Registrar accesos era una de las tres condiciones con las que se
            # aceptó que el administrador pudiera leerlo todo (decisión del
            # 10/08/2026). Sin ella el panel sería una puerta silenciosa: las
            # otras dos —decirlo en Ayuda y advertirlo en el registro— avisan
            # de que la puerta existe; esta es la que deja constancia de cuándo
            # se usa.
            log.info(
                "admin_accede_a_contenido_ajeno",
                id_situacion=sa.id_situacion,
                id_administrador=usuario.id_usuario,
                id_propietario=sa.id_usuario,
            )
        return
    if sa.id_usuario != usuario.id_usuario:
        raise SituacionError("permiso_denegado", http_status=403)


def _proximo_numero_version(id_situacion: int) -> int:
    """Calcula el siguiente número de versión secuencial."""
    actual = db.session.scalar(
        select(db.func.max(Version.numero_version)).where(
            Version.id_situacion == id_situacion
        )
    )
    return (actual or 0) + 1


# ---------------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------------


def crear(usuario: Usuario, datos: dict[str, Any]) -> SituacionAprendizaje:
    """Crea una nueva situación de aprendizaje propiedad del usuario dado.

    **La provincia se hereda del perfil si no viene en los datos**, y de ella
    se deriva la comunidad. Antes daba
    igual —el campo era descriptivo y nadie filtraba por él—, pero desde que
    decide qué currículo se aplica, una SdA sin comunidad es una SdA sin
    currículo: la generación se rechaza y el docente no entiende por qué, si en
    su perfil pone bien de dónde es.

    Se hereda, no se impone: quien mande una comunidad explícita —porque da
    clase en dos sitios, o está preparando material para otra— se queda con la
    suya.
    """
    provincia = datos.pop("provincia", None) or usuario.provincia
    datos.pop("comunidad_autonoma", None)   # se calcula, no se acepta suelta

    sa = SituacionAprendizaje(id_usuario=usuario.id_usuario, **datos)

    # La provincia se escribe con el servicio, que es el único sitio que fija
    # las dos columnas a la vez. Asignarla a mano dejaría `comunidad_autonoma`
    # con lo que hubiera antes, y una SdA que dice ser de Sevilla generando con
    # el currículo de otra comunidad no tiene forma de detectarse después.
    geografia.fijar_provincia(sa, provincia)
    if sa.provincia is None:
        # Sin provincia reconocible se conserva la comunidad del perfil, que es
        # lo que tienen las cuentas anteriores a que existiera este campo.
        sa.comunidad_autonoma = usuario.comunidad_autonoma

    db.session.add(sa)
    db.session.commit()
    return sa


#: Situaciones por página en el listado del docente. El mismo número que usa
#: el panel de administración: es lo que cabe en pantalla sin desplazarse.
POR_PAGINA = 10
LIMITE_MAXIMO = 100


def _filtros_listado(
    usuario: Usuario,
    *,
    curso: str | None,
    materia: str | None,
    estado: str | None,
    q: str | None,
    incluir_adaptaciones: bool,
    provincia: str | None = None,
) -> list:
    """Condiciones WHERE del listado, compartidas por la página y el conteo.

    Existe para que ``listar`` y ``contar`` no puedan divergir: si los filtros
    se escribieran dos veces, el total mostraría un número que no corresponde a
    las filas que se están viendo, y nadie lo notaría hasta que alguien
    contase las páginas.
    """
    # Los administradores ven todas; el resto, solo las suyas. Es coherente con
    # ``_verificar_propietario``: si pueden abrirlas, ocultarlas del listado
    # solo obligaría a llegar a ellas escribiendo la URL a mano.
    condiciones = []
    if not usuario.es_administrador:
        condiciones.append(SituacionAprendizaje.id_usuario == usuario.id_usuario)
    # La provincia FILTRA, no solo acota el desplegable de materias.
    #
    # Al montar el selector el 15/08 se decidió que no viajara al servidor,
    # razonando que solo servía para decidir qué materias ofrecer. Era un
    # razonamiento sobre el mecanismo, no sobre lo que espera quien lo usa:
    # elegir «Barcelona» y ver las SdA de Sevilla es sencillamente un filtro
    # que no filtra. Y el desconcierto crecía porque **sí** parecía funcionar
    # en cuanto se añadía un curso.
    if provincia:
        condiciones.append(SituacionAprendizaje.provincia == provincia)
    if curso:
        condiciones.append(SituacionAprendizaje.curso == curso)
    if materia:
        condiciones.append(SituacionAprendizaje.materia == materia)
    if estado:
        condiciones.append(SituacionAprendizaje.estado == estado)
    if q:
        condiciones.append(SituacionAprendizaje.titulo.ilike(f"%{q}%"))
    if not incluir_adaptaciones:
        condiciones.append(SituacionAprendizaje.id_situacion_origen.is_(None))
    return condiciones


def listar(
    usuario: Usuario,
    *,
    curso: str | None = None,
    materia: str | None = None,
    estado: str | None = None,
    q: str | None = None,
    incluir_adaptaciones: bool = True,
    provincia: str | None = None,
    limit: int = POR_PAGINA,
    offset: int = 0,
) -> list[SituacionAprendizaje]:
    """Lista las situaciones del usuario aplicando los filtros indicados.

    Los administradores ven todas; el resto solo las suyas.

    Ordena por fecha **y por identificador**: dos situaciones guardadas en el
    mismo instante empatan, y con un orden no determinista una misma fila puede
    salir en dos páginas mientras otra no sale en ninguna.
    """
    condiciones = _filtros_listado(
        usuario,
        curso=curso,
        materia=materia,
        estado=estado,
        q=q,
        incluir_adaptaciones=incluir_adaptaciones,
        provincia=provincia,
    )
    stmt = (
        select(SituacionAprendizaje)
        .where(*condiciones)
        .order_by(
            SituacionAprendizaje.fecha_modificacion.desc(),
            SituacionAprendizaje.id_situacion.desc(),
        )
        .limit(max(1, min(limit, LIMITE_MAXIMO)))
        .offset(max(0, offset))
    )
    return list(db.session.scalars(stmt).all())


def contar(
    usuario: Usuario,
    *,
    curso: str | None = None,
    materia: str | None = None,
    estado: str | None = None,
    q: str | None = None,
    incluir_adaptaciones: bool = True,
    provincia: str | None = None,
) -> int:
    """Cuántas situaciones devolvería ``listar`` sin límite de página."""
    condiciones = _filtros_listado(
        usuario,
        curso=curso,
        materia=materia,
        estado=estado,
        q=q,
        incluir_adaptaciones=incluir_adaptaciones,
        provincia=provincia,
    )
    return (
        db.session.scalar(
            select(func.count(SituacionAprendizaje.id_situacion)).where(*condiciones)
        )
        or 0
    )


def resumen_por_estado(usuario: Usuario) -> dict[str, int]:
    """Cuántas situaciones tiene el usuario en cada estado.

    Se cuenta en la base de datos y no recorriendo el listado en el navegador,
    que es como se hacía: el dashboard pedía las SA y las contaba en
    JavaScript, así que al paginar el listado el desglose pasó a calcularse
    sobre la primera página. Con 23 situaciones mostraba «10».

    Devuelve todos los estados, también los que están a cero: un hueco en la
    interfaz parece un fallo de carga, y un cero informa.
    """
    conteos = dict.fromkeys(SituacionAprendizaje.ESTADOS, 0)

    filas = db.session.execute(
        select(
            SituacionAprendizaje.estado,
            func.count(SituacionAprendizaje.id_situacion),
        )
        .where(*_filtros_listado(
            usuario, curso=None, materia=None, estado=None, q=None,
            incluir_adaptaciones=True,
        ))
        .group_by(SituacionAprendizaje.estado)
    )
    for estado, cuantas in filas:
        conteos[estado] = cuantas

    conteos["total"] = sum(conteos.values())
    return conteos


def obtener(id_situacion: int, usuario: Usuario) -> SituacionAprendizaje:
    """Devuelve la situación si el usuario tiene acceso, o lanza error."""
    sa = db.session.get(SituacionAprendizaje, id_situacion)
    if sa is None:
        raise SituacionError("no_encontrada", http_status=404)
    _verificar_propietario(sa, usuario)
    return sa


def actualizar(
    id_situacion: int,
    usuario: Usuario,
    cambios: dict[str, Any],
) -> SituacionAprendizaje:
    """Aplica los cambios y crea una nueva Version con el estado **previo**.

    De este modo, la última versión guardada siempre representa la situación
    inmediatamente antes del último guardado, lo que permite restaurar.
    """
    sa = obtener(id_situacion, usuario)

    descripcion_cambio = cambios.pop("descripcion_cambio", None)

    # La comunidad se deriva de la provincia; aceptarla suelta permitiría
    # dejar las dos columnas contando cosas distintas. El esquema la acepta
    # para no romper clientes que la sigan mandando, y aquí se descarta.
    cambios.pop("comunidad_autonoma", None)
    provincia = cambios.pop("provincia", None)

    # Se valida ANTES de tocar nada. `fijar_provincia` limpia las dos columnas
    # cuando no reconoce el valor, así que llamarla y luego lanzar dejaría el
    # objeto ya modificado en la sesión, a merced de que alguien haga rollback.
    # Y se rechaza en vez de limpiar porque al editar, a diferencia de al
    # crear, quedarse sin provincia significa perder la que ya tenía.
    if provincia is not None and cat_provincias.normalizar(provincia) is None:
        raise SituacionError(
            "provincia_no_reconocida",
            f"La provincia '{provincia}' no está en el catálogo.",
            http_status=422,
        )

    # Los estados "generando" y "error_generacion" son gestionados por el
    # backend (tarea de generación). El docente puede pasar a "borrador",
    # "generada" o "finalizada" manualmente, pero no reclamar un estado
    # transitorio/error.
    nuevo_estado = cambios.get("estado")
    if nuevo_estado in (SituacionAprendizaje.GENERANDO, SituacionAprendizaje.ERROR_GENERACION):
        raise SituacionError(
            "estado_no_editable_manualmente",
            "El estado 'generando'/'error_generacion' lo gestiona el backend.",
            http_status=409,
        )

    if not cambios and provincia is None:
        return sa  # nada que hacer; no creamos versión vacía

    # 1) Snapshot del estado actual ANTES de aplicar los cambios
    version = Version(
        id_situacion=sa.id_situacion,
        numero_version=_proximo_numero_version(sa.id_situacion),
        contenido=_snapshot(sa),
        descripcion_cambio=descripcion_cambio,
    )
    db.session.add(version)

    # 2) Aplicar cambios sobre la situación
    for campo, valor in cambios.items():
        setattr(sa, campo, valor)

    # La provincia NO se asigna con `setattr` como las demás: escribe dos
    # columnas —ella y la comunidad derivada— y hacerlo a mano dejaría la
    # comunidad anterior puesta. Una SdA que dice ser de Sevilla generando con
    # el currículo de Cataluña no se detecta después: los dos campos son
    # plausibles por separado.
    if provincia is not None:
        geografia.fijar_provincia(sa, provincia)   # validada más arriba

    db.session.commit()
    return sa


def reasignar_curriculo(
    sa: SituacionAprendizaje, *, materia: str, curso: str, motivo: str
) -> SituacionAprendizaje:
    """Cambia la materia y el curso de una SdA, guardando antes una versión.

    PARA QUÉ EXISTE
    ---------------
    Hay SdA creadas en la época del TFG, antes de que el formulario validara
    que la pareja (materia, curso) existiera. Quedaron ancladas a combinaciones
    imposibles: `Matemáticas · 4º ESO` —en 4º hay A y B—,
    `Tecnología y Digitalización · 4º ESO` —solo se imparte en 2º y 3º— y
    `Lengua Castellana y Literatura`, que en el catálogo se llama `Lengua`.

    POR QUÉ NO ES UN `UPDATE` Y YA
    -------------------------------
    Porque **guarda una versión con el estado anterior**. Son documentos de
    trabajo de alguien, no filas de prueba: si la reasignación resulta
    equivocada, hay a dónde volver. Es la misma red que usa `actualizar`.

    No es lo mismo que `actualizar`: aquella comprueba permisos de usuario y
    esta se llama desde la consola, donde no hay sesión. Se mantienen
    separadas en vez de añadirle un parámetro «sáltate el permiso», que es
    justo la clase de puerta trasera que acaba usándose desde un endpoint.

    LO QUE NO HACE
    --------------
    No toca el contenido. Los códigos del JSONB siguen siendo los del currículo
    equivocado, así que hasta regenerarla la SdA sigue citando criterios que no
    le corresponden. Quien llama decide si regenera; el comando de la consola
    avisa de ello.
    """
    version = Version(
        id_situacion=sa.id_situacion,
        numero_version=_proximo_numero_version(sa.id_situacion),
        contenido=_snapshot(sa),
        descripcion_cambio=motivo,
    )
    db.session.add(version)

    sa.materia = materia
    sa.curso = curso
    db.session.commit()

    log.info(
        "curriculo_reasignado",
        id_situacion=sa.id_situacion,
        materia=materia,
        curso=curso,
    )
    return sa


def eliminar(id_situacion: int, usuario: Usuario) -> None:
    """Elimina la situación, sus versiones por cascade y su audio.

    El audio vive en un volumen, no en la base de datos, así que ningún
    `cascade` se lo lleva: hay que borrarlo a mano o el volumen acumularía
    ficheros de situaciones que ya no existen — invisibles y creciendo.
    """
    from . import audio as almacen_audio

    sa = obtener(id_situacion, usuario)
    db.session.delete(sa)
    db.session.commit()
    almacen_audio.borrar_los_de(id_situacion)


def duplicar(
    id_situacion: int,
    usuario: Usuario,
    nuevo_titulo: str | None = None,
) -> SituacionAprendizaje:
    """Crea una copia independiente de la situación dada.

    El usuario que duplica pasa a ser el dueño. La copia arranca como
    ``borrador`` y sin historial de versiones (es una nueva situación).
    """
    original = obtener(id_situacion, usuario)

    titulo = nuevo_titulo or f"{original.titulo} (copia)"
    copia = SituacionAprendizaje(
        id_usuario=usuario.id_usuario,
        titulo=titulo,
        curso=original.curso,
        materia=original.materia,
        comunidad_autonoma=original.comunidad_autonoma,
        descripcion=original.descripcion,
        metodologia=original.metodologia,
        num_sesiones=original.num_sesiones,
        duracion_sesion_minutos=original.duracion_sesion_minutos,
        idioma=original.idioma,
        perfil_aula=original.perfil_aula,
        materiales_contexto=original.materiales_contexto,
        contenido=copy.deepcopy(original.contenido),
        estado=SituacionAprendizaje.BORRADOR,
        # No heredamos id_situacion_origen ni tipo_adaptacion: una "copia"
        # no es una "adaptación curricular" (que se modela aparte).
    )
    db.session.add(copia)
    db.session.commit()
    return copia


def listar_versiones(id_situacion: int, usuario: Usuario) -> list[Version]:
    """Devuelve el historial de versiones ordenado descendentemente."""
    sa = obtener(id_situacion, usuario)
    return sorted(sa.versiones, key=lambda v: v.numero_version, reverse=True)


def restaurar_seccion(
    id_situacion: int, usuario: Usuario, seccion: str
) -> SituacionAprendizaje:
    """Devuelve una sección al contenido de la última versión guardada.

    Es el «deshacer» de las operaciones de bloque. Restaura **solo** esa
    sección, no la SA entera: si el docente resume un bloque y luego edita
    otro, deshacer el resumen no debe llevarse por delante la edición.

    Se apoya en el historial que ya existía para el CRUD, así que no hay dos
    mecanismos de versionado compitiendo.
    """
    sa = obtener(id_situacion, usuario)

    versiones = sorted(sa.versiones, key=lambda v: v.numero_version, reverse=True)
    for version in versiones:
        anterior = (version.contenido or {}).get("contenido") or {}
        if seccion in anterior:
            contenido = dict(sa.contenido or {})
            contenido[seccion] = anterior[seccion]
            sa.contenido = contenido
            if seccion == "conexion_curricular":
                svc_enlaces.sincronizar(sa, commit=False)
            db.session.commit()
            return sa

    raise SituacionError(
        "sin_version_previa",
        f"No hay ninguna versión guardada de la sección «{seccion}» a la que volver.",
        http_status=404,
    )


def elegir_propuesta(
    id_situacion: int, usuario: Usuario, seccion: str, cual: str
) -> SituacionAprendizaje:
    """Resuelve una doble propuesta quedándose con una de las dos redacciones.

    :param cual: ``"actual"`` o ``"alternativa"``.

    La descartada **no se pierde**: antes de resolver se guarda una versión con
    ambas, así que se puede volver a ella. Y la elección se registra en
    :class:`EleccionPropuesta` con la procedencia de las dos candidatas — es la
    única forma de saber después qué prompt produce mejores redacciones, y ese
    dato no se puede reconstruir a posteriori.
    """
    if cual not in ("actual", "alternativa"):
        raise SituacionError(
            "eleccion_invalida",
            "Hay que elegir entre «actual» y «alternativa».",
        )

    sa = obtener(id_situacion, usuario)
    bloque = (sa.contenido or {}).get(seccion)
    if not isinstance(bloque, dict) or not isinstance(bloque.get("_alternativa"), dict):
        raise SituacionError(
            "sin_alternativa",
            f"La sección «{seccion}» no tiene ninguna alternativa pendiente de elegir.",
            http_status=404,
        )

    alternativa = bloque["_alternativa"]
    actual = {k: v for k, v in bloque.items() if k != "_alternativa"}

    gana, pierde = (
        (alternativa, actual) if cual == "alternativa" else (actual, alternativa)
    )
    meta_gana = gana.get("_meta", {}) or {}
    meta_pierde = pierde.get("_meta", {}) or {}

    # Snapshot con las DOS candidatas todavía presentes: es lo que permite
    # recuperar la descartada si el docente se arrepiente.
    version = Version(
        id_situacion=sa.id_situacion,
        numero_version=_proximo_numero_version(sa.id_situacion),
        contenido=_snapshot(sa),
        descripcion_cambio=f"Elección en «{seccion}»: se queda la {cual}",
    )
    db.session.add(version)

    db.session.add(
        EleccionPropuesta(
            id_situacion=sa.id_situacion,
            id_usuario=usuario.id_usuario,
            seccion=seccion,
            # La versión del prompt de sección, no la de la operación: lo que
            # se quiere medir es qué redacción gana, y de dónde salió.
            variante_elegida=str(meta_gana.get("version_prompt") or "?"),
            variante_descartada=str(meta_pierde.get("version_prompt") or "?"),
            posicion_elegida=cual,
            meta_elegida=meta_gana,
            meta_descartada=meta_pierde,
        )
    )

    contenido = dict(sa.contenido or {})
    ganadora = {k: v for k, v in gana.items() if k != "_alternativa"}
    contenido[seccion] = ganadora
    sa.contenido = contenido
    if seccion == "conexion_curricular":
        svc_enlaces.sincronizar(sa, commit=False)
    db.session.commit()
    return sa


def materias_con_curriculo(curso: str, comunidad: str | None = None) -> list[str]:
    """Materias con currículo completo para ``curso``, en orden alfabético.

    Se usa para que el mensaje de error no se limite a decir que algo falta,
    sino a nombrar lo que sí existe: ante «Matemáticas · 4º ESO» el docente
    necesita enterarse de que sus opciones son «Matemáticas A» y
    «Matemáticas B».

    **Y por eso hay que filtrar por comunidad aquí también.** Sin ello, a un
    docente de Ceuta se le sugerirían materias que solo existen en el catálogo
    catalán: un mensaje de ayuda que lleva a otro callejón sin salida es peor
    que no dar ninguna sugerencia.

    Sin comunidad reconocida no hay nada que sugerir, y devolver todas sería
    volver al problema.
    """
    from sqlalchemy import func

    if comunidad is None:
        return []

    def _materias(modelo) -> set[str]:
        filas = db.session.execute(
            select(
                modelo.materia,
                func.jsonb_array_elements_text(modelo.cursos_aplicables).label("c"),
            )
            .where(modelo.comunidad == comunidad)
            .where(modelo.materia.is_not(None))
        ).all()
        return {m for m, c in filas if c == curso}

    return sorted(_materias(Competencia) & _materias(CriterioEvaluacion) & _materias(SaberBasico))
