"""Los secretos con los que el proceso se niega a arrancar.

POR QUÉ ESTO NO VIVE EN `config.py`, QUE ES SU SITIO NATURAL
-------------------------------------------------------------
Porque `tests/unit/test_configuracion.py` hace `reload(app.config)` para
comprobar que un `SMTP_PORT=` vacío no tumba el arranque, y **`reload()`
reejecuta el módulo sobre su propio diccionario**: las clases que define pasan
a ser objetos nuevos, mientras que quien ya tenía una referencia se queda con
la vieja.

Para una constante o una función eso da igual. Para una **clase de excepción**
es veneno silencioso: un `except` escrito antes del `reload` deja de casar con
lo que se lanza después, porque la función que lanza busca el nombre en el
diccionario del módulo —el que acaba de cambiar— mientras que el `except`
guarda la clase de antes.

Aquí no es teoría. El 21/09/2026 `ConfiguracionInsegura` nació dentro de
`config.py` y sus siete tests de `pytest.raises` pasaron en solitario y
fallaron en la batería completa, porque el fichero que recarga corre al 47 % y
el que los tenía al 89 %.

Así que la regla, y la vigila un test en `test_configuracion.py`: **`config.py`
no define excepciones.** Viven aquí, donde nadie recarga nada.
"""
from __future__ import annotations

#: Valores de ``SECRET_KEY`` que no pueden llegar a un servidor público porque
#: cualquiera los conoce: están escritos en ficheros que se publican.
#:
#: El primero estuvo hasta el 21/09/2026 como valor por defecto de
#: `Config.SECRET_KEY`, dentro de un repositorio AGPL. El segundo sigue en
#: `.env.example`, que es exactamente lo que copia quien despliega por primera
#: vez — y por eso importa tanto como el otro.
CLAVES_PUBLICADAS = frozenset({
    "dev-key-change-me",
    "cambia-esto-por-una-clave-aleatoria-larga",
})

#: Una clave corta se rompe por fuerza bruta, así que no basta con que sea
#: distinta de las de arriba. 32 caracteres es el mínimo razonable; lo que
#: genera `python -c "import secrets; print(secrets.token_hex(32))"` son 64.
LONGITUD_MINIMA_SECRET_KEY = 32

#: Credenciales de base de datos que este repositorio publica. Mismo motivo.
CREDENCIALES_BD_PUBLICADAS = ("awebo_user:awebo_password",)


class ConfiguracionInsegura(RuntimeError):
    """El proceso arrancaría con un secreto que cualquiera puede leer.

    Es un error y no un aviso **a propósito**. Un aviso en el log lo lee quien
    está mirando el log en ese momento, que en un despliegue es nadie; y el
    servidor se queda funcionando, firmando sesiones con una clave pública, sin
    que nada vuelva a mencionarlo nunca.
    """


def comprobar_configuracion(config) -> None:
    """Se niega a arrancar si un secreto es un valor publicado.

    POR QUÉ EXISTE ESTO
    -------------------
    Hasta el 21/09/2026, `SECRET_KEY` tenía el valor por defecto
    ``"dev-key-change-me"`` y `FLASK_ENV` valía ``"production"`` también por
    defecto. Es decir: **olvidar una variable de entorno bastaba** para que el
    servidor arrancara en silencio firmando con una clave que está publicada.

    Y no firma una cosa sino dos. La cookie de sesión —con la clave se falsifica
    la sesión de cualquiera— y, en ``services/tokens.py``, los enlaces de
    restablecer contraseña y de verificar correo, que se emiten con esa misma
    clave y un ``salt`` por propósito. Con la clave pública se puede emitir un
    enlace válido de cambio de contraseña para cualquier cuenta.

    No hacía falta ningún ataque: bastaba un despliegue descuidado.

    LO QUE NO COMPRUEBA
    -------------------
    Que la clave sea *buena*. Puede ser 32 caracteres iguales y pasa. Esto
    detecta lo que se puede detectar sin adivinar intenciones: el valor
    heredado, el marcador de posición del ejemplo, la clave vacía y la
    demasiado corta. Contra una clave elegida a mano y mala no hay guarda
    posible desde aquí, y pretender lo contrario sería peor.
    """
    # En los tests la comprobación sobra: `TestConfig` fija su propia clave y
    # lo que se está probando no es el despliegue. En desarrollo también, para
    # que levantar el stack en local no exija ceremonia.
    if config.get("TESTING") or config.get("FLASK_ENV") == "development":
        return

    clave = config.get("SECRET_KEY") or ""
    generar = 'python -c "import secrets; print(secrets.token_hex(32))"'

    if not clave:
        raise ConfiguracionInsegura(
            "SECRET_KEY no está definida y FLASK_ENV no es 'development'. "
            "Firma la cookie de sesión y los enlaces de restablecer "
            f"contraseña, así que no hay valor por defecto posible. Genera una con: {generar}"
        )
    if clave in CLAVES_PUBLICADAS:
        raise ConfiguracionInsegura(
            "SECRET_KEY tiene un valor que está publicado en el repositorio, "
            "así que cualquiera puede falsificar sesiones y enlaces de "
            f"restablecer contraseña. Genera una propia con: {generar}"
        )
    if len(clave) < LONGITUD_MINIMA_SECRET_KEY:
        raise ConfiguracionInsegura(
            f"SECRET_KEY tiene {len(clave)} caracteres y el mínimo son "
            f"{LONGITUD_MINIMA_SECRET_KEY}. Genera una con: {generar}"
        )

    uri = config.get("SQLALCHEMY_DATABASE_URI") or ""
    for credencial in CREDENCIALES_BD_PUBLICADAS:
        if credencial in uri:
            raise ConfiguracionInsegura(
                f"La cadena de conexión usa las credenciales de ejemplo "
                f"({credencial}), que están publicadas en el repositorio. "
                "Define DATABASE_URL con las de verdad."
            )
