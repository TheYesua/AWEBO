"""Catálogo de provincias, con la comunidad a la que pertenece cada una.

POR QUÉ EXISTE, SI EL CURRÍCULO VA POR COMUNIDAD
--------------------------------------------------
Porque son dos preguntas distintas y solo una la decide el currículo.

La LOMLOE se desarrolla en un decreto **por comunidad autónoma**. Andalucía
tiene ocho provincias y un único decreto: Sevilla y Granada comparten las mismas
materias, los mismos cursos y los mismos criterios. Guardar el currículo por
provincia sería duplicarlo ocho veces, con ocho sitios donde puede
desincronizarse.

Pero la provincia sí aporta algo que la comunidad no: **contexto local**. Una
situación de aprendizaje sobre el entorno cercano no se parece en Cádiz y en
Lugo, y ese matiz puede llegar al prompt. Además da el desplegable agrupado, que
es más corto de recorrer que una lista plana de cincuenta.

Así que se pregunta la provincia, y de ella se deriva la comunidad. La
agrupación del desplegable no es decorativa: es la relación que existe.

CEUTA Y MELILLA
---------------
No son provincias, son **ciudades autónomas**. Aquí figuran como si lo fueran
porque en un desplegable de «dónde das clase» tienen que estar, y porque su
currículo —el del ámbito de gestión del Ministerio— se comporta igual que el de
una comunidad uniprovincial. Es una simplificación consciente, no un descuido.
"""
from __future__ import annotations

import unicodedata


#: código de provincia -> (nombre, código de comunidad)
#:
#: Los códigos son el nombre sin tildes y con guiones, igual que en
#: `comunidades`. No se usa el código INE porque un número no se lee en una URL
#: ni en un log, y aquí no hay ningún dato oficial que casar por él.
PROVINCIAS: dict[str, tuple[str, str]] = {
    # Andalucía
    "almeria": ("Almería", "andalucia"),
    "cadiz": ("Cádiz", "andalucia"),
    "cordoba": ("Córdoba", "andalucia"),
    "granada": ("Granada", "andalucia"),
    "huelva": ("Huelva", "andalucia"),
    "jaen": ("Jaén", "andalucia"),
    "malaga": ("Málaga", "andalucia"),
    "sevilla": ("Sevilla", "andalucia"),
    # Aragón
    "huesca": ("Huesca", "aragon"),
    "teruel": ("Teruel", "aragon"),
    "zaragoza": ("Zaragoza", "aragon"),
    # Asturias, Baleares, Cantabria (uniprovinciales)
    "asturias": ("Asturias", "asturias"),
    "baleares": ("Illes Balears", "baleares"),
    "cantabria": ("Cantabria", "cantabria"),
    # Canarias
    "las-palmas": ("Las Palmas", "canarias"),
    "tenerife": ("Santa Cruz de Tenerife", "canarias"),
    # Castilla-La Mancha
    "albacete": ("Albacete", "castilla-la-mancha"),
    "ciudad-real": ("Ciudad Real", "castilla-la-mancha"),
    "cuenca": ("Cuenca", "castilla-la-mancha"),
    "guadalajara": ("Guadalajara", "castilla-la-mancha"),
    "toledo": ("Toledo", "castilla-la-mancha"),
    # Castilla y León
    "avila": ("Ávila", "castilla-y-leon"),
    "burgos": ("Burgos", "castilla-y-leon"),
    "leon": ("León", "castilla-y-leon"),
    "palencia": ("Palencia", "castilla-y-leon"),
    "salamanca": ("Salamanca", "castilla-y-leon"),
    "segovia": ("Segovia", "castilla-y-leon"),
    "soria": ("Soria", "castilla-y-leon"),
    "valladolid": ("Valladolid", "castilla-y-leon"),
    "zamora": ("Zamora", "castilla-y-leon"),
    # Cataluña
    "barcelona": ("Barcelona", "cataluna"),
    "girona": ("Girona", "cataluna"),
    "lleida": ("Lleida", "cataluna"),
    "tarragona": ("Tarragona", "cataluna"),
    # Comunitat Valenciana
    "alicante": ("Alicante", "valencia"),
    "castellon": ("Castellón", "valencia"),
    "valencia": ("València", "valencia"),
    # Extremadura
    "badajoz": ("Badajoz", "extremadura"),
    "caceres": ("Cáceres", "extremadura"),
    # Galicia
    "a-coruna": ("A Coruña", "galicia"),
    "lugo": ("Lugo", "galicia"),
    "ourense": ("Ourense", "galicia"),
    "pontevedra": ("Pontevedra", "galicia"),
    # Madrid, La Rioja, Murcia, Navarra (uniprovinciales)
    "madrid": ("Madrid", "madrid"),
    "la-rioja": ("La Rioja", "la-rioja"),
    "murcia": ("Murcia", "murcia"),
    "navarra": ("Navarra", "navarra"),
    # País Vasco
    "araba": ("Araba/Álava", "pais-vasco"),
    "bizkaia": ("Bizkaia", "pais-vasco"),
    "gipuzkoa": ("Gipuzkoa", "pais-vasco"),
    # Ciudades autónomas: ver el docstring del módulo.
    "ceuta": ("Ceuta", "ceuta"),
    "melilla": ("Melilla", "melilla"),
}


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


#: Formas alternativas que se aceptan. Las oficiales bilingües sobre todo: en
#: un campo que ha sido texto libre, «Lérida» y «Lleida» están las dos escritas.
_ALIAS: dict[str, str] = {
    "alava": "araba", "araba/alava": "araba", "vitoria": "araba",
    "vizcaya": "bizkaia", "guipuzcoa": "gipuzkoa",
    "lerida": "lleida", "gerona": "girona",
    "la coruna": "a-coruna", "coruna": "a-coruna", "a coruna": "a-coruna",
    "orense": "ourense",
    "islas baleares": "baleares", "illes balears": "baleares",
    "palma": "baleares",
    "santa cruz de tenerife": "tenerife",
    "castellon de la plana": "castellon", "castello": "castellon",
    "valencia/valencia": "valencia",
    "principado de asturias": "asturias", "oviedo": "asturias",
    "region de murcia": "murcia",
    "comunidad de madrid": "madrid",
    "navarra/nafarroa": "navarra", "nafarroa": "navarra",
}


def normalizar(valor: str | None) -> str | None:
    """Texto libre → código de provincia, o ``None`` si no se reconoce.

    ``None`` y no un valor por defecto, por el mismo motivo que en
    `comunidades.normalizar`: de aquí sale la comunidad, y de la comunidad el
    currículo. Adivinar mal significa anclar un documento a una normativa que
    no es la de quien lo pide, sin decirlo.
    """
    if not valor:
        return None

    limpio = _sin_tildes(valor.strip().lower())
    if limpio in PROVINCIAS:
        return limpio
    if limpio in _ALIAS:
        return _ALIAS[limpio]

    con_guiones = limpio.replace(" ", "-").replace("/", "-")
    if con_guiones in PROVINCIAS:
        return con_guiones
    if con_guiones in _ALIAS:
        return _ALIAS[con_guiones]

    for codigo, (nombre, _com) in PROVINCIAS.items():
        if _sin_tildes(nombre.lower()) == limpio:
            return codigo
    return None


def comunidad_de(provincia: str | None) -> str | None:
    """Código de comunidad al que pertenece esa provincia.

    Es la función que convierte lo que el docente elige en lo que decide el
    currículo. Acepta texto libre y lo normaliza por el camino, porque lo
    guardado antes de que existiera este catálogo no sigue ninguna convención.
    """
    codigo = normalizar(provincia)
    return PROVINCIAS[codigo][1] if codigo else None


def nombre(codigo: str | None) -> str | None:
    """Código → nombre presentable."""
    entrada = PROVINCIAS.get(codigo) if codigo else None
    return entrada[0] if entrada else None


def agrupadas() -> list[tuple[str, list[tuple[str, str]]]]:
    """Para el desplegable: ``[(nombre de comunidad, [(codigo, nombre), …]), …]``.

    El orden es el de `comunidades.COMUNIDADES`, que ya pone delante las que
    tienen currículo previsto. Dentro de cada grupo, alfabético.

    Se sirve desde el servidor y no se construye en JavaScript porque la lista
    de comunidades con currículo cargado depende de la base de datos, y tener
    dos copias de la misma verdad es cómo se desincronizan.
    """
    from . import comunidades

    por_comunidad: dict[str, list[tuple[str, str]]] = {}
    for codigo, (nombre_prov, com) in PROVINCIAS.items():
        por_comunidad.setdefault(com, []).append((codigo, nombre_prov))

    salida: list[tuple[str, list[tuple[str, str]]]] = []
    for com, etiqueta in comunidades.COMUNIDADES.items():
        provincias = sorted(por_comunidad.get(com, []), key=lambda p: p[1])
        if provincias:
            salida.append((etiqueta, provincias))
    return salida


__all__ = ["PROVINCIAS", "normalizar", "comunidad_de", "nombre", "agrupadas"]
