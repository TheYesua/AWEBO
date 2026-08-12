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
def cmd_seed_curriculo(directorio: str | None) -> None:
    """Carga competencias, criterios y saberes desde los JSON del extractor."""
    from pathlib import Path

    from .seeds import seed_curriculo

    ruta = Path(directorio) if directorio else None
    result = seed_curriculo(ruta)
    click.echo(
        f"[seed:curriculo] ficheros={result['ficheros']} "
        f"ce_nuevas={result['ce_nuevas']} ce_actualizadas={result['ce_actualizadas']} "
        f"cr_nuevos={result['cr_nuevos']} sb_nuevos={result['sb_nuevos']}"
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


def register_cli(app: Flask) -> None:
    """Registra todos los grupos de comandos CLI en la aplicación."""
    app.cli.add_command(seed_cli)
    app.cli.add_command(usuarios_cli)
    app.cli.add_command(curriculo_cli)

