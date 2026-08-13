"""Enlazar una SdA con las filas reales del catálogo curricular.

QUÉ PROBLEMA RESUELVE
---------------------
La sección ``conexion_curricular`` del JSONB guarda **códigos sueltos**:
``"CE1"``, ``"1.1"``, ``"A.3"``. Un código no es una referencia: es una cadena
que se parece a una. Si un criterio se renombra o desaparece del catálogo, la
SdA se queda apuntando al vacío y nada avisa. Pasó de verdad al separar
Tecnología de Tecnología y Digitalización.

Las cuatro tablas de enlace existían desde el TFG para eso, y **nadie escribía
nunca en ellas**. Se descubrió el 09/08/2026 mirando los recuentos del primer
backup: 39 SdA y 0 enlaces. Cuatro consultas por cada carga de una SdA que
siempre devolvían vacío.

LO QUE NO CAMBIA
----------------
El JSONB sigue siendo la fuente de la que se pinta y se exporta. Estos enlaces
son una **capa de integridad añadida**, no un sustituto: si mañana se borraran
las cuatro tablas, la aplicación seguiría funcionando igual. Por eso ``FALLO``
nunca tumba una generación — ver ``sincronizar``.

EL EFECTO SECUNDARIO QUE MÁS VALE
----------------------------------
Un código que no casa con ninguna fila del catálogo es, casi siempre, un código
que el modelo **se ha inventado**. El prompt se lo prohíbe expresamente
(«No inventes códigos»), pero prohibirlo no es lo mismo que comprobarlo. Al
resolverlos contra la base de datos, los inventados se caen solos y quedan en
el registro con su código, su materia y su curso. Es la primera medida directa
que tiene el proyecto de cuánto alucina cada modelo.

POR QUÉ ``situacion_ods`` NO SE POBLA
--------------------------------------
Porque no hay de dónde. Ningún prompt pide ODS —se comprobó recorriendo
``app/prompts/`` entero—, así que el JSONB nunca los trae. La tabla y el
catálogo de la ONU se quedan donde están, para cuando haya una sección que los
pida; lo que se ha quitado es la relación con ``lazy="selectin"``, que era una
consulta garantizada a vacío en cada carga.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select

from ..extensions import db
from . import geografia
from ..models import Competencia, CriterioEvaluacion, SaberBasico, SituacionAprendizaje


log = structlog.get_logger(__name__)


#: Cada entrada: (clave en el JSONB, modelo, atributo de la relación).
_MAPA = (
    ("competencias", Competencia, "competencias"),
    ("criterios", CriterioEvaluacion, "criterios"),
    ("saberes", SaberBasico, "saberes"),
)


def _codigos(contenido: dict, clave: str) -> list[str]:
    """Los códigos de una lista del JSONB, sin repetidos y en orden.

    Tolera basura a propósito. El contenido lo escribe un modelo de lenguaje y
    ha llegado aquí en formas que el esquema no prometía: la lista ausente, un
    diccionario en vez de una lista, elementos que son cadenas sueltas en lugar
    de objetos con ``codigo``. Reventar aquí dejaría la generación entera en
    error por un adorno del JSON que la pantalla pinta sin problema.
    """
    seccion = (contenido or {}).get("conexion_curricular") or {}
    if not isinstance(seccion, dict):
        return []
    bruto = seccion.get(clave)
    if not isinstance(bruto, list):
        return []

    vistos: dict[str, None] = {}
    for elemento in bruto:
        if isinstance(elemento, dict):
            codigo = elemento.get("codigo")
        elif isinstance(elemento, str):
            codigo = elemento
        else:
            continue
        if isinstance(codigo, str) and codigo.strip():
            vistos.setdefault(codigo.strip(), None)
    return list(vistos)


def _resolver(
    modelo, codigos: list[str], materia: str, curso: str, comunidad: str | None
) -> tuple[list, list[str]]:
    """Filas del catálogo que casan, y códigos que no casaron.

    Se filtra por materia **y** curso, no solo por código. Los códigos no son
    únicos: ``"1.1"`` existe en todas las materias, y la Orden EFP/754 llega a
    desarrollar criterios distintos con el mismo código en cursos distintos
    dentro de una misma materia. Buscar solo por código enlazaría la SdA con el
    criterio de otra asignatura, que es peor que no enlazar nada: parecería
    correcto.

    ``cursos_aplicables`` es un JSONB con la lista de cursos, así que la
    comprobación se hace en Python y no en SQL. Son catálogos de unos cientos
    de filas por materia; no compensa un operador de contención por ahorrar una
    comparación de listas.
    """
    if not codigos or not comunidad:
        return [], []

    # La comunidad va lo primero: un código de Cataluña y uno de Ceuta pueden
    # ser idénticos, y enlazar el de la otra comunidad es peor que no enlazar
    # nada, porque el resultado parece correcto.
    condicion = (modelo.comunidad == comunidad) & modelo.codigo.in_(codigos)
    if hasattr(modelo, "materia"):
        # `Competencia.materia` es NULL en las competencias clave, que valen
        # para cualquier materia. Excluirlas dejaría fuera precisamente las
        # transversales.
        condicion = condicion & ((modelo.materia == materia) | (modelo.materia.is_(None)))

    candidatas = db.session.scalars(select(modelo).where(condicion)).all()
    validas = [
        fila for fila in candidatas
        if not fila.cursos_aplicables or curso in fila.cursos_aplicables
    ]
    encontrados = {fila.codigo for fila in validas}
    return validas, [c for c in codigos if c not in encontrados]


def hay_curriculo(materia: str, curso: str, comunidad: str | None = None) -> bool:
    """¿Existe currículo cargado para esta pareja?

    LA DISTINCIÓN QUE FALTABA, Y QUE COSTÓ UN DIAGNÓSTICO FALSO
    ------------------------------------------------------------
    Sin esto, `sincronizar` metía en el mismo saco dos cosas que no se parecen
    en nada, y el comando de la CLI las anunciaba a las dos como «códigos que
    el modelo se inventó»:

    * **La materia y el curso tienen currículo, pero algún código no casa.**
      Eso sí es una alucinación del modelo: se le prohíbe inventarse códigos y
      lo ha hecho igual.
    * **La pareja (materia, curso) no existe en el catálogo.** Entonces
      *ningún* código puede casar, hagan lo que hagan el modelo y el docente.
      No hay nada inventado: la SdA está anclada a un currículo que no existe.

    En la primera ejecución real, 17 de 39 SdA cayeron en el segundo caso y el
    comando las presentó como el primero. Eran `Matemáticas · 4º ESO` (en 4º
    hay A y B), `Tecnología y Digitalización · 4º ESO` (solo se imparte en 2º y
    3º) y `Lengua Castellana y Literatura`, que en el catálogo se llama
    `Lengua`. Todas anteriores a que el formulario validara la pareja.

    Un diagnóstico confiado y equivocado es peor que no diagnosticar: manda a
    quien lo lee a buscar donde no está el problema.
    """
    if comunidad is None:
        return False

    for modelo in (Competencia, CriterioEvaluacion, SaberBasico):
        condicion = (modelo.comunidad == comunidad) & (modelo.materia == materia)
        existe = db.session.scalars(select(modelo).where(condicion).limit(50)).all()
        if any(not f.cursos_aplicables or curso in f.cursos_aplicables for f in existe):
            return True
    return False


def sincronizar(situacion: SituacionAprendizaje, *, commit: bool = True) -> dict:
    """Rehace los enlaces de esta SdA a partir de su JSONB.

    Devuelve un resumen con cuántos enlaces hay de cada tipo y qué códigos no
    se pudieron resolver.

    **No lanza nunca.** Se llama al final de una generación que ya ha guardado
    su contenido; dejar que un fallo aquí tumbe la petición cambiaría un
    problema de integridad —que no impide usar la SdA— por uno de
    disponibilidad, que sí. Cualquier excepción queda en el registro y la SdA
    se queda como estaba.
    """
    resumen: dict = {
        "id_situacion": situacion.id_situacion,
        "huerfanos": {},
        "sin_curriculo": False,
    }
    try:
        comunidad = geografia.comunidad_de(situacion)
        resumen["sin_curriculo"] = not hay_curriculo(
            situacion.materia, situacion.curso, comunidad
        )
        for clave, modelo, atributo in _MAPA:
            codigos = _codigos(situacion.contenido, clave)
            filas, huerfanos = _resolver(
                modelo, codigos, situacion.materia, situacion.curso, comunidad
            )
            # Asignación completa y no `.append`: la sección se puede regenerar
            # o deshacer, y entonces los enlaces de la versión anterior tienen
            # que desaparecer. Acumular dejaría un histórico que nadie pidió y
            # que haría que la cobertura solo pudiera crecer.
            setattr(situacion, atributo, filas)
            resumen[clave] = len(filas)
            if huerfanos:
                resumen["huerfanos"][clave] = huerfanos

        if commit:
            db.session.commit()
    except Exception:
        db.session.rollback()
        log.warning(
            "enlaces_curriculares_fallidos",
            id_situacion=situacion.id_situacion,
            exc_info=True,
        )
        return {"id_situacion": situacion.id_situacion, "error": True}

    if resumen["sin_curriculo"]:
        # Evento propio: la SdA está anclada a una pareja que no existe, así
        # que sus códigos no fallan por ser falsos sino por no tener contra qué
        # comprobarse. Mezclarlo con el aviso de abajo falsearía la medida de
        # cuánto alucinan los modelos.
        log.warning(
            "situacion_sin_curriculo",
            id_situacion=situacion.id_situacion,
            materia=situacion.materia,
            curso=situacion.curso,
            # Sin la comunidad, este aviso no distingue «no hay currículo de
            # esta materia» de «la comunidad no se reconoce», que se arreglan
            # de formas muy distintas.
            comunidad=situacion.comunidad_autonoma,
            comunidad_normalizada=comunidad,
        )
    elif resumen["huerfanos"]:
        # Aquí sí: la materia y el curso tienen currículo cargado, y aun así
        # hay códigos que no casan. Eso es el modelo inventándoselos pese a
        # tenerlo prohibido en el prompt, y es lo que permite compararlos.
        log.warning(
            "codigos_curriculares_inventados",
            id_situacion=situacion.id_situacion,
            materia=situacion.materia,
            curso=situacion.curso,
            **{k: v for k, v in resumen["huerfanos"].items()},
        )
    else:
        log.info("enlaces_curriculares_sincronizados", **{
            k: v for k, v in resumen.items() if k != "huerfanos"
        })
    return resumen


__all__ = ["sincronizar", "hay_curriculo"]
