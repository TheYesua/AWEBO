"""Tareas periódicas de mantenimiento.

De momento solo el purgado de cuentas dadas de baja cuyo plazo de reclamación
ha vencido. Al eliminar la fila de ``usuario``, el ``ondelete="CASCADE"`` que
ya existía sobre ``situacion_aprendizaje`` se lleva su contenido por delante:
no hay que borrar nada a mano, y eso es precisamente lo que hace segura esta
tarea. Una implementación que fuera tabla por tabla se quedaría desactualizada
en cuanto alguien añadiera una relación nueva.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from celery import shared_task
from sqlalchemy import select

from ..extensions import db
from ..models import Usuario


log = structlog.get_logger(__name__)


@shared_task(name="awebo.purgar_cuentas_vencidas")
def purgar_cuentas_vencidas() -> dict:
    """Borra definitivamente las cuentas cuya lápida superó el plazo.

    Devuelve un resumen para que quede en el resultado de la tarea y se pueda
    consultar sin bucear en los logs.

    El corte se calcula aquí y se compara en SQL, en lugar de traer todas las
    cuentas con lápida y filtrarlas en Python con ``gracia_vencida``. Con pocas
    filas daría igual, pero esto se ejecuta a diario y sin límite de tamaño: la
    versión en Python cargaría en memoria todas las bajas pendientes cada vez,
    junto con sus situaciones, porque ``Usuario.situaciones`` es ``selectin``.
    """
    corte = datetime.now(timezone.utc) - timedelta(days=Usuario.DIAS_DE_GRACIA)

    vencidas = list(
        db.session.scalars(
            select(Usuario).where(
                Usuario.eliminado_en.is_not(None),
                Usuario.eliminado_en <= corte,
            )
        )
    )

    purgadas = []
    for usuario in vencidas:
        # Se registra ANTES de borrar: después, el objeto queda en un estado
        # en el que leer sus atributos puede disparar consultas a filas que ya
        # no existen.
        purgadas.append(
            {
                "id_usuario": usuario.id_usuario,
                "correo": usuario.correo,
                "situaciones": len(usuario.situaciones),
                "eliminado_en": usuario.eliminado_en.isoformat(),
                # Los ids de sus SdA, por el mismo motivo que el resto: hacen
                # falta después de borrar, y después ya no se pueden leer. El
                # audio vive en un volumen y ningún cascade llega hasta él.
                "ids_situaciones": [sa.id_situacion for sa in usuario.situaciones],
            }
        )
        db.session.delete(usuario)

    db.session.commit()

    if purgadas:
        from ..services import audio as almacen_audio

        for cuenta in purgadas:
            for id_situacion in cuenta["ids_situaciones"]:
                almacen_audio.borrar_los_de(id_situacion)

    if purgadas:
        log.info(
            "purgado_cuentas_vencidas",
            cuentas=len(purgadas),
            situaciones=sum(p["situaciones"] for p in purgadas),
            detalle=purgadas,
        )

    return {
        "corte": corte.isoformat(),
        "cuentas_purgadas": len(purgadas),
        "situaciones_borradas": sum(p["situaciones"] for p in purgadas),
    }
