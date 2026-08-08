"""Catálogo de proveedores y modelos que el usuario puede elegir.

Fuente única de verdad para responder a dos preguntas: qué proveedores están
realmente utilizables en este despliegue, y qué modelos se pueden pedir a cada
uno.

Por qué el catálogo sale de la CONFIGURACIÓN y no de una lista fija en el
código: los nombres de modelo cambian con el tiempo, y una lista incrustada
aquí quedaría obsoleta en silencio — el usuario elegiría un modelo que ya no
existe y el fallo aparecería en mitad de una generación. Así que cada
proveedor ofrece:

* el modelo configurado en ``OPENAI_MODEL`` / ``GEMINI_MODEL``, que es el que
  este despliegue ya usa y por tanto se sabe válido;
* más los que se añadan en ``OPENAI_MODELOS`` / ``GEMINI_MODELOS``, listas
  separadas por comas.

Ampliar la oferta es editar el ``.env``, sin tocar código ni desplegar.

Un proveedor solo aparece si tiene clave configurada: ofrecer una opción que
va a caer a ``FakeProvider`` en cuanto se use sería engañar al usuario.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from flask import current_app


#: Proveedor especial: determinista, sin red y sin coste. No es un modelo de
#: verdad, así que solo se ofrece cuando el despliegue lo tiene configurado
#: como proveedor por defecto (desarrollo y tests).
FAKE = "fake"

ETIQUETAS = {
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    FAKE: "Simulado (sin coste, respuestas de prueba)",
}


@dataclass(frozen=True)
class Modelo:
    """Un modelo ofrecible, con su identificador de API y su etiqueta.

    El ``id`` es lo que viaja a la API del proveedor; la ``etiqueta`` es lo
    único que ve el docente. Importa la distinción: ``gpt-5.6-luna`` no le dice
    nada a nadie, y lo que necesita para decidir es «el más económico».
    """

    id: str
    etiqueta: str

    def to_dict(self) -> dict:
        return {"id": self.id, "etiqueta": self.etiqueta}


@dataclass(frozen=True)
class ProveedorDisponible:
    """Un proveedor utilizable, con los modelos que ofrece."""

    nombre: str
    etiqueta: str
    modelo_por_defecto: str
    modelos: list[Modelo] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return [m.id for m in self.modelos]

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "etiqueta": self.etiqueta,
            "modelo_por_defecto": self.modelo_por_defecto,
            "modelos": [m.to_dict() for m in self.modelos],
        }


def _lista(valor: str | None) -> list[str]:
    """Parte una lista separada por comas, sin vacíos ni espacios sobrantes."""
    return [x.strip() for x in (valor or "").split(",") if x.strip()]


def _parsear_modelo(entrada: str) -> Modelo:
    """Acepta ``id`` o ``id|Etiqueta legible``.

    Sin etiqueta se muestra el identificador tal cual: sigue siendo utilizable,
    solo menos amable. Las etiquetas **no pueden contener comas**, que es el
    separador de la lista.
    """
    id_, _, etiqueta = entrada.partition("|")
    id_ = id_.strip()
    etiqueta = etiqueta.strip()
    return Modelo(id=id_, etiqueta=etiqueta or id_)


def _modelos(clave_modelo: str, clave_lista: str) -> list[Modelo]:
    """Modelo configurado primero, luego los extra, sin repetir por id.

    Un id repetido no se añade dos veces, pero **sí puede aportar etiqueta**:
    ``OPENAI_MODEL`` / ``GEMINI_MODEL`` son identificadores pelados, así que
    repetir ese mismo id en la lista con ``id|Etiqueta`` es la única forma de
    que el modelo por defecto se muestre tan legible como los demás. Conserva
    su posición —sigue siendo el primero—, solo mejora cómo se lee.
    """
    cfg = current_app.config
    salida: list[Modelo] = []
    posicion: dict[str, int] = {}
    for entrada in [cfg.get(clave_modelo) or "", *_lista(cfg.get(clave_lista))]:
        if not entrada.strip():
            continue
        m = _parsear_modelo(entrada)
        if not m.id:
            continue
        if m.id not in posicion:
            posicion[m.id] = len(salida)
            salida.append(m)
        elif m.etiqueta != m.id and salida[posicion[m.id]].etiqueta == m.id:
            # El primero venía sin etiqueta y este la trae: se adopta.
            salida[posicion[m.id]] = m
    return salida


def disponibles() -> list[ProveedorDisponible]:
    """Proveedores utilizables en este despliegue, en orden de presentación."""
    cfg = current_app.config
    salida: list[ProveedorDisponible] = []

    if cfg.get("OPENAI_API_KEY"):
        modelos = _modelos("OPENAI_MODEL", "OPENAI_MODELOS")
        if modelos:
            salida.append(
                ProveedorDisponible(
                    "openai", ETIQUETAS["openai"], modelos[0].id, modelos
                )
            )

    if cfg.get("GEMINI_API_KEY"):
        modelos = _modelos("GEMINI_MODEL", "GEMINI_MODELOS")
        if modelos:
            salida.append(
                ProveedorDisponible(
                    "gemini", ETIQUETAS["gemini"], modelos[0].id, modelos
                )
            )

    # El simulado solo se ofrece si el despliegue ya lo usa por defecto.
    # En producción no tiene sentido que un docente pueda elegir respuestas
    # falsas sin saberlo.
    if (cfg.get("AI_PROVIDER") or "").lower().strip() == FAKE:
        salida.append(
            ProveedorDisponible(
                FAKE, ETIQUETAS[FAKE], FAKE, [Modelo(FAKE, "Respuestas simuladas")]
            )
        )

    return salida


def por_defecto() -> tuple[str, str]:
    """Proveedor y modelo del sistema: lo que se usa si el usuario no elige.

    Replica la resolución de :func:`app.ai.factory.get_provider` para que el
    perfil pueda mostrar «Usar el del sistema (Gemini · …)» con el valor real.
    """
    cfg = current_app.config
    solicitado = (cfg.get("AI_PROVIDER") or "").lower().strip()

    if solicitado == FAKE:
        return FAKE, FAKE
    if solicitado == "gemini":
        return "gemini", cfg.get("GEMINI_MODEL") or ""
    if solicitado == "openai":
        return "openai", cfg.get("OPENAI_MODEL") or ""

    # Sin AI_PROVIDER explícito: openai si hay clave, si no el simulado.
    if cfg.get("OPENAI_API_KEY"):
        return "openai", cfg.get("OPENAI_MODEL") or ""
    return FAKE, FAKE


def validar(proveedor: str | None, modelo: str | None) -> tuple[str | None, str | None]:
    """Sanea una elección de usuario.

    Devuelve ``(None, None)`` —es decir, «usar el del sistema»— si la elección
    está vacía o ya no es válida. Que un proveedor desaparezca del ``.env`` no
    debe dejar inservible la cuenta de quien lo tuviera elegido: simplemente
    vuelve al valor por defecto.
    """
    if not proveedor:
        return None, None

    proveedor = proveedor.lower().strip()
    for p in disponibles():
        if p.nombre != proveedor:
            continue
        if not modelo:
            return p.nombre, p.modelo_por_defecto
        return (
            (p.nombre, modelo)
            if modelo in p.ids
            else (p.nombre, p.modelo_por_defecto)
        )

    return None, None
