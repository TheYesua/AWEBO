"""Comandos CLI personalizados expuestos vía ``flask <grupo> <comando>``."""
from __future__ import annotations

import click
from flask import Flask
from flask.cli import AppGroup


seed_cli = AppGroup("seed", help="Carga datos iniciales en la base de datos.")


@seed_cli.command("roles")
def cmd_seed_roles() -> None:
    """Inserta los roles del sistema (docente, administrador)."""
    from .seeds import seed_roles

    result = seed_roles()
    click.echo(
        f"[seed:roles] creados={result['creados']} actualizados={result['actualizados']}"
    )


@seed_cli.command("ods")
def cmd_seed_ods() -> None:
    """Inserta los 17 Objetivos de Desarrollo Sostenible."""
    from .seeds import seed_ods

    result = seed_ods()
    click.echo(
        f"[seed:ods] creados={result['creados']} actualizados={result['actualizados']}"
    )


@seed_cli.command("curriculo")
@click.option(
    "--directorio",
    "-d",
    default=None,
    help="Directorio con los JSON del extractor (por defecto /curriculo/salida).",
)
@click.option(
    "--comunidad",
    default=None,
    help="De qué comunidad es este currículo. Por defecto, ceuta.",
)
@click.option(
    "--idioma",
    default=None,
    help="Lengua en que publica el boletín de origen. Por defecto, es.",
)
@click.option(
    "--borrar-sobrantes",
    is_flag=True,
    default=False,
    help=(
        "Recarga limpia: borra lo que quede de esa comunidad y ya no esté en "
        "los ficheros. NO borra lo que cite alguna SdA. Sin esta opción el "
        "seed solo añade y actualiza, que es lo seguro."
    ),
)
def cmd_seed_curriculo(
    directorio: str | None,
    comunidad: str | None,
    idioma: str | None,
    borrar_sobrantes: bool,
) -> None:
    """Carga competencias, criterios y saberes desde los JSON del extractor.

    Si un JSON trae dentro su `comunidad` o su `idioma`, **el fichero manda**
    sobre estas opciones: el dato correcto es el del extractor, no el de quien
    teclea la orden.
    """
    from pathlib import Path

    from .seeds import seed_curriculo

    ruta = Path(directorio) if directorio else None
    try:
        result = seed_curriculo(
            ruta, comunidad=comunidad, idioma=idioma,
            borrar_sobrantes=borrar_sobrantes,
        )
    except ValueError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1)
    click.echo(
        f"[seed:curriculo] ficheros={result['ficheros']} "
        f"ce_nuevas={result['ce_nuevas']} ce_actualizadas={result['ce_actualizadas']} "
        f"cr_nuevos={result['cr_nuevos']} sb_nuevos={result['sb_nuevos']}"
    )
    if borrar_sobrantes:
        borradas = sum(v for k, v in result.items() if k.endswith("_borradas"))
        en_uso = sum(v for k, v in result.items() if k.endswith("_en_uso"))
        click.echo(f"[seed:curriculo] sobrantes borradas={borradas}")
        if en_uso:
            # Se dice aparte y siempre, no solo en el log: es lo que explica
            # que el recuento no cuadre con lo que trae el boletín.
            click.echo(
                f"[seed:curriculo] {en_uso} filas obsoletas se CONSERVAN porque "
                f"alguna SdA las cita. Borrarlas la dejaría citando algo "
                f"inexistente."
            )


@seed_cli.command("all")
def cmd_seed_all() -> None:
    """Ejecuta todos los seeds disponibles en orden."""
    from .seeds import seed_roles, seed_ods, seed_curriculo

    r = seed_roles()
    click.echo(f"[seed:roles] creados={r['creados']} actualizados={r['actualizados']}")
    o = seed_ods()
    click.echo(f"[seed:ods] creados={o['creados']} actualizados={o['actualizados']}")
    c = seed_curriculo()
    click.echo(
        f"[seed:curriculo] ficheros={c['ficheros']} "
        f"ce_nuevas={c['ce_nuevas']} ce_actualizadas={c['ce_actualizadas']} "
        f"cr_nuevos={c['cr_nuevos']} sb_nuevos={c['sb_nuevos']}"
    )


usuarios_cli = AppGroup("usuarios", help="Gestión de cuentas desde la consola.")


@usuarios_cli.command("listar-admins")
def cmd_listar_admins() -> None:
    """Muestra qué cuentas tienen rol de administrador."""
    from sqlalchemy import select

    from .extensions import db
    from .models import Rol, Usuario

    filas = db.session.scalars(
        select(Usuario).join(Rol).where(Rol.nombre == Rol.ADMINISTRADOR)
        .order_by(Usuario.correo)
    ).all()

    if not filas:
        click.echo("No hay ninguna cuenta de administrador.")
        click.echo("Crea una con:  flask usuarios crear-admin")
        return

    click.echo(f"{len(filas)} cuenta(s) de administrador:")
    for u in filas:
        # Se marcan las que tienen lápida: cuentan como administradoras en la
        # tabla pero no pueden iniciar sesión, así que ver «hay 1 admin» sin
        # este aviso llevaría a pensar que se puede entrar.
        estado = " [DADA DE BAJA · no puede entrar]" if u.esta_eliminado else ""
        click.echo(f"  · {u.correo}  ({u.nombre}){estado}")


@usuarios_cli.command("crear-admin")
@click.option("--correo", prompt="Correo", help="Correo de la cuenta.")
@click.option("--nombre", prompt="Nombre completo", help="Nombre de la persona.")
@click.password_option(
    "--contrasena",
    prompt="Contraseña",
    confirmation_prompt="Repite la contraseña",
    help="Se pide de forma interactiva; no la pases como argumento.",
)
def cmd_crear_admin(correo: str, nombre: str, contrasena: str) -> None:
    """Crea una cuenta con rol de administrador.

    La contraseña se pide de forma interactiva y oculta. Pasarla como argumento
    la dejaría en el historial del intérprete de órdenes y visible en la lista
    de procesos mientras dura el comando.

    Se apoya en ``registrar_usuario``, el mismo servicio que usa el registro
    web, así que el hasheado y la política de contraseñas son los mismos.

    Lo segundo no era cierto cuando se escribió este comentario: la política
    vivía duplicada en tres validadores Pydantic y ninguno cubría este camino,
    de modo que el comando creaba administradores con la contraseña que fuera.
    Se movió a ``auth_service.validar_contrasena``, que ``registrar_usuario``
    aplica siempre. Hay un test que lo comprueba desde aquí.
    """
    from .services.auth_service import AuthError, registrar_usuario
    from .models import Rol

    try:
        usuario = registrar_usuario(
            correo=correo,
            contrasena=contrasena,
            nombre=nombre,
            rol_nombre=Rol.ADMINISTRADOR,
        )
    except AuthError as exc:
        if exc.code == "correo_duplicado":
            click.echo(f"Ya existe una cuenta con {correo}.", err=True)
            click.echo("Para darle el rol:  flask usuarios promover " + correo, err=True)
        elif exc.code == "reclamacion_pendiente":
            # registrar_usuario, ante un correo con lápida, deja una solicitud
            # en vez de crear nada. Aquí eso no es lo que se ha pedido.
            click.echo(
                f"{correo} corresponde a una cuenta dada de baja. Se ha "
                "registrado una solicitud de reclamación, pero NO se ha creado "
                "ninguna cuenta.",
                err=True,
            )
            click.echo(
                "Resuélvela desde el panel, o usa otro correo.", err=True
            )
        elif exc.code == "contrasena_debil":
            click.echo(str(exc), err=True)
        elif exc.code == "rol_inexistente":
            click.echo(
                "No existe el rol 'administrador'. Ejecuta antes:  flask seed roles",
                err=True,
            )
        else:
            click.echo(f"No se pudo crear: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"Administrador creado: {usuario.correo} (id={usuario.id_usuario})")


@usuarios_cli.command("promover")
@click.argument("correo")
def cmd_promover(correo: str) -> None:
    """Da rol de administrador a una cuenta que ya existe."""
    from sqlalchemy import select

    from .extensions import db
    from .models import Rol, Usuario

    usuario = db.session.scalar(
        select(Usuario).where(Usuario.correo == correo.lower().strip())
    )
    if usuario is None:
        click.echo(f"No existe ninguna cuenta con {correo}.", err=True)
        raise SystemExit(1)

    rol = db.session.scalar(select(Rol).where(Rol.nombre == Rol.ADMINISTRADOR))
    if rol is None:
        click.echo("No existe el rol 'administrador'. Ejecuta:  flask seed roles", err=True)
        raise SystemExit(1)

    if usuario.id_rol == rol.id_rol:
        click.echo(f"{usuario.correo} ya es administrador.")
        return

    usuario.id_rol = rol.id_rol
    db.session.commit()
    click.echo(f"{usuario.correo} ahora es administrador.")

    if usuario.esta_eliminado:
        # Promover no levanta la lápida a propósito: son dos decisiones
        # distintas y juntarlas haría que dar permisos reactivara una cuenta
        # dada de baja sin que nadie lo pidiera.
        click.echo(
            "Aviso: la cuenta está dada de baja y sigue sin poder iniciar sesión.",
            err=True,
        )


@usuarios_cli.command("proveedor")
@click.argument("correo")
@click.option("--proveedor", help="openai, gemini… o vacío para usar el del sistema.")
@click.option("--modelo", default=None, help="Modelo concreto. Si falta, el por defecto.")
def cmd_proveedor(correo: str, proveedor: str | None, modelo: str | None) -> None:
    """Fija con qué proveedor de IA genera una cuenta.

    POR QUÉ HACE FALTA DESDE LA CONSOLA
    ------------------------------------
    El proveedor sale de las preferencias del **propietario de la SdA**. Las
    situaciones heredadas del TFG son de cuentas de prueba —`estudio@ejemplo.com`
    y similares— cuya contraseña puede que nadie recuerde, así que cambiar su
    preferencia por la interfaz exige entrar como ellas.

    Sin `--proveedor` **muestra** la preferencia actual en vez de cambiarla. Un
    comando que informa cuando no se le pide nada es más difícil de usar por
    error que uno que borre la preferencia al invocarlo sin argumentos.

    La elección se valida contra el catálogo, igual que en el perfil: si ese
    proveedor no está disponible en este despliegue se avisa **en vez de
    guardarlo en silencio**. Guardar algo que luego se ignora es justo lo que
    hizo perder una tarde persiguiendo por qué las regeneraciones seguían
    yendo a Gemini.
    """
    from sqlalchemy import select

    from .ai import catalogo
    from .extensions import db
    from .models import Usuario

    usuario = db.session.scalar(
        select(Usuario).where(Usuario.correo == correo.lower().strip())
    )
    if usuario is None:
        click.echo(f"No hay ninguna cuenta con el correo {correo}.", err=True)
        raise SystemExit(1)

    sistema, modelo_sistema = catalogo.por_defecto()

    if proveedor is None:
        actual = usuario.proveedor_ia or "—"
        click.echo(f"{usuario.correo}: {actual}/{usuario.modelo_ia or '—'}")
        if not usuario.proveedor_ia:
            click.echo(f"  usa el del sistema: {sistema}/{modelo_sistema}")
        click.echo("\nPara cambiarlo:  --proveedor openai [--modelo gpt-5.4]")
        return

    if not proveedor.strip():
        usuario.proveedor_ia = None
        usuario.modelo_ia = None
        db.session.commit()
        click.echo(f"{usuario.correo}: ahora usa el del sistema ({sistema}/{modelo_sistema}).")
        return

    validado, modelo_validado = catalogo.validar(proveedor, modelo)
    if validado is None:
        nombres = ", ".join(p.nombre for p in catalogo.disponibles()) or "ninguno"
        click.echo(
            f"«{proveedor}» no está disponible en este despliegue. "
            f"Disponibles: {nombres}. No se ha guardado nada.",
            err=True,
        )
        raise SystemExit(1)

    if modelo and modelo_validado != modelo:
        click.echo(
            f"El modelo «{modelo}» no está en el catálogo de {validado}; "
            f"se usará {modelo_validado}.",
            err=True,
        )

    usuario.proveedor_ia = validado
    usuario.modelo_ia = modelo_validado
    db.session.commit()
    click.echo(f"{usuario.correo}: ahora genera con {validado}/{modelo_validado}.")


# ---------------------------------------------------------------------------
# Currículo
# ---------------------------------------------------------------------------

curriculo_cli = AppGroup("curriculo", help="Mantenimiento del catálogo curricular.")


@curriculo_cli.command("enlazar")
@click.option(
    "--simular",
    is_flag=True,
    help="Solo informa: no escribe nada en la base de datos.",
)
def enlazar(simular: bool) -> None:
    """Rehace los enlaces entre las SdA y el catálogo curricular.

    Hace falta una sola vez, para las situaciones creadas antes de que esto
    existiera: las nuevas se enlazan solas al generarse. También sirve después
    de tocar el catálogo —renombrar una materia, recargar el currículo— para
    ver qué SdA se han quedado apuntando al vacío.

    ``--simular`` es lo que se ejecuta primero. Este comando reasigna enlaces,
    y sobre 39 situaciones eso es barato, pero conviene ver el recuento de
    huérfanos antes de escribir nada: si sale disparado, el problema no son
    las SdA sino que el catálogo cargado no es el que se cree.
    """
    # Importes dentro de la función, como el resto de comandos de este fichero:
    # a nivel de módulo crearían un ciclo con la aplicación.
    #
    # `select` se quedó fuera y el comando reventó con `NameError` en la
    # primera ejecución real. No lo detectó nada porque la comprobación que
    # hice fue `import app.cli`, e importar un módulo **no ejecuta el cuerpo de
    # sus funciones**: un nombre que solo se usa dentro de una función no falta
    # hasta que alguien la llama. Ahora hay un test que la llama.
    from sqlalchemy import select

    from .extensions import db
    from .models import SituacionAprendizaje
    from .services.enlaces_curriculares import sincronizar

    situaciones = db.session.scalars(select(SituacionAprendizaje)).all()
    if not situaciones:
        click.echo("No hay situaciones que enlazar.")
        return

    totales = {"competencias": 0, "criterios": 0, "saberes": 0}
    con_huerfanos: list[tuple[int, dict]] = []
    sin_curriculo: list[tuple[int, str, str]] = []
    fallidas = 0

    for sa in situaciones:
        resumen = sincronizar(sa, commit=False)
        if resumen.get("error"):
            fallidas += 1
            continue
        for clave in totales:
            totales[clave] += resumen.get(clave, 0)
        # Las dos causas van por separado. Juntarlas fue el error de la primera
        # versión: anunció 17 SdA como «códigos que el modelo se inventó»
        # cuando ninguna lo era.
        if resumen.get("sin_curriculo"):
            if resumen.get("huerfanos"):
                sin_curriculo.append((sa.id_situacion, sa.materia, sa.curso))
        elif resumen.get("huerfanos"):
            con_huerfanos.append((sa.id_situacion, resumen["huerfanos"]))

    if simular:
        db.session.rollback()
    else:
        db.session.commit()

    click.echo(
        f"{len(situaciones)} situaciones · "
        f"{totales['competencias']} competencias, {totales['criterios']} criterios, "
        f"{totales['saberes']} saberes"
        + (" (simulado, no se ha escrito nada)" if simular else "")
    )
    if fallidas:
        click.echo(f"{fallidas} situaciones fallaron; mira el registro.", err=True)

    if sin_curriculo:
        # Se informa primero porque es la causa que más veces se cumple y la
        # única que no se arregla regenerando: la SdA apunta a una pareja que
        # no existe, y decidir qué hacer con ella —renombrar la materia,
        # separarla en dos, dejarla— cambia lo que la aplicación le afirma a un
        # docente. No es una decisión del comando.
        parejas = sorted({(m, c) for _id, m, c in sin_curriculo})
        click.echo(
            f"\n{len(sin_curriculo)} situaciones NO tienen currículo cargado para su "
            f"materia y curso, así que ningún código suyo puede casar. No son "
            f"códigos inventados: están ancladas a una pareja que no existe.",
            err=True,
        )
        for materia, curso in parejas:
            cuantas = sum(1 for _i, m, c in sin_curriculo if (m, c) == (materia, curso))
            click.echo(f"  {materia} · {curso} — {cuantas} situaciones", err=True)

    if con_huerfanos:
        click.echo(
            f"\n{len(con_huerfanos)} situaciones citan códigos que no existen, "
            f"teniendo currículo cargado para su materia y curso. Estos sí son "
            f"códigos que el modelo se inventó:",
            err=True,
        )
        for id_situacion, huerfanos in con_huerfanos[:20]:
            detalle = "; ".join(f"{k}: {', '.join(v)}" for k, v in huerfanos.items())
            click.echo(f"  SdA {id_situacion} — {detalle}", err=True)
        if len(con_huerfanos) > 20:
            click.echo(f"  … y {len(con_huerfanos) - 20} más.", err=True)

    if not sin_curriculo and not con_huerfanos:
        click.echo("Todos los códigos casan con el catálogo.")


#: Reasignaciones mecánicas: la pareja de origen tiene un destino único y
#: comprobable contra la Orden EFP/754. No hay nada que decidir.
#:
#: `Matemáticas · 4º ESO` NO está aquí, y es deliberado: en 4º existen
#: Matemáticas A y Matemáticas B, y cuál toca depende del contenido de la SdA,
#: no de una regla. Se pregunta.
_REASIGNACIONES: dict[tuple[str, str], tuple[str, str]] = {
    # En el catálogo la materia se llama «Lengua»: es un mapeo deliberado a la
    # etiqueta histórica, documentado en `_MATERIAS_ORDEN_754`. Solo cambia el
    # nombre; el curso es correcto.
    ("Lengua Castellana y Literatura", "1º ESO"): ("Lengua", "1º ESO"),
    ("Lengua Castellana y Literatura", "2º ESO"): ("Lengua", "2º ESO"),
    ("Lengua Castellana y Literatura", "3º ESO"): ("Lengua", "3º ESO"),
    ("Lengua Castellana y Literatura", "4º ESO"): ("Lengua", "4º ESO"),
    # «Tecnología y Digitalización» es de 2º y 3º; en 4º la materia se llama
    # «Tecnología». Se conserva el curso, que es lo que el docente eligió, y se
    # corrige el nombre, que es lo que estaba mal.
    ("Tecnología y Digitalización", "4º ESO"): ("Tecnología", "4º ESO"),
}


@curriculo_cli.command("reasignar")
@click.option("--simular", is_flag=True, help="Solo informa: no escribe nada.")
@click.option(
    "--matematicas",
    type=click.Choice(["A", "B", "preguntar"]),
    default="preguntar",
    help="Qué itinerario asignar a las SdA de «Matemáticas · 4º ESO».",
)
@click.option(
    "--regenerar",
    is_flag=True,
    help="Encola la regeneración completa de cada SdA reasignada.",
)
def reasignar(simular: bool, matematicas: str, regenerar: bool) -> None:
    """Arregla las SdA ancladas a una pareja (materia, curso) inexistente.

    Son las creadas antes de que el formulario validara la pareja. Guarda una
    versión con el estado anterior de cada una, así que la reasignación se
    puede deshacer desde el historial.

    **Reasignar no arregla el contenido.** Los códigos del JSONB se generaron
    contra un currículo que no era el suyo, así que hasta regenerar la SdA
    seguirá citando criterios que no le corresponden — y ahora, además,
    aparecerán como códigos inventados, porque la pareja ya tiene currículo.
    Por eso existe `--regenerar`, y por eso el comando insiste si no se usa.
    """
    from sqlalchemy import select

    from .extensions import db
    from .models import SituacionAprendizaje
    from .services import situacion_service as svc
    from .services.enlaces_curriculares import hay_curriculo, sincronizar
    from .tasks import encolar
    from .tasks import generacion as tareas_generacion

    situaciones = db.session.scalars(select(SituacionAprendizaje)).all()
    huerfanas = [
        sa for sa in situaciones if not hay_curriculo(sa.materia, sa.curso)
    ]
    if not huerfanas:
        click.echo("Ninguna situación está anclada a una pareja inexistente.")
        return

    click.echo(f"{len(huerfanas)} situaciones sin currículo para su materia y curso.\n")

    reasignadas: list[tuple[int, str, str]] = []
    sin_regla: list[tuple[int, str, str]] = []

    for sa in huerfanas:
        origen = (sa.materia, sa.curso)
        destino = _REASIGNACIONES.get(origen)

        if destino is None and origen == ("Matemáticas", "4º ESO"):
            destino = _elegir_matematicas(sa, matematicas)

        if destino is None:
            sin_regla.append((sa.id_situacion, sa.materia, sa.curso))
            continue

        materia, curso = destino
        click.echo(
            f"  SdA {sa.id_situacion} «{sa.titulo[:40]}»  "
            f"{sa.materia} · {sa.curso}  →  {materia} · {curso}"
        )
        if not simular:
            svc.reasignar_curriculo(
                sa,
                materia=materia,
                curso=curso,
                motivo=(
                    f"Reasignación curricular: {origen[0]} · {origen[1]} no existe "
                    f"en el catálogo."
                ),
            )
            sincronizar(sa)
        reasignadas.append((sa.id_situacion, materia, curso))

    if sin_regla:
        click.echo(
            f"\n{len(sin_regla)} sin regla de reasignación. Hay que decidirlas a "
            f"mano y añadirlas a `_REASIGNACIONES`:",
            err=True,
        )
        for id_situacion, materia, curso in sin_regla:
            click.echo(f"  SdA {id_situacion} — {materia} · {curso}", err=True)

    if simular:
        db.session.rollback()
        click.echo(f"\n{len(reasignadas)} se reasignarían (simulado, no se ha escrito nada).")
        return

    click.echo(f"\n{len(reasignadas)} reasignadas. El estado anterior queda en el historial.")

    if regenerar:
        for id_situacion, _m, _c in reasignadas:
            encolar(tareas_generacion.generar_situacion_completa, id_situacion)
        click.echo(
            f"{len(reasignadas)} regeneraciones encoladas. Consumen API de pago y "
            f"tardan; sigue el avance en el log del worker."
        )
    elif reasignadas:
        click.echo(
            "\nAVISO: no se ha regenerado nada. El contenido de esas SdA sigue "
            "citando el currículo anterior, así que ahora aparecerán como "
            "códigos inventados —esta vez con razón—. Vuelve a lanzarlo con "
            "--regenerar cuando quieras arreglarlo.",
            err=True,
        )


def _elegir_matematicas(sa, modo: str) -> tuple[str, str] | None:
    """Matemáticas A o B para una SdA de 4º ESO.

    NO SE DECIDE POR REGLA, Y ESE ES EL PUNTO
    ------------------------------------------
    En 4º de ESO, Matemáticas A y Matemáticas B no son niveles de la misma
    asignatura: son itinerarios con currículos distintos —A orientada a la
    aplicación, B a la continuidad hacia el bachillerato científico—. Elegir
    por defecto sería decidir por el docente qué asignatura imparte, y eso
    cambia lo que la aplicación le afirma.

    Así que por defecto se le enseña el título y se pregunta. `--matematicas A`
    o `B` existe para cuando ya se ha decidido y no apetece contestar siete
    veces, no como atajo para no mirar.
    """
    if modo in ("A", "B"):
        return (f"Matemáticas {modo}", "4º ESO")

    click.echo(f"\n  SdA {sa.id_situacion}: «{sa.titulo}»")
    if sa.descripcion:
        click.echo(f"    {sa.descripcion[:160]}")
    click.echo(
        "    Matemáticas A = orientada a la aplicación · "
        "Matemáticas B = continuidad hacia el bachillerato científico"
    )
    eleccion = click.prompt(
        "    ¿A, B o s para saltarla?",
        type=click.Choice(["A", "B", "s"], case_sensitive=False),
        default="A",
        show_default=True,
    ).upper()
    if eleccion == "S":
        return None
    return (f"Matemáticas {eleccion}", "4º ESO")


@curriculo_cli.command("estado")
@click.option(
    "--codigo-de-salida",
    is_flag=True,
    help="Termina con código 1 mientras queden generaciones en curso.",
)
def estado(codigo_de_salida: bool) -> None:
    """Cuántas SdA siguen generándose, cuántas fallaron y cuántas están listas.

    PARA QUÉ
    --------
    Después de `reasignar --regenerar` quedan varias tareas en la cola, y
    seguirlas en el log del worker obliga a leer líneas sueltas y llevar la
    cuenta a mano. Esto lo cuenta contra la base de datos, que es donde está
    el estado de verdad.

    ``--codigo-de-salida`` existe para poder esperar desde un script sin
    analizar el texto:

        while (-not (docker compose exec -T api flask curriculo estado --codigo-de-salida)) {
            Start-Sleep 30
        }

    OJO: `error_generacion` significa DOS cosas distintas
    ------------------------------------------------------
    Se escribió aquí que una generación en error «no vuelve sola». **Es falso a
    medias**, y lo desmintieron los datos de una ejecución real: SdA que
    figuraban en error pasaron a `generada` sin que nadie tocara nada.

    El motivo está en `generar_situacion_completa`: ante un `LLMProviderError`
    marca la SdA como `error_generacion` **y luego relanza**, para que
    `autoretry_for` la reintente. Con `max_retries=2` y espera creciente, una
    SdA puede pasar minutos en ese estado y acabar bien.

    Así que el estado no distingue «falló y va a reintentarlo» de «falló y ahí
    se queda». Mientras `generando` no llegue a cero, un `error_generacion` es
    provisional; solo cuando no queda ninguna en curso —y ha pasado el último
    reintento— es definitivo.

    Distinguirlos de verdad pediría una columna nueva o consultar el backend de
    Celery. Por ahora se dice en la salida, que es barato y evita el error de
    lectura; anotado como deuda.
    """
    from sqlalchemy import func, select

    from .extensions import db
    from .models import SituacionAprendizaje

    filas = db.session.execute(
        select(SituacionAprendizaje.estado, func.count())
        .group_by(SituacionAprendizaje.estado)
    ).all()
    conteo = {estado: n for estado, n in filas}

    generando = conteo.get(SituacionAprendizaje.GENERANDO, 0)
    con_error = conteo.get(SituacionAprendizaje.ERROR_GENERACION, 0)
    total = sum(conteo.values())

    click.echo(f"{total} situaciones en total")
    for nombre in SituacionAprendizaje.ESTADOS:
        if conteo.get(nombre):
            click.echo(f"  {nombre:20s} {conteo[nombre]}")

    if generando:
        click.echo(f"\nQuedan {generando} generándose.")
        if con_error:
            # El matiz que evita relanzar por encima de un reintento en curso.
            click.echo(
                f"  Hay {con_error} en error, pero mientras queden en curso ese "
                f"número es PROVISIONAL: una que falla se marca así y se "
                f"reintenta sola (hasta 2 veces). Espera a que no quede ninguna."
            )
    elif con_error:
        click.echo(
            f"\nNinguna en curso y {con_error} en error. Ahora sí es definitivo: "
            f"se agotaron los reintentos."
        )
    else:
        click.echo("\nNinguna en curso y ninguna en error.")

    if con_error:
        # Con sus ids: son las que hay que volver a lanzar a mano, y buscarlas
        # después obliga a repetir la consulta.
        ids = db.session.scalars(
            select(SituacionAprendizaje.id_situacion).where(
                SituacionAprendizaje.estado == SituacionAprendizaje.ERROR_GENERACION
            )
        ).all()
        click.echo(f"  En error: {', '.join(str(i) for i in ids)}", err=True)

    # Línea canónica para scripts, al final y con formato fijo.
    #
    # `esperar.ps1` buscaba la frase «terminaron en error», y al reescribir ese
    # mensaje dejó de detectarlos sin que nada avisara: un script acoplado a
    # una frase en prosa se rompe la primera vez que alguien mejora la
    # redacción. Esta línea existe para que la prosa pueda cambiar libremente.
    click.echo(f"\nRESUMEN generando={generando} error={con_error} total={total}")

    if codigo_de_salida and generando:
        raise SystemExit(1)


@curriculo_cli.command("regenerar")
@click.option(
    "--espaciado",
    type=int,
    default=0,
    help="Segundos entre una generación y la siguiente. 0 = todas a la vez.",
)
@click.option("--simular", is_flag=True, help="Solo dice cuáles relanzaría.")
def regenerar(espaciado: int, simular: bool) -> None:
    """Vuelve a lanzar las SdA que quedaron en `error_generacion`.

    POR QUÉ HACE FALTA
    ------------------
    Una generación fallida **no vuelve sola**: la tarea marca la SdA como
    `error_generacion` y ahí se queda. Sin esto, recuperar un lote obliga a
    entrar en cada SdA por la interfaz y pulsar regenerar una por una.

    QUÉ HACE `--espaciado`, Y POR QUÉ NO ES UN ADORNO
    --------------------------------------------------
    Encolar veinte generaciones de golpe manda veinte peticiones casi
    simultáneas al proveedor de IA. Si el fallo del lote anterior fue un límite
    de peticiones por minuto, repetir la misma ráfaga reproduce el mismo fallo
    y no se aprende nada. Con `--espaciado 30` salen de una en una, separadas.

    Se usa `apply_async(countdown=...)` en vez de `encolar`, que es la
    convención del proyecto, porque `encolar` no admite `countdown`: propaga el
    `request_id` de la petición, y aquí no hay petición que propagar.

    NO SE LANZA SI HAY GENERACIONES EN CURSO
    -----------------------------------------
    Una SdA marcada `error_generacion` puede estar esperando su reintento
    automático. Relanzarla entonces pondría dos generaciones sobre la misma
    SdA, que se pisarían sección a sección. Así que el comando se planta si hay
    algo en curso, en vez de dejar que quien lo lanza adivine el momento.

    OJO CON EL CONTENIDO A MEDIAS
    ------------------------------
    La generación guarda cada sección en cuanto la termina, así que una SdA que
    falló a mitad tiene unas secciones nuevas y otras viejas. Regenerar las
    reescribe todas, que es lo que se quiere; pero conviene saber que el estado
    de partida no es «como estaba antes».
    """
    from sqlalchemy import func, select

    from .extensions import db
    from .models import SituacionAprendizaje
    from .tasks import generacion as tareas_generacion

    en_curso = db.session.scalar(
        select(func.count()).select_from(SituacionAprendizaje).where(
            SituacionAprendizaje.estado == SituacionAprendizaje.GENERANDO
        )
    )
    if en_curso:
        click.echo(
            f"Hay {en_curso} generándose ahora mismo. Algunas de las que figuran "
            f"en error pueden estar esperando su reintento automático, y "
            f"relanzarlas ahora pondría dos generaciones sobre la misma SdA.\n"
            f"Espera a que `flask curriculo estado` no muestre ninguna en curso.",
            err=True,
        )
        raise SystemExit(1)

    ids = db.session.scalars(
        select(SituacionAprendizaje.id_situacion).where(
            SituacionAprendizaje.estado == SituacionAprendizaje.ERROR_GENERACION
        ).order_by(SituacionAprendizaje.id_situacion)
    ).all()

    if not ids:
        click.echo("Ninguna situación en error. No hay nada que relanzar.")
        return

    click.echo(f"{len(ids)} en error: {', '.join(str(i) for i in ids)}")
    if simular:
        click.echo("Simulado: no se ha encolado nada.")
        return

    for posicion, id_situacion in enumerate(ids):
        tareas_generacion.generar_situacion_completa.apply_async(
            args=[id_situacion], countdown=posicion * espaciado
        )

    if espaciado:
        minutos = (len(ids) - 1) * espaciado / 60
        click.echo(
            f"{len(ids)} encoladas, una cada {espaciado}s: la última empieza "
            f"en unos {minutos:.0f} min."
        )
    else:
        click.echo(
            f"{len(ids)} encoladas de golpe. Si el lote anterior falló por un "
            f"límite de peticiones del proveedor, esto lo repetirá: prueba con "
            f"--espaciado 30."
        )
    click.echo("Sigue el avance con:  flask curriculo estado")


ia_cli = AppGroup("ia", help="Diagnóstico del proveedor de IA.")


@ia_cli.command("diagnostico")
@click.option(
    "--situaciones",
    default="error",
    type=click.Choice(["error", "todas", "ninguna"]),
    help="De qué SdA mostrar el proveedor efectivo.",
)
def diagnostico(situaciones: str) -> None:
    """Con qué proveedor se generaría cada SdA, y por qué.

    POR QUÉ HACE FALTA
    ------------------
    El proveedor sale de las preferencias del **propietario de la SdA**, no de
    quien pulsa regenerar ni de la configuración del proceso. Es deliberado
    —quien paga la generación es su dueño—, pero tiene una consecuencia que no
    se ve por ninguna parte: **cambiar tu perfil no cambia con qué se
    regeneran las SdA de otra persona**.

    Y hay una segunda vía silenciosa. `catalogo.validar` devuelve «usar el del
    sistema» cuando el proveedor elegido ya no está disponible en este
    despliegue, así que una preferencia guardada puede estar siendo ignorada
    sin que nada lo diga. Eso protege la cuenta de romperse, pero deja al
    usuario creyendo que usa un modelo que no usa.

    Este comando enseña las dos cosas: qué hay disponible **en este proceso**
    —ojo, `api` y `worker` son contenedores distintos y podrían no ver las
    mismas variables— y qué proveedor acabaría usando cada SdA.
    """
    from sqlalchemy import select

    from .ai import catalogo
    from .extensions import db
    from .models import SituacionAprendizaje

    disponibles = catalogo.disponibles()
    click.echo("Proveedores disponibles en ESTE proceso:")
    if not disponibles:
        click.echo("  ninguno — sin claves de API, todo cae al proveedor simulado")
    for p in disponibles:
        click.echo(f"  {p.nombre:8s} por defecto {p.modelo_por_defecto}")

    sistema, modelo_sistema = catalogo.por_defecto()
    click.echo(f"\nDel sistema: {sistema} · {modelo_sistema}")

    if situaciones == "ninguna":
        return

    consulta = select(SituacionAprendizaje)
    if situaciones == "error":
        consulta = consulta.where(
            SituacionAprendizaje.estado == SituacionAprendizaje.ERROR_GENERACION
        )
    filas = db.session.scalars(consulta.order_by(SituacionAprendizaje.id_situacion)).all()

    if not filas:
        click.echo("\nNinguna situación que mirar.")
        return

    click.echo(f"\n{len(filas)} situaciones · qué proveedor usaría cada una:\n")
    click.echo(f"  {'SdA':>5}  {'propietario':28s} {'elegido':22s} {'efectivo'}")
    resumen: dict[str, int] = {}
    descartadas = 0

    for sa in filas:
        dueno = sa.usuario
        crudo = f"{dueno.proveedor_ia or '—'}/{dueno.modelo_ia or '—'}"
        proveedor, modelo = catalogo.validar(dueno.proveedor_ia, dueno.modelo_ia)
        if proveedor is None:
            efectivo = f"{sistema}/{modelo_sistema} (del sistema)"
        else:
            efectivo = f"{proveedor}/{modelo}"
        # La marca es lo que hace útil la tabla: señala las filas donde lo
        # elegido y lo efectivo no coinciden, que son las que confunden.
        ignorada = proveedor is None and bool(dueno.proveedor_ia)
        descartadas += int(ignorada)
        marca = " ←" if ignorada else ""
        click.echo(
            f"  {sa.id_situacion:>5}  {dueno.correo[:28]:28s} {crudo[:22]:22s} {efectivo}{marca}"
        )
        resumen[efectivo.split(" ")[0]] = resumen.get(efectivo.split(" ")[0], 0) + 1

    click.echo("\nResumen: " + " · ".join(f"{k}: {n}" for k, n in resumen.items()))
    if descartadas:
        click.echo(
            f"\n{descartadas} filas marcadas con ← tienen una preferencia guardada "
            f"que este proceso IGNORA, porque ese proveedor no está disponible "
            f"aquí. Si el selector del perfil sí lo ofrece, es que `api` y "
            f"`worker` no ven las mismas variables de entorno."
        )


def register_cli(app: Flask) -> None:
    """Registra todos los grupos de comandos CLI en la aplicación."""
    app.cli.add_command(seed_cli)
    app.cli.add_command(usuarios_cli)
    app.cli.add_command(curriculo_cli)
    app.cli.add_command(ia_cli)

