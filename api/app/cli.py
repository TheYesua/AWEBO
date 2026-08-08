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


def register_cli(app: Flask) -> None:
    """Registra todos los grupos de comandos CLI en la aplicación."""
    app.cli.add_command(seed_cli)
    app.cli.add_command(usuarios_cli)
