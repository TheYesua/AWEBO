"""Blueprint REST para Situaciones de Aprendizaje (CRUD + duplicar + versiones)."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required

from ..schemas import (
    AdaptacionCreateIn,
    AudioIn,
    DuplicarIn,
    SituacionCreateIn,
    SituacionListItemOut,
    SituacionOut,
    SituacionUpdateIn,
    SugerenciaIn,
    VersionOut,
)
from ..extensions import limiter
from ..services import audio as almacen_audio
from ..services import exportacion_service as exp
from ..services import situacion_service as svc
from ..services import sugerencias_service as sug
from ..tasks import generacion as tareas_generacion
from ..tasks import audio as tareas_audio
from ..tasks import operaciones as tareas_operaciones
from ..tasks import encolar
from ..prompts import SECCIONES
from ..prompts.contexto import construir_contexto
from ..prompts import operaciones as prompt_operaciones


bp = Blueprint("situaciones", __name__, url_prefix="/api/situaciones")


# ---------------------------------------------------------------------------
# Manejador de errores propio del blueprint
# ---------------------------------------------------------------------------


@bp.errorhandler(svc.SituacionError)
def _handle(exc: svc.SituacionError):
    return jsonify({"error": exc.code, "mensaje": str(exc)}), exc.http_status


@bp.errorhandler(sug.SugerenciasError)
def _handle_sugerencias(exc: sug.SugerenciasError):
    return jsonify({"error": exc.code, "mensaje": str(exc)}), exc.http_status


# ---------------------------------------------------------------------------
# Sugerencia inicial de temáticas
# ---------------------------------------------------------------------------


# Ruta literal declarada antes que las de ``/<int:id_situacion>``: no colisiona
# con ellas (``sugerencias`` no casa con el conversor ``int``), pero mantenerla
# arriba deja claro que es una operación del blueprint y no de una SA concreta.
@bp.post("/sugerencias")
@login_required
# Llama al LLM de forma síncrona: es barato de invocar y caro de servir, así
# que necesita un límite propio, más generoso que el de generar una SA entera
# (10/hora) porque el docente probará varias veces hasta dar con el enfoque.
@limiter.limit("30 per hour")
def sugerir_tematicas():
    """Propone temáticas de partida a partir de curso, materia y contexto libre.

    Responde de forma **síncrona**, sin pasar por Celery: son unas pocas
    propuestas cortas y encolarlas obligaría a montar polling para algo que
    tarda un par de segundos. Ver ``services/sugerencias_service``.
    """
    datos = SugerenciaIn.model_validate(request.get_json(silent=True) or {})
    resultado = sug.proponer(
        curso=datos.curso,
        materia=datos.materia,
        contexto=datos.contexto,
        idioma=datos.idioma,
        num_propuestas=datos.num_propuestas,
        usuario=current_user,
    )
    return jsonify(resultado), 200


# ---------------------------------------------------------------------------
# Listar y crear (CU-03)
# ---------------------------------------------------------------------------


@bp.get("")
@login_required
def listar():
    """Lista situaciones del usuario aplicando filtros opcionales.

    Paginado. La respuesta pasó de ser un array a ``{total, situaciones}``: sin
    el total, la interfaz no puede decir cuántas páginas hay, y un paginador
    que solo sabe si la página actual viene llena adivina mal la última. Es la
    misma forma que devuelven los endpoints del panel, para no arrastrar dos
    convenciones en la misma API.
    """
    incluir_adapt = request.args.get("incluir_adaptaciones", "true").lower() != "false"
    filtros = dict(
        curso=request.args.get("curso"),
        materia=request.args.get("materia"),
        estado=request.args.get("estado"),
        q=request.args.get("q"),
        incluir_adaptaciones=incluir_adapt,
    )
    items = svc.listar(
        current_user,
        **filtros,
        limit=request.args.get("limit", default=svc.POR_PAGINA, type=int),
        offset=request.args.get("offset", default=0, type=int),
    )
    return (
        jsonify(
            {
                "total": svc.contar(current_user, **filtros),
                "situaciones": [
                    SituacionListItemOut.from_model(sa).model_dump(mode="json")
                    for sa in items
                ],
            }
        ),
        200,
    )


@bp.get("/resumen")
@login_required
def resumen():
    """Recuento por estado de las situaciones del usuario.

    Endpoint aparte del listado porque son preguntas distintas: el listado
    devuelve una página, esto cuenta el total. Mezclarlos obligaría a pedir
    todas las filas solo para contarlas, que es justo lo que se quitó al
    paginar.
    """
    return jsonify(svc.resumen_por_estado(current_user)), 200


@bp.post("")
@login_required
def crear():
    """Crea una nueva situación de aprendizaje.

    Si se pasa ``?generar=true`` o ``{"generar": true}`` en el body, lanza
    adicionalmente la tarea Celery de generación y devuelve 202 con
    ``task_id``. En otro caso devuelve 201 con la SA creada en borrador.
    """
    body = request.get_json(silent=True) or {}
    # "generar" no forma parte del esquema de creación; lo extraemos aparte.
    generar_flag = bool(body.pop("generar", False)) or (
        request.args.get("generar", "false").lower() == "true"
    )
    data = SituacionCreateIn.model_validate(body)
    sa = svc.crear(current_user, data.model_dump())

    if not generar_flag:
        return jsonify(SituacionOut.from_model(sa).model_dump(mode="json")), 201

    # La SA ya está creada: si falta currículo se avisa aquí, pero se conserva
    # en borrador para que el docente pueda corregir la materia sin perderla.
    _exigir_curriculo(sa)

    async_result = encolar(
        tareas_generacion.generar_situacion_completa, sa.id_situacion
    )
    payload = SituacionOut.from_model(sa).model_dump(mode="json")
    payload["task_id"] = async_result.id
    return jsonify(payload), 202


# ---------------------------------------------------------------------------
# Operaciones sobre una situación concreta
# ---------------------------------------------------------------------------


@bp.get("/<int:id_situacion>")
@login_required
def obtener(id_situacion: int):
    sa = svc.obtener(id_situacion, current_user)
    return jsonify(SituacionOut.from_model(sa).model_dump(mode="json")), 200


@bp.post("/<int:id_situacion>/audio")
@login_required
@limiter.limit("30 per hour")
def pedir_audio(id_situacion: int):
    """Encola la narración de una sección.

    Devuelve 202 y no el audio: sintetizar tarda segundos, y hacerlo dentro de
    la petición dejaría la pantalla colgada y ocuparía uno de los dos
    trabajadores de gunicorn mientras tanto.

    Si el audio de ese texto **ya existe**, responde 200 sin encolar nada. La
    comprobación sale gratis porque el nombre del fichero se calcula a partir
    del propio texto: no hay que preguntarle a ninguna tabla si está hecho.
    """
    sa = svc.obtener(id_situacion, current_user)   # 403/404 si no es suya
    data = AudioIn.model_validate(request.get_json(silent=True) or {})

    idioma = sa.idioma or "es"
    if almacen_audio.ruta(sa.id_situacion, data.seccion, data.texto, idioma).is_file():
        return jsonify({"estado": "listo"}), 200

    encolar(tareas_audio.generar_audio, id_situacion=sa.id_situacion,
            seccion=data.seccion, texto=data.texto, idioma=idioma)
    return jsonify({"estado": "generando"}), 202


@bp.get("/<int:id_situacion>/audio")
@login_required
def obtener_audio(id_situacion: int):
    """Devuelve el MP3 si está listo, y 404 si todavía no.

    El texto viaja como parámetro porque es lo que identifica al audio: pedir
    «el audio de la sección X» sin decir de qué texto devolvería la narración
    de una versión anterior después de editar, que suena bien y dice otra cosa.
    """
    sa = svc.obtener(id_situacion, current_user)
    seccion = (request.args.get("seccion") or "").strip()
    texto = request.args.get("texto") or ""
    if not seccion or not texto:
        return jsonify({"error": "faltan_parametros"}), 400

    try:
        ruta = almacen_audio.ruta(sa.id_situacion, seccion, texto, sa.idioma or "es")
    except ValueError:
        return jsonify({"error": "seccion_invalida"}), 400

    if not ruta.is_file():
        return jsonify({"estado": "no_disponible"}), 404

    return Response(
        ruta.read_bytes(),
        mimetype="audio/mpeg",
        headers={
            # `inline` para que el reproductor del navegador lo use sin
            # descargar, y un nombre legible por si alguien sí lo descarga.
            "Content-Disposition": f'inline; filename="{seccion}.mp3"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@bp.put("/<int:id_situacion>")
@login_required
def actualizar(id_situacion: int):
    """Actualiza la situación. Crea automáticamente una versión histórica."""
    data = SituacionUpdateIn.model_validate(request.get_json(silent=True) or {})
    cambios = data.model_dump(exclude_unset=True)
    sa = svc.actualizar(id_situacion, current_user, cambios)
    return jsonify(SituacionOut.from_model(sa).model_dump(mode="json")), 200


@bp.delete("/<int:id_situacion>")
@login_required
def eliminar(id_situacion: int):
    svc.eliminar(id_situacion, current_user)
    return "", 204


# ---------------------------------------------------------------------------
# Duplicación
# ---------------------------------------------------------------------------


@bp.post("/<int:id_situacion>/duplicar")
@login_required
def duplicar(id_situacion: int):
    data = DuplicarIn.model_validate(request.get_json(silent=True) or {})
    copia = svc.duplicar(id_situacion, current_user, data.titulo)
    return jsonify(SituacionOut.from_model(copia).model_dump(mode="json")), 201


# ---------------------------------------------------------------------------
# Versiones (CU-07)
# ---------------------------------------------------------------------------


@bp.get("/<int:id_situacion>/versiones")
@login_required
def listar_versiones(id_situacion: int):
    versiones = svc.listar_versiones(id_situacion, current_user)
    return (
        jsonify(
            [
                VersionOut.model_validate(v, from_attributes=True).model_dump(
                    mode="json"
                )
                for v in versiones
            ]
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Adaptaciones curriculares (CU-10)
# ---------------------------------------------------------------------------


@bp.post("/<int:id_situacion>/adaptaciones")
@login_required
def crear_adaptacion(id_situacion: int):
    """Crea una SA hija de adaptación y lanza su generación asíncrona (CU-10).

    Devuelve 202 + task_id. La SA adaptada queda en estado ``generando``
    hasta que la tarea Celery termine.
    """
    sa_origen = svc.obtener(id_situacion, current_user)

    data = AdaptacionCreateIn.model_validate(request.get_json(silent=True) or {})

    tipo_label = {"no_significativa": "ACNS", "significativa": "ACS"}[data.tipo_adaptacion]
    titulo_adapt = data.titulo or f"[{tipo_label}] {sa_origen.titulo}"

    sa_adapt = svc.crear(current_user, {
        "titulo": titulo_adapt,
        "curso": sa_origen.curso,
        "materia": sa_origen.materia,
        "comunidad_autonoma": sa_origen.comunidad_autonoma,
        "descripcion": sa_origen.descripcion,
        "metodologia": sa_origen.metodologia,
        "num_sesiones": sa_origen.num_sesiones,
        "duracion_sesion_minutos": sa_origen.duracion_sesion_minutos,
        "idioma": sa_origen.idioma,
        # perfil_aula de la SA hija = descripción del alumno concreto,
        # no el perfil de aula de origen (que se pasa por contenido_origen).
        "perfil_aula": data.perfil_alumnado,
        "materiales_contexto": sa_origen.materiales_contexto,
        # Metadatos de adaptación en el mismo commit para evitar estado inconsistente.
        "id_situacion_origen": sa_origen.id_situacion,
        "tipo_adaptacion": data.tipo_adaptacion,
        "perfil_alumnado": data.perfil_alumnado,
    })

    async_result = encolar(
        tareas_generacion.generar_situacion_completa, sa_adapt.id_situacion
    )
    payload = SituacionOut.from_model(sa_adapt).model_dump(mode="json")
    payload["task_id"] = async_result.id
    return jsonify(payload), 202


@bp.get("/<int:id_situacion>/adaptaciones")
@login_required
def listar_adaptaciones(id_situacion: int):
    """Lista todas las adaptaciones derivadas de una SA (CU-10)."""
    svc.obtener(id_situacion, current_user)  # valida permisos
    from ..extensions import db
    from ..models import SituacionAprendizaje as SAModel
    from sqlalchemy import select
    adaptaciones = db.session.scalars(
        select(SAModel).where(SAModel.id_situacion_origen == id_situacion)
    ).all()
    return (
        jsonify([
            SituacionListItemOut.from_model(a).model_dump(mode="json")
            for a in adaptaciones
        ]),
        200,
    )


# ---------------------------------------------------------------------------
# Generación IA (CU-03 / CU-05)
# ---------------------------------------------------------------------------


def _exigir_curriculo(sa) -> None:
    """Aborta si la SA no tiene currículo LOMLOE que anclar.

    Los desplegables de curso y materia eran independientes, así que se podía
    crear una SA de «Matemáticas · 4º ESO» — combinación que no existe: en 4.º
    la materia se desdobla en los itinerarios A y B. La generación seguía
    adelante, el modelo recibía un listado curricular vacío y devolvía
    ``objetivos: []`` y ``conexion_curricular`` sin nada. La SA quedaba en
    estado «generada», aparentemente correcta, y el docente descubría el
    problema al abrirla.

    Vale más gastar una consulta que una generación entera y la confianza de
    quien la lea.
    """
    ctx = construir_contexto(sa)
    if ctx.tiene_curriculo():
        return

    alternativas = svc.materias_con_curriculo(sa.curso)
    sugerencia = (
        f" Para {sa.curso} hay currículo de: {', '.join(alternativas)}."
        if alternativas
        else ""
    )
    raise svc.SituacionError(
        "sin_curriculo",
        f"No hay currículo cargado para «{sa.materia}» en {sa.curso}, así que "
        f"la situación se generaría sin criterios ni saberes a los que "
        f"anclarse.{sugerencia}",
        http_status=422,
    )


@bp.post("/<int:id_situacion>/generar")
@login_required
@limiter.limit("10 per hour")
def generar(id_situacion: int):
    """Lanza la generación asíncrona completa de la SA. Devuelve 202 + task_id."""
    sa = svc.obtener(id_situacion, current_user)
    _exigir_curriculo(sa)
    if sa.estado == sa.GENERANDO:
        return (
            jsonify(
                {
                    "error": "ya_generando",
                    "mensaje": "La SA ya tiene una generación en curso.",
                }
            ),
            409,
        )

    async_result = encolar(
        tareas_generacion.generar_situacion_completa, id_situacion
    )
    return (
        jsonify(
            {
                "id_situacion": id_situacion,
                "task_id": async_result.id,
                "estado": sa.GENERANDO,
            }
        ),
        202,
    )


@bp.post("/<int:id_situacion>/regenerar/<seccion>")
@login_required
@limiter.limit("15 per hour")
def regenerar_seccion(id_situacion: int, seccion: str):
    """Regenera una única sección de la SA (CU-05)."""
    sa = svc.obtener(id_situacion, current_user)

    # El nombre de sección se valida ANTES que el currículo: es un error de la
    # petición, más concreto y más barato de comprobar. Al revés, pedir una
    # sección inexistente en una SA sin currículo devolvería «falta currículo»,
    # que no es el problema.
    if seccion not in SECCIONES:
        return (
            jsonify(
                {
                    "error": "seccion_desconocida",
                    "mensaje": f"Secciones válidas: {sorted(SECCIONES)}",
                }
            ),
            400,
        )

    _exigir_curriculo(sa)

    if sa.estado == sa.GENERANDO:
        return (
            jsonify(
                {
                    "error": "ya_generando",
                    "mensaje": "La SA ya tiene una generación en curso.",
                }
            ),
            409,
        )

    async_result = encolar(
        tareas_generacion.generar_seccion, id_situacion, seccion
    )
    return (
        jsonify(
            {
                "id_situacion": id_situacion,
                "seccion": seccion,
                "task_id": async_result.id,
                "estado": sa.GENERANDO,
            }
        ),
        202,
    )


# ---------------------------------------------------------------------------
# Operaciones sobre un bloque: resumir, expandir, traducir
# ---------------------------------------------------------------------------


@bp.post("/<int:id_situacion>/secciones/<seccion>/<operacion>")
@login_required
@limiter.limit("40 per hour")
def transformar_seccion(id_situacion: int, seccion: str, operacion: str):
    """Resume, desarrolla o traduce una sección ya generada.

    Se aplica directamente: la tarea guarda una versión antes de sustituir, y
    ``POST …/deshacer`` la restaura. Ver ``app/tasks/operaciones.py``.
    """
    sa = svc.obtener(id_situacion, current_user)

    if operacion not in prompt_operaciones.OPERACIONES:
        return (
            jsonify(
                {
                    "error": "operacion_desconocida",
                    "mensaje": f"Operaciones válidas: {sorted(prompt_operaciones.OPERACIONES)}",
                }
            ),
            400,
        )

    if seccion not in SECCIONES:
        return (
            jsonify(
                {
                    "error": "seccion_desconocida",
                    "mensaje": f"Secciones válidas: {sorted(SECCIONES)}",
                }
            ),
            400,
        )

    # No toda operación tiene sentido en toda sección: la conexión curricular
    # es una tabla de códigos, y resumirla, desarrollarla o traducirla la
    # estropea. Ver SECCIONES_APLICABLES.
    if not prompt_operaciones.aplicable(operacion, seccion):
        return (
            jsonify(
                {
                    "error": "operacion_no_aplicable",
                    "mensaje": (
                        f"«{operacion}» no se puede aplicar a «{seccion}»: es "
                        "contenido anclado al currículo oficial, no redacción libre."
                    ),
                }
            ),
            422,
        )

    if not (sa.contenido or {}).get(seccion):
        return (
            jsonify(
                {
                    "error": "seccion_vacia",
                    "mensaje": "Esa sección aún no tiene contenido que transformar.",
                }
            ),
            422,
        )

    if sa.estado == sa.GENERANDO:
        return (
            jsonify(
                {
                    "error": "ya_generando",
                    "mensaje": "La SA ya tiene una generación en curso.",
                }
            ),
            409,
        )

    async_result = encolar(
        tareas_operaciones.transformar_seccion, id_situacion, seccion, operacion
    )
    return (
        jsonify(
            {
                "id_situacion": id_situacion,
                "seccion": seccion,
                "operacion": operacion,
                "task_id": async_result.id,
            }
        ),
        202,
    )


@bp.post("/<int:id_situacion>/secciones/<seccion>/elegir/<cual>")
@login_required
def elegir_propuesta(id_situacion: int, seccion: str, cual: str):
    """Resuelve una doble propuesta: ``cual`` es ``actual`` o ``alternativa``.

    La descartada no se pierde —queda en el histórico— y la elección se
    registra con la procedencia de ambas candidatas. Ver
    ``situacion_service.elegir_propuesta``.
    """
    sa = svc.elegir_propuesta(id_situacion, current_user, seccion, cual)
    return jsonify(SituacionOut.from_model(sa).model_dump(mode="json")), 200


@bp.post("/<int:id_situacion>/secciones/<seccion>/deshacer")
@login_required
def deshacer_seccion(id_situacion: int, seccion: str):
    """Devuelve una sección a su última versión guardada.

    Restaura solo esa sección: si el docente resume un bloque y después edita
    otro, deshacer el resumen no debe llevarse por delante la edición.
    """
    sa = svc.restaurar_seccion(id_situacion, current_user, seccion)
    return jsonify(SituacionOut.from_model(sa).model_dump(mode="json")), 200


# ---------------------------------------------------------------------------
# Exportación a PDF/DOCX (CU-06)
# ---------------------------------------------------------------------------


@bp.get("/<int:id_situacion>/exportar")
@login_required
@limiter.limit("20 per minute")
def exportar(id_situacion: int):
    """Exporta la SA en el formato indicado por ``?formato=pdf|docx``.

    Sólo permite exportar SA que ya tienen contenido generado. Si la
    SA está en borrador, devuelve 409.
    """
    formato = (request.args.get("formato") or "pdf").lower()
    if formato not in {"pdf", "docx"}:
        return (
            jsonify(
                {
                    "error": "formato_no_soportado",
                    "mensaje": "Formatos válidos: pdf, docx.",
                }
            ),
            400,
        )

    sa = svc.obtener(id_situacion, current_user)
    if not sa.contenido:
        return (
            jsonify(
                {
                    "error": "sin_contenido",
                    "mensaje": "La SA aún no tiene contenido generado.",
                }
            ),
            409,
        )

    if formato == "pdf":
        data = exp.renderizar_pdf(sa, current_user)
        mimetype = "application/pdf"
    else:  # docx
        data = exp.renderizar_docx(sa, current_user)
        mimetype = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    return Response(
        data,
        mimetype=mimetype,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{exp.nombre_fichero(sa, formato)}"'
            ),
        },
    )
