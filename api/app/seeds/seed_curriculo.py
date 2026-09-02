"""Carga el currículo LOMLOE (competencias, criterios y saberes) en la BD.

Lee los ficheros JSON generados por ``app.curriculo.extractor`` (uno por
cada par materia/ciclo) y los inserta o actualiza de forma idempotente.

Esquema de unicidad utilizado para los UPSERT. **La comunidad y la etapa entran
en todas las claves.** Sin la comunidad, cargar el decreto de una segunda
actualizaría las filas de la primera en vez de añadir las suyas —los códigos y
las materias coinciden— y el currículo de Ceuta acabaría con las descripciones
catalanas. Sin la etapa pasa lo mismo entre la ESO y Bachillerato, donde
«Matemáticas» existe en las dos y sus competencias se numeran igual.

* **Competencia**: ``(comunidad, etapa, codigo, materia)`` — las competencias
  específicas son comunes a todos los cursos de **su** etapa, así que se fusiona
  ``cursos_aplicables`` haciendo unión con lo ya almacenado. Por eso los cursos
  no están en la clave, y por eso hace falta la etapa: es lo único que separa la
  competencia 1 de Matemáticas de la ESO de la 1 de Matemáticas de Bachillerato.
* **CriterioEvaluacion**: ``(comunidad, etapa, codigo, materia, cursos_aplicables)``
  — los criterios pueden repetir código entre cursos con descripciones distintas
  (caso de Lengua/Inglés en la Orden EFP/754).
* **SaberBasico**: ``(comunidad, etapa, codigo, materia, cursos_aplicables,
  descripcion)`` — cada item de saber básico es una fila independiente.

La fuente por defecto es ``implementacion/curriculo/salida/`` (montada en
el contenedor como ``/app/curriculo/salida/``).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select

from ..extensions import db
from ..models import Competencia, CriterioEvaluacion, SaberBasico


logger = logging.getLogger("seeds.curriculo")


# Ruta por defecto dentro del contenedor (volumen montado en docker-compose).
RUTA_SALIDA_DEFECTO = Path("/curriculo/salida")


# ---------------------------------------------------------------------------
# Helpers de upsert
# ---------------------------------------------------------------------------


#: Orden de presentación de los cursos. Primero la ESO y después Bachillerato,
#: que es el orden en que los cursa quien los cursa.
#:
#: La versión anterior solo conocía «Nº ESO» y mandaba todo lo demás al final
#: con un 99: con Bachillerato eso habría dejado sus dos cursos empatados y en
#: orden arbitrario, sin fallar. Se escribe la lista entera en vez de analizar
#: la cadena porque son seis valores y no cambian.
_ORDEN_CURSOS = {
    **{f"{i}º ESO": i for i in range(1, 5)},
    "1º Bachillerato": 5,
    "2º Bachillerato": 6,
}


def _union_cursos(actual: list[str], nuevos: list[str]) -> list[str]:
    """Fusiona dos listas de cursos preservando el orden 1.º ESO → 2.º Bach."""
    unidos = set(actual) | set(nuevos)
    # Lo desconocido va al final y **por orden alfabético**, no en el que
    # llegue: un orden que depende del recorrido de un `set` produce
    # diferencias entre cargas que parecen cambios de datos.
    return sorted(unidos, key=lambda c: (_ORDEN_CURSOS.get(c, 99), c))


def _upsert_competencia(
    *,
    codigo: str,
    materia: str,
    cursos: list[str],
    descriptores: list[str],
    descripcion: str,
    comunidad: str,
    etapa: str,
    idioma: str,
) -> tuple[Competencia, bool]:
    """Inserta o actualiza una Competencia por (comunidad, codigo, materia)."""
    existente = db.session.scalar(
        select(Competencia).where(
            Competencia.comunidad == comunidad,
            Competencia.etapa == etapa,
            Competencia.codigo == codigo,
            Competencia.materia == materia,
        )
    )
    if existente is None:
        ce = Competencia(
            codigo=codigo,
            tipo=Competencia.ESPECIFICA,
            materia=materia,
            comunidad=comunidad,
            etapa=etapa,
            idioma=idioma,
            cursos_aplicables=list(cursos),
            descriptores=list(descriptores),
            descripcion=descripcion,
        )
        db.session.add(ce)
        db.session.flush()
        return ce, True

    existente.cursos_aplicables = _union_cursos(
        existente.cursos_aplicables or [], cursos
    )
    # Fusionar descriptores (suelen coincidir entre cursos, pero por si acaso).
    existente.descriptores = sorted(
        set(existente.descriptores or []) | set(descriptores)
    )
    existente.descripcion = descripcion
    return existente, False


def _upsert_criterio(
    *,
    codigo: str,
    id_competencia: int,
    materia: str,
    cursos: list[str],
    descripcion: str,
    comunidad: str,
    etapa: str,
    idioma: str,
    ya_vistas: set | None = None,
) -> tuple[CriterioEvaluacion, bool]:
    """Upsert por (comunidad, codigo, materia, cursos). True si se creó.

    Devuelve también la fila —como `_upsert_competencia`— porque el modo de
    recarga limpia necesita saber **qué filas ha visto** para poder distinguir
    las que sobran. Con un booleano solo se sabe cuántas, no cuáles.

    POR QUÉ SE MIRA LO YA VISTO EN ESTA MISMA CARGA
    ------------------------------------------------
    Porque **el código no siempre es único dentro de una materia**. El Decreto
    76/2023 publica dos criterios distintos con el código `8.3` en Euskara eta
    Literatura, y el decreto no dice en ninguna parte cuál de los dos está mal
    numerado — a diferencia de los otros cinco casos, que el extractor sí puede
    deducir de la cabecera.

    Sin esta comprobación el segundo `8.3` **actualizaba la fila del primero**:
    el texto del primero se perdía y el recuento decía `cr_nuevos` uno menos
    que criterios había en el JSON. Una fila que ya se ha tocado en esta carga
    no puede volver a ser el destino de otro criterio: si el código se repite,
    el segundo va a una fila nueva. Se acepta el código duplicado, que es lo
    que publica el boletín, y no se pierde texto curricular.
    """
    candidatos = db.session.scalars(
        select(CriterioEvaluacion).where(
            CriterioEvaluacion.comunidad == comunidad,
            CriterioEvaluacion.etapa == etapa,
            CriterioEvaluacion.codigo == codigo,
            CriterioEvaluacion.materia == materia,
        )
    ).all()
    cursos_norm = sorted(cursos)
    vistas = ya_vistas or set()
    for c in candidatos:
        if c in vistas:
            continue
        if sorted(c.cursos_aplicables or []) == cursos_norm:
            c.descripcion = descripcion
            c.id_competencia = id_competencia
            return c, False
    nuevo = CriterioEvaluacion(
        codigo=codigo,
        id_competencia=id_competencia,
        materia=materia,
        comunidad=comunidad,
        etapa=etapa,
        idioma=idioma,
        cursos_aplicables=list(cursos),
        descripcion=descripcion,
    )
    db.session.add(nuevo)
    return nuevo, True


def _upsert_saber_item(
    *,
    codigo: str,
    bloque: str,
    materia: str,
    cursos: list[str],
    descripcion: str,
    comunidad: str,
    etapa: str,
    idioma: str,
) -> tuple[SaberBasico, bool]:
    """Upsert por (comunidad, codigo, materia, cursos, descripcion).

    Devuelve la fila además del booleano, por lo mismo que `_upsert_criterio`:
    la recarga limpia necesita saber cuáles ha visto, no cuántas.
    """
    candidatos = db.session.scalars(
        select(SaberBasico).where(
            SaberBasico.comunidad == comunidad,
            SaberBasico.etapa == etapa,
            SaberBasico.codigo == codigo,
            SaberBasico.materia == materia,
            SaberBasico.descripcion == descripcion,
        )
    ).all()
    cursos_norm = sorted(cursos)
    for s in candidatos:
        if sorted(s.cursos_aplicables or []) == cursos_norm:
            s.bloque = bloque
            return s, False
    nuevo = SaberBasico(
        codigo=codigo,
        bloque=bloque,
        materia=materia,
        comunidad=comunidad,
        etapa=etapa,
        idioma=idioma,
        cursos_aplicables=list(cursos),
        descripcion=descripcion,
    )
    db.session.add(nuevo)
    return nuevo, True


# ---------------------------------------------------------------------------
# Procesamiento de un fichero JSON del extractor
# ---------------------------------------------------------------------------


def _procesar_fichero(
    ruta: Path, comunidad: str, idioma: str
) -> dict[str, object]:
    """Carga el JSON ``ruta`` y vuelca su contenido en BD. Devuelve contadores.

    **El fichero manda sobre los argumentos.** Los JSON de hoy no traen
    `comunidad` ni `idioma` —salen todos de la Orden EFP/754— pero los de un
    DOGC o un BOPV sí los traerán, y entonces el dato correcto es el del
    fichero y no lo que alguien haya tecleado en la línea de órdenes. Al revés
    sería posible cargar el decreto catalán como si fuera de Ceuta por una
    opción mal puesta.
    """
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    materia = datos["materia"]
    cursos = list(datos["cursos_aplicables"])
    if not cursos:
        # Se carga igual —el dato es el que es y ocultarlo no ayuda— pero se
        # dice, porque el resultado es una materia **invisible**: sin cursos no
        # aparece en el desplegable ni en el contexto del modelo, y tampoco
        # enlaza ningún código. Pasó con «Robòtica i Programació», que estuvo
        # dos días cargada y muerta sin que nada lo señalara.
        logger.error(
            "%s: «%s» viene SIN CURSOS. Se cargará, pero no se podrá usar: "
            "revisa el extractor.", ruta.name, materia,
        )
    comunidad = datos.get("comunidad") or comunidad
    idioma = datos.get("idioma") or idioma
    # La etapa la pone el extractor en el JSON y **no se pasa por la línea de
    # órdenes**, al revés que la comunidad y el idioma: no hay ningún caso en
    # que tenga sentido cargar un fichero de Bachillerato diciendo que es de
    # la ESO. Si falta, se cae al valor de las cinco comunidades ya cargadas,
    # que es lo único que puede ser un fichero anterior a este campo.
    etapa = datos.get("etapa") or "ESO"

    stats: dict[str, object] = {
        "ce_nuevas": 0, "ce_actualizadas": 0, "cr_nuevos": 0, "sb_nuevos": 0,
        # No es un contador: es la comunidad que **acabó mandando**, para que
        # quien llama pueda decir en el log qué se cargó de verdad.
        "comunidad": comunidad,
        # Y la etapa, por lo mismo: el borrado de sobrantes se acota a los
        # pares (comunidad, etapa) que esta carga ha tocado.
        "etapa": etapa,
        # Las filas que este fichero ha tocado. Es lo que permite después
        # distinguir lo que sobra: todo lo de esta comunidad que no esté aquí
        # es de una carga anterior y ya no existe en la norma.
        #
        # Se guardan los **objetos** y no sus identificadores, y no da igual:
        # una fila recién insertada no tiene id hasta que se hace `flush`, y
        # hacer uno por fila serían cinco mil viajes a la base de datos en una
        # carga completa. Se convierten a id de una vez, después del único
        # flush, en `seed_curriculo`.
        "vistas": {"competencia": set(), "criterio": set(), "saber": set()},
    }
    vistas = stats["vistas"]

    # 1) Competencias específicas
    competencias_por_codigo: dict[str, Competencia] = {}
    for ce in datos["competencias_especificas"]:
        obj, creado = _upsert_competencia(
            codigo=ce["codigo"],
            materia=materia,
            cursos=cursos,
            descriptores=ce.get("descriptores") or [],
            descripcion=ce["descripcion"],
            comunidad=comunidad,
            etapa=etapa,
            idioma=idioma,
        )
        competencias_por_codigo[ce["codigo"]] = obj
        vistas["competencia"].add(obj)
        if creado:
            stats["ce_nuevas"] += 1
        else:
            stats["ce_actualizadas"] += 1

    # 2) Criterios de evaluación
    for cr in datos["criterios_evaluacion"]:
        ce_codigo = cr["competencia"]  # "CE1", "CE2", ...
        comp = competencias_por_codigo.get(ce_codigo)
        if comp is None:
            logger.warning(
                "Criterio %s referencia %s pero no se encontró la competencia "
                "en %s; se omite.",
                cr["codigo"],
                ce_codigo,
                ruta.name,
            )
            continue
        fila, creado = _upsert_criterio(
            comunidad=comunidad,
            etapa=etapa,
            idioma=idioma,
            codigo=cr["codigo"],
            id_competencia=comp.id_competencia,
            materia=materia,
            cursos=cursos,
            descripcion=cr["descripcion"],
            ya_vistas=vistas["criterio"],
        )
        vistas["criterio"].add(fila)
        if creado:
            stats["cr_nuevos"] += 1

    # 3) Saberes básicos: cada item del bloque es una fila independiente.
    for bloque in datos["saberes_basicos"]:
        cod_bloque = bloque["codigo"]
        titulo = bloque["titulo"]
        # Si el boletín numera sus saberes, se respeta su código. Solo cuando
        # no lo hace se cae al contador `bloque.N`.
        #
        # POR QUÉ IMPORTA: ese contador es nuestro, no de ninguna norma. Un
        # docente que lea «A.7» en la programación no lo encuentra en el
        # decreto, y si mañana el extractor lee un saber más, todos los
        # posteriores cambian de número y las SdA ya generadas pasan a citar
        # otro saber distinto sin que nada avise. El BOJA sí los numera
        # —`BYG.1.A.8`—, y ese código es estable y citable.
        codigos = bloque.get("codigos_items") or []
        for idx, item in enumerate(bloque["items"], start=1):
            codigo = codigos[idx - 1] if idx <= len(codigos) else f"{cod_bloque}.{idx}"
            fila, creado = _upsert_saber_item(
                comunidad=comunidad,
                etapa=etapa,
                idioma=idioma,
                codigo=codigo,
                bloque=titulo,
                materia=materia,
                cursos=cursos,
                descripcion=item,
            )
            vistas["saber"].add(fila)
            if creado:
                stats["sb_nuevos"] += 1

    return stats


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def _tablas_de_curriculo():
    """Las tres tablas de currículo, **en orden de hijo a padre**.

    El orden no es cosmético. `CriterioEvaluacion.id_competencia` es una clave
    ajena con ``ondelete="RESTRICT"``, así que borrar una competencia antes que
    sus criterios lanza un IntegrityError y **aborta la carga entera**, no solo
    el borrado. Recorriendo saberes → criterios → competencias, cuando le toca
    a la competencia sus criterios sobrantes ya no están.

    En una estructura y no repetido tres veces porque el borrado tiene que
    tratarlas igual: olvidar una dejaría sobrantes de un tipo y no de otro, que
    es más difícil de detectar que no limpiar nada.
    """
    from ..models.situacion import (
        situacion_competencia, situacion_criterio, situacion_saber,
    )

    return (
        ("saber", SaberBasico, SaberBasico.id_saber,
         situacion_saber, "id_saber"),
        ("criterio", CriterioEvaluacion, CriterioEvaluacion.id_criterio,
         situacion_criterio, "id_criterio"),
        ("competencia", Competencia, Competencia.id_competencia,
         situacion_competencia, "id_competencia"),
    )


def _borrar_sobrantes(
    ambitos_vistos: set[tuple[str, str]], vistas: dict[str, set[int]]
) -> dict[str, int]:
    """Borra lo que quedó de una carga anterior y ya no está en los ficheros.

    POR QUÉ NO ES EL COMPORTAMIENTO POR DEFECTO
    --------------------------------------------
    Porque borra. El seed normal solo añade y actualiza, así que equivocarse de
    directorio no cuesta nada; con esto activado, apuntar a una carpeta a medias
    se llevaría por delante el resto del currículo de esa comunidad.

    LO QUE NO SE BORRA, Y ES DELIBERADO
    ------------------------------------
    Las filas que alguna SdA esté citando. Las tablas de enlace las declaran con
    ``ondelete="RESTRICT"``, así que la base de datos lo impediría de todos
    modos —lanzando un IntegrityError que abortaría la carga entera—, pero la
    razón de fondo es mejor que la técnica: **borrar el saber que una situación
    cita rompe esa situación**. El documento pasaría a decir «(no encontrado en
    el currículo)» donde antes había texto, y el docente no habría hecho nada.

    Así que se informan y se dejan. Son currículo viejo, pero currículo que
    alguien usó. Si de verdad hay que quitarlas, primero hay que decidir qué
    pasa con las SdA que dependen de ellas, y esa decisión no es de un seed.

    EL ÁMBITO ES (COMUNIDAD, ETAPA), Y COSTÓ UN CURRÍCULO ENTERO
    -------------------------------------------------------------
    El 02/09/2026 se recargó Bachillerato del País Vasco con este flag y
    **desapareció la ESO del País Vasco**: 723 criterios y 1480 saberes
    borrados, y solo sobrevivieron los 28 que alguna SdA citaba.

    El filtro miraba la comunidad y nada más, así que todo lo vasco que no
    viniera en esa carpeta era sobrante — y la ESO no venía, porque estaba
    cargando Bachillerato. El comentario que había aquí decía «sin este filtro,
    cargar Cataluña borraría el currículo de Andalucía entero» y el mismo
    razonamiento valía palabra por palabra para la etapa; sencillamente no se
    hizo cuando la etapa entró en el esquema.

    Que la etapa estuviera ya en la clave de los tres upsert no protegía de
    nada: eso evita **sobrescribir**, no borrar. Son dos operaciones distintas
    y solo una se revisó al añadir la columna.
    """
    from sqlalchemy import delete, select as sa_select, update as sa_update, tuple_

    resumen: dict[str, int] = {}
    for tipo, modelo, pk, enlace, col_enlace in _tablas_de_curriculo():
        # Solo de los pares (comunidad, etapa) que esta carga ha tocado. Sin la
        # comunidad, cargar Cataluña borraría el currículo de Andalucía entero;
        # sin la etapa, cargar Bachillerato se lleva la ESO de esa misma
        # comunidad, que es lo que pasó.
        sobrantes = set(db.session.scalars(
            sa_select(pk).where(
                tuple_(modelo.comunidad, modelo.etapa).in_(ambitos_vistos),
                pk.notin_(vistas[tipo] or {-1}),
            )
        ).all())
        if not sobrantes:
            resumen[f"{tipo}_borradas"] = 0
            continue

        enlazadas = set(db.session.scalars(
            sa_select(enlace.c[col_enlace]).where(
                enlace.c[col_enlace].in_(sobrantes)
            )
        ).all())

        # Una competencia tiene además criterios colgando, también con
        # RESTRICT. Los sobrantes ya se habrán borrado —por eso este bucle va
        # de hijo a padre—, pero puede quedar alguno **vigente** apuntando a
        # una competencia que el boletín ya no lista. Es una incoherencia del
        # extractor, no del borrado, y hay que verla en vez de estrellarse
        # contra la clave ajena.
        if modelo is Competencia:
            con_criterios = set(db.session.scalars(
                sa_select(CriterioEvaluacion.id_competencia).where(
                    CriterioEvaluacion.id_competencia.in_(sobrantes)
                )
            ).all())
            if con_criterios - enlazadas:
                logger.warning(
                    "%d competencias sobrantes conservan criterios vigentes: "
                    "no se borran. Apunta a que el extractor cambió el código "
                    "de la competencia pero no el de sus criterios.",
                    len(con_criterios - enlazadas),
                )
            enlazadas |= con_criterios

        libres = sobrantes - enlazadas

        # LAS QUE SE CONSERVAN SE RETIRAN DE LA OFERTA
        # ---------------------------------------------
        # Conservarlas tal cual crea un ciclo del que no se sale. Pasó el
        # 27/08 con el País Vasco: seis saberes con el texto mal extraído
        # sobrevivieron porque una SdA los citaba, siguieron apareciendo en el
        # catálogo que ve el modelo, y **al regenerar esa misma SdA el modelo
        # volvió a citarlos**. A la siguiente carga seguían en uso, así que se
        # conservaban otra vez.
        #
        # Vaciar `cursos_aplicables` los saca del contexto sin borrarlos:
        # `contexto.py` filtra con el operador `?` de JSONB, que con la lista
        # vacía no casa con ningún curso —la decisión del 16/08 sobre qué
        # significa una fila sin cursos—. La SdA que ya los cita no se entera:
        # la exportación lee el texto por la relación ya enlazada y no vuelve
        # a filtrar por curso.
        #
        # Con eso el ciclo se cierra solo: nadie los vuelve a citar, y en la
        # carga siguiente a que se regenere esa SdA ya se pueden borrar.
        if enlazadas:
            db.session.execute(
                sa_update(modelo)
                .where(pk.in_(enlazadas))
                .values(cursos_aplicables=[]),
                execution_options={"synchronize_session": False},
            )

        if libres:
            # `synchronize_session=False`: es un borrado masivo por clave y no
            # hace falta que la sesión reconcilie objeto a objeto. Con la
            # estrategia por defecto, SQLAlchemy intenta casar cada fila con lo
            # que tiene en memoria y aquí eso es trabajo inútil sobre miles.
            db.session.execute(
                delete(modelo).where(pk.in_(libres)),
                execution_options={"synchronize_session": False},
            )
        resumen[f"{tipo}_borradas"] = len(libres)
        resumen[f"{tipo}_en_uso"] = len(enlazadas)

        logger.info(
            "%s: %d sobrantes, %d borradas, %d conservadas por estar citadas "
            "en alguna SdA", tipo, len(sobrantes), len(libres), len(enlazadas),
        )
        if enlazadas:
            logger.warning(
                "%d filas de %s ya no están en el boletín pero las cita alguna "
                "situación de aprendizaje: se conservan. Borrarlas dejaría esas "
                "SdA citando algo que no existe.", len(enlazadas), tipo,
            )

    # Contrapartida de `synchronize_session=False`: la sesión sigue teniendo en
    # memoria objetos de filas que ya no existen. Si alguno estuviera sucio, el
    # commit intentaría un UPDATE contra una fila borrada y saltaría
    # `StaleDataError` al final de la carga, lejos de aquí. Expirarlos obliga a
    # releer y cierra el hueco.
    db.session.expire_all()
    return resumen


def seed_curriculo(
    directorio: Path | None = None,
    *,
    comunidad: str | None = None,
    idioma: str | None = None,
    borrar_sobrantes: bool = False,
) -> dict[str, int]:
    """Carga todos los ficheros JSON del directorio indicado.

    Es idempotente: ejecutarla de nuevo solo actualizará textos cambiados
    sin generar duplicados.

    Con ``borrar_sobrantes`` se hace además una **recarga limpia**: lo que
    quede de esa comunidad y no esté en los ficheros se borra. Ver
    `_borrar_sobrantes` para por qué no es la opción por defecto.

    ``comunidad`` e ``idioma`` son el valor **de respaldo** para los ficheros
    que no lo traigan dentro. Por defecto, Ceuta en castellano: es lo que son
    todos los JSON existentes, que salen de la Orden EFP/754 —la del ámbito de
    gestión del Ministerio—.

    Se valida la comunidad contra el catálogo antes de escribir nada. Cargar
    dos mil filas bajo un código inventado y descubrirlo después obligaría a
    borrarlas a mano, y no hay ningún comando para eso.
    """
    from ..curriculo import comunidades

    codigo = comunidades.normalizar(comunidad) if comunidad else comunidades.POR_DEFECTO
    if codigo is None:
        raise ValueError(
            f"Comunidad no reconocida: {comunidad!r}. "
            f"Válidas: {', '.join(sorted(comunidades.COMUNIDADES))}"
        )
    lengua = (idioma or "es").strip().lower()
    base = directorio or RUTA_SALIDA_DEFECTO
    ficheros = sorted(base.glob("*.json"))
    if not ficheros:
        logger.warning("No se han encontrado ficheros JSON en %s", base)
        return {
            "ficheros": 0,
            "ce_nuevas": 0,
            "ce_actualizadas": 0,
            "cr_nuevos": 0,
            "sb_nuevos": 0,
        }

    total = {"ce_nuevas": 0, "ce_actualizadas": 0, "cr_nuevos": 0, "sb_nuevos": 0}
    # «Por defecto», y dicho así a propósito. Este mensaje se emite **antes de
    # abrir ningún fichero**, así que solo puede enseñar la opción de la orden;
    # pero manda lo que traiga dentro cada JSON. Cargando Andalucía imprimía
    # «Cargando currículo de ceuta», que es exactamente lo contrario de lo que
    # estaba pasando, y quien lea el log tiene que poder fiarse de él.
    logger.info(
        "Cargando currículo desde %s (por defecto %s/%s; manda lo que diga "
        "cada fichero)", base, codigo, lengua,
    )
    comunidades_vistas: set[str] = set()
    #: Pares (comunidad, etapa) que esta carga toca. Es el ámbito del borrado
    #: de sobrantes: fuera de él no se toca nada.
    ambitos_vistos: set[tuple[str, str]] = set()
    vistas: dict[str, set[int]] = {"competencia": set(), "criterio": set(), "saber": set()}
    for ruta in ficheros:
        logger.info("Procesando %s", ruta.name)
        stats = _procesar_fichero(ruta, codigo, lengua)
        for k, v in stats.items():
            if k in total:
                total[k] += v
        comunidades_vistas.add(str(stats.get("comunidad") or codigo))
        ambitos_vistos.add((str(stats.get("comunidad") or codigo),
                            str(stats.get("etapa") or "ESO")))
        for tipo, ids in (stats.get("vistas") or {}).items():
            vistas[tipo] |= ids

    if borrar_sobrantes:
        # Un solo flush para toda la carga: asigna de golpe los identificadores
        # de lo insertado, que es lo que hace falta para saber qué NO se ha
        # visto. Sin él, las filas nuevas no tendrían id y se tomarían por
        # sobrantes — o sea, se borraría justo lo que se acaba de escribir.
        db.session.flush()
        ids = {
            tipo: {getattr(o, campo) for o in objetos}
            for tipo, campo, objetos in (
                ("competencia", "id_competencia", vistas["competencia"]),
                ("criterio", "id_criterio", vistas["criterio"]),
                ("saber", "id_saber", vistas["saber"]),
            )
        }
        total.update(_borrar_sobrantes(ambitos_vistos, ids))

    db.session.commit()
    total["ficheros"] = len(ficheros)
    # Lo que se cargó de verdad, que es el dato con el que se comprueba.
    logger.info(
        "Cargado currículo de %s desde %d ficheros",
        ", ".join(sorted(comunidades_vistas)), len(ficheros),
    )
    return total
