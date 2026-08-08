"""Carga el currículo LOMLOE (competencias, criterios y saberes) en la BD.

Lee los ficheros JSON generados por ``app.curriculo.extractor`` (uno por
cada par materia/ciclo) y los inserta o actualiza de forma idempotente.

Esquema de unicidad utilizado para los UPSERT:

* **Competencia**: ``(codigo, materia)`` — las competencias específicas son
  comunes a todos los cursos de la etapa, así que se fusiona el campo
  ``cursos_aplicables`` haciendo unión con lo ya almacenado.
* **CriterioEvaluacion**: ``(codigo, materia, cursos_aplicables)`` — los
  criterios pueden repetir código entre cursos con descripciones distintas
  (caso de Lengua/Inglés en la Orden EFP/754).
* **SaberBasico**: ``(codigo, materia, cursos_aplicables, descripcion)`` —
  cada item de saber básico es una fila independiente.

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


def _union_cursos(actual: list[str], nuevos: list[str]) -> list[str]:
    """Fusiona dos listas de cursos preservando el orden 1.º → 4.º ESO."""
    orden = {f"{i}º ESO": i for i in range(1, 5)}
    unidos = set(actual) | set(nuevos)
    return sorted(unidos, key=lambda c: orden.get(c, 99))


def _upsert_competencia(
    *,
    codigo: str,
    materia: str,
    cursos: list[str],
    descriptores: list[str],
    descripcion: str,
) -> tuple[Competencia, bool]:
    """Inserta o actualiza una Competencia por (codigo, materia)."""
    existente = db.session.scalar(
        select(Competencia).where(
            Competencia.codigo == codigo, Competencia.materia == materia
        )
    )
    if existente is None:
        ce = Competencia(
            codigo=codigo,
            tipo=Competencia.ESPECIFICA,
            materia=materia,
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
) -> bool:
    """Upsert por (codigo, materia, cursos_aplicables). Devuelve True si se creó."""
    # Buscar criterios con el mismo (codigo, materia) y comparar cursos en Python.
    candidatos = db.session.scalars(
        select(CriterioEvaluacion).where(
            CriterioEvaluacion.codigo == codigo,
            CriterioEvaluacion.materia == materia,
        )
    ).all()
    cursos_norm = sorted(cursos)
    for c in candidatos:
        if sorted(c.cursos_aplicables or []) == cursos_norm:
            c.descripcion = descripcion
            c.id_competencia = id_competencia
            return False
    db.session.add(
        CriterioEvaluacion(
            codigo=codigo,
            id_competencia=id_competencia,
            materia=materia,
            cursos_aplicables=list(cursos),
            descripcion=descripcion,
        )
    )
    return True


def _upsert_saber_item(
    *,
    codigo: str,
    bloque: str,
    materia: str,
    cursos: list[str],
    descripcion: str,
) -> bool:
    """Upsert de un ítem por (codigo, materia, cursos_aplicables, descripcion)."""
    candidatos = db.session.scalars(
        select(SaberBasico).where(
            SaberBasico.codigo == codigo,
            SaberBasico.materia == materia,
            SaberBasico.descripcion == descripcion,
        )
    ).all()
    cursos_norm = sorted(cursos)
    for s in candidatos:
        if sorted(s.cursos_aplicables or []) == cursos_norm:
            s.bloque = bloque
            return False
    db.session.add(
        SaberBasico(
            codigo=codigo,
            bloque=bloque,
            materia=materia,
            cursos_aplicables=list(cursos),
            descripcion=descripcion,
        )
    )
    return True


# ---------------------------------------------------------------------------
# Procesamiento de un fichero JSON del extractor
# ---------------------------------------------------------------------------


def _procesar_fichero(ruta: Path) -> dict[str, int]:
    """Carga el JSON ``ruta`` y vuelca su contenido en BD. Devuelve contadores."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    materia = datos["materia"]
    cursos = list(datos["cursos_aplicables"])

    stats = {"ce_nuevas": 0, "ce_actualizadas": 0, "cr_nuevos": 0, "sb_nuevos": 0}

    # 1) Competencias específicas
    competencias_por_codigo: dict[str, Competencia] = {}
    for ce in datos["competencias_especificas"]:
        obj, creado = _upsert_competencia(
            codigo=ce["codigo"],
            materia=materia,
            cursos=cursos,
            descriptores=ce.get("descriptores") or [],
            descripcion=ce["descripcion"],
        )
        competencias_por_codigo[ce["codigo"]] = obj
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
        if _upsert_criterio(
            codigo=cr["codigo"],
            id_competencia=comp.id_competencia,
            materia=materia,
            cursos=cursos,
            descripcion=cr["descripcion"],
        ):
            stats["cr_nuevos"] += 1

    # 3) Saberes básicos: cada item del bloque es una fila independiente.
    for bloque in datos["saberes_basicos"]:
        cod_bloque = bloque["codigo"]
        titulo = bloque["titulo"]
        for idx, item in enumerate(bloque["items"], start=1):
            if _upsert_saber_item(
                codigo=f"{cod_bloque}.{idx}",
                bloque=titulo,
                materia=materia,
                cursos=cursos,
                descripcion=item,
            ):
                stats["sb_nuevos"] += 1

    return stats


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def seed_curriculo(directorio: Path | None = None) -> dict[str, int]:
    """Carga todos los ficheros JSON del directorio indicado.

    Es idempotente: ejecutarla de nuevo solo actualizará textos cambiados
    sin generar duplicados.
    """
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
    for ruta in ficheros:
        logger.info("Procesando %s", ruta.name)
        stats = _procesar_fichero(ruta)
        for k, v in stats.items():
            total[k] += v

    db.session.commit()
    total["ficheros"] = len(ficheros)
    return total
