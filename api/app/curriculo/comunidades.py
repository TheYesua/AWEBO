"""Catálogo de comunidades autónomas, con código canónico.

POR QUÉ HACE FALTA UN CATÁLOGO
-------------------------------
Hasta ahora `comunidad_autonoma` era **texto libre**: un `<input type="text">`
con «Ceuta» escrito por defecto. Daba igual, porque nadie filtraba por él — era
un dato descriptivo que viajaba hasta el prompt y poco más.

Deja de dar igual en cuanto ese campo decide **qué currículo se usa**. Con texto
libre, «Ceuta», «ceuta» y «CEUTA» son tres comunidades distintas, y un docente
que escriba «Andalucia» sin tilde se queda sin currículo sin entender por qué.
Un identificador que decide qué normativa se aplica no puede depender de cómo
teclee cada persona.

CÓDIGO, NO NOMBRE
-----------------
Las tablas de currículo guardan el **código** (`"ceuta"`, `"andalucia"`), no el
nombre. El nombre es texto de interfaz: puede cambiar de forma —con o sin
artículo, con la denominación oficial completa— y traducirse a las cuatro
lenguas. El código no cambia nunca, que es justo lo que se necesita de una
clave.

Es el mismo reparto que ya usa `i18n.IDIOMAS`: código estable dentro, etiqueta
fuera.

QUÉ SE OFRECE Y QUÉ NO
-----------------------
Están las diecisiete comunidades más Ceuta y Melilla, porque un docente de
Aragón existe aunque AWEBO no tenga todavía su decreto. Lo que dice si hay
currículo cargado es la base de datos, no esta lista: preguntarlo aquí sería
duplicar la verdad en dos sitios, y el día que se cargue una comunidad nueva
habría que acordarse de tocar los dos.
"""
from __future__ import annotations

import unicodedata


#: código canónico -> nombre en castellano.
#:
#: El orden es el de presentación: primero las que tienen currículo previsto en
#: la tarea 9c —para que quien las busque las encuentre arriba— y luego el
#: resto por orden alfabético.
COMUNIDADES: dict[str, str] = {
    "ceuta": "Ceuta",
    "andalucia": "Andalucía",
    "cataluna": "Cataluña",
    "galicia": "Galicia",
    "pais-vasco": "País Vasco",
    "aragon": "Aragón",
    "asturias": "Asturias",
    "baleares": "Illes Balears",
    "canarias": "Canarias",
    "cantabria": "Cantabria",
    "castilla-la-mancha": "Castilla-La Mancha",
    "castilla-y-leon": "Castilla y León",
    "extremadura": "Extremadura",
    "la-rioja": "La Rioja",
    "madrid": "Madrid",
    "melilla": "Melilla",
    "murcia": "Murcia",
    "navarra": "Navarra",
    "valencia": "Comunitat Valenciana",
}

#: La comunidad de lo que ya está cargado. Todo el currículo existente sale de
#: la Orden EFP/754, que es la del ámbito de gestión del Ministerio: Ceuta y
#: Melilla. La migración marca las filas existentes con este valor.
POR_DEFECTO = "ceuta"


def _sin_tildes(texto: str) -> str:
    """«Andalucía» → «andalucia». Descompone y tira los diacríticos."""
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


#: Formas alternativas que se aceptan al normalizar.
#:
#: No es una lista de sinónimos por gusto: son las que **ya están escritas en la
#: base de datos** o las que una persona teclea sin pensar. `comunidad_autonoma`
#: lleva siendo texto libre desde el TFG, así que lo guardado no sigue ninguna
#: convención.
_ALIAS: dict[str, str] = {
    "catalunya": "cataluna",
    "cataluna": "cataluna",
    "euskadi": "pais-vasco",
    "paisvasco": "pais-vasco",
    "pais vasco": "pais-vasco",
    "islas baleares": "baleares",
    "illes balears": "baleares",
    "comunidad valenciana": "valencia",
    "comunitat valenciana": "valencia",
    "comunidad de madrid": "madrid",
    "principado de asturias": "asturias",
    "region de murcia": "murcia",
    "castilla la mancha": "castilla-la-mancha",
    "castilla leon": "castilla-y-leon",
}


def normalizar(valor: str | None) -> str | None:
    """Texto libre → código canónico, o ``None`` si no se reconoce.

    Devolver ``None`` y no `POR_DEFECTO` es deliberado. Caer a Ceuta ante una
    comunidad irreconocible generaría contenido anclado a una normativa que no
    es la de quien lo pide, **sin decirlo**. Es justo el tipo de error que no se
    ve: la SdA sale completa, con criterios de verdad, y solo se descubre al
    comparar con el decreto propio.

    Con ``None``, el contexto se queda sin currículo y la generación se rechaza
    antes de gastarse, con el mensaje que ya existe para las materias sin
    currículo. Es más incómodo y es honesto.
    """
    if not valor:
        return None

    limpio = _sin_tildes(valor.strip().lower())
    if limpio in COMUNIDADES:
        return limpio

    # Con guiones y con espacios, para aceptar «pais-vasco» y «pais vasco».
    if limpio in _ALIAS:
        return _ALIAS[limpio]
    con_guiones = limpio.replace(" ", "-")
    if con_guiones in COMUNIDADES:
        return con_guiones
    if con_guiones in _ALIAS:
        return _ALIAS[con_guiones]

    # Por el nombre tal y como se presenta: es lo que llega de un formulario
    # que ofrecía las etiquetas y no los códigos.
    for codigo, nombre in COMUNIDADES.items():
        if _sin_tildes(nombre.lower()) == limpio:
            return codigo
    return None


def nombre(codigo: str | None) -> str | None:
    """Código canónico → nombre presentable, o ``None`` si no existe."""
    return COMUNIDADES.get(codigo) if codigo else None


__all__ = ["COMUNIDADES", "POR_DEFECTO", "normalizar", "nombre"]
