"""Los correos salen en el idioma que tenga la página al pedirlos.

EL RAZONAMIENTO QUE LO TUVO PARADO
-----------------------------------
Los cuatro correos estuvieron en castellano fijo con esta justificación escrita
en el código: «el correo se envía desde una tarea de Celery, fuera de una
petición, así que ahí no hay idioma de interfaz que consultar».

Era falso, y de una forma instructiva: mezclaba **componer** con **entregar**.
El texto se compone en el servicio, dentro de la petición, donde el idioma se
conoce perfectamente; al worker le llegan cadenas ya hechas. Bastaba con
marcarlas. El trabajo que se creía pendiente —guardar el idioma en el usuario y
activarlo dentro de la tarea— no hacía ninguna falta.

QUÉ VIGILA ESTE FICHERO
------------------------
Que los cuatro correos cambien de verdad al cambiar el idioma. Y, sobre todo,
que **ninguno se quede atrás**: el riesgo real no es que falle el que se acaba
de tocar, sino que dentro de tres meses alguien añada un quinto correo copiando
uno de estos y se olvide de las comillas de `_()`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest


CLAVE = "ContrasenaAna1"
PERSONAL = "ana.personal@ejemplo.es"


@pytest.fixture
def ana(db):
    from app.models import Rol, Usuario

    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="ana@ies.es", nombre="Ana", id_rol=rol.id_rol)
    u.set_password(CLAVE)
    db.session.add(u)
    db.session.commit()
    return u


def _en(client, idioma):
    """Deja la página en ese idioma, como haría el selector de la cabecera."""
    client.set_cookie("idioma", idioma)


def _entrar(client):
    client.post("/auth/login", json={"correo": "ana@ies.es", "contrasena": CLAVE})


# ---------------------------------------------------------------------------
# Un caso por cada correo que manda la aplicación.
#
# Se comprueban los cuatro y no solo uno porque cada uno tiene su propia
# función de composición: que el del restablecimiento esté traducido no dice
# absolutamente nada del de la baja.
# ---------------------------------------------------------------------------


class TestCadaCorreoCambiaDeIdioma:
    def test_restablecimiento(self, client, ana):
        _en(client, "ca")
        with patch("app.tasks.encolar") as encolar:
            client.post("/auth/solicitar-restablecimiento", json={"correo": "ana@ies.es"})

        texto = encolar.call_args.kwargs["texto"]
        assert "Has demanat" in texto, texto[:200]
        assert "Has pedido restablecer" not in texto

    def test_baja(self, client, ana):
        _entrar(client)
        _en(client, "ca")
        with patch("app.tasks.encolar") as encolar:
            r = client.post("/auth/solicitar-baja", json={
                "contrasena": CLAVE, "conservar_contenido": True,
            })

        assert r.status_code == 202, r.get_json()
        texto = encolar.call_args.kwargs["texto"]
        assert "Has demanat donar de baixa" in texto, texto[:200]

    def test_respaldo(self, client, ana):
        _entrar(client)
        _en(client, "ca")
        with patch("app.tasks.encolar") as encolar:
            r = client.post("/me/correo-de-respaldo", json={"correo": PERSONAL})

        assert r.status_code == 202, r.get_json()
        texto = encolar.call_args.kwargs["texto"]
        assert "Has afegit" in texto, texto[:200]

    def test_reclamacion(self, client, db, ana):
        """Este es el que peor lo tiene, y conviene tenerlo presente.

        Sale en el idioma de quien **pide** la reclamación, que no es quien la
        recibe: el destinatario es el dueño del respaldo anterior. Es lo mejor
        posible sin guardar un idioma por cuenta, y en el caso que importa —un
        intruso pidiéndola— el aviso llega igual, porque el enlace y la
        estructura se reconocen aunque el texto no se entienda del todo.
        """
        ana.correo_respaldo = PERSONAL
        ana.correo_respaldo_verificado_en = datetime.now(timezone.utc)
        db.session.commit()
        ana.marcar_eliminado()
        db.session.commit()

        _en(client, "ca")
        with patch("app.tasks.encolar") as encolar:
            r = client.post("/auth/register", json={
                "correo": "ana@ies.es", "contrasena": "ContrasenaJuan9",
                "nombre": "Juan", "reclamar_contenido": True,
            })

        assert r.status_code == 202, r.get_json()
        texto = encolar.call_args.kwargs["texto"]
        assert "Algú s'ha registrat" in texto, texto[:200]


class TestElAsuntoTambien:
    def test_no_se_queda_en_castellano(self, client, ana):
        """El asunto es lo primero que se ve en la bandeja de entrada.

        Y es el más fácil de olvidar, porque no está dentro de la función que
        compone el cuerpo: va suelto en la llamada a `encolar`.
        """
        _en(client, "ca")
        with patch("app.tasks.encolar") as encolar:
            client.post("/auth/solicitar-restablecimiento", json={"correo": "ana@ies.es"})

        assert encolar.call_args.kwargs["asunto"] != "Restablecer tu contraseña de AWEBO"


class TestNingunoSeQuedaAtras:
    """El test que de verdad protege a futuro.

    Los de arriba comprueban una frase concreta de cada correo, así que un
    quinto correo añadido mañana —o un párrafo nuevo dentro de uno de estos—
    pasaría por delante sin que nadie se entere. Este recorre las funciones de
    composición y exige que **todo** el cuerpo cambie al cambiar de idioma.
    """

    @staticmethod
    def _componer(app, idioma):
        """Llama a las cuatro funciones con el idioma forzado.

        Se usa `force_locale` y no una cookie, y el motivo es una trampa que
        este proyecto ya tenía documentada en `app/i18n.idioma_actual`:
        **Flask-Babel cachea el idioma resuelto en `g._flask_babel`**, o sea en
        el contexto de *aplicación*, no en el de petición. El fixture `db`
        mantiene uno abierto para toda la sesión de tests, así que el primer
        idioma que se resolviera se quedaría fijo y las cuatro llamadas de
        abajo saldrían idénticas — dando este test por roto cuando el código
        está bien.

        La primera versión sí usaba la cookie y falló exactamente así. En
        producción no ocurre: cada petición empuja su propio contexto. Los
        tests de arriba, que van por HTTP, cubren el camino real de la cookie.
        """
        from flask_babel import force_locale

        from app.services import baja, reclamacion, respaldo, restablecimiento

        with app.test_request_context(), force_locale(idioma):
            return {
                "restablecimiento": restablecimiento._texto_del_correo("http://x/t", 1),
                "baja_lapida": baja._texto_del_correo("http://x/t", 30, True),
                "baja_total": baja._texto_del_correo("http://x/t", 30, False),
                "respaldo_nuevo": respaldo._texto_del_correo("http://x/t", 24, False),
                "respaldo_cambio": respaldo._texto_del_correo("http://x/t", 24, True),
            }

    @pytest.mark.parametrize("idioma", ["ca", "gl", "eu"])
    def test_ningun_parrafo_sale_igual_que_en_castellano(self, app, idioma):
        """Compara **párrafo a párrafo**, no el cuerpo entero.

        La primera versión comparaba las cadenas completas, y al sabotearla se
        vio que prometía más de lo que hacía: dejando una sola frase sin `_()`
        el cuerpo seguía siendo distinto —el resto sí se traducía—, así que el
        test pasaba tan contento. Es el mismo defecto que ya tuvo aquí un test
        de la baja: **una comprobación que solo falla con el sabotaje total no
        vigila los parciales, que son los que ocurren de verdad.**

        Un párrafo que sale igual en las dos lenguas es sospechoso siempre. Los
        que legítimamente coinciden —una URL suelta— se excluyen a mano y en
        una lista corta, para que la excepción se vea.
        """
        castellano = self._componer(app, "es")
        otro = self._componer(app, idioma)

        sospechosos = []
        for clave, (texto_es, _html) in castellano.items():
            parrafos_otro = otro[clave][0].split("\n\n")
            for i, parrafo in enumerate(texto_es.split("\n\n")):
                if parrafo.startswith("http") or len(parrafo) < 12:
                    continue          # una URL suelta sí debe salir idéntica
                if i < len(parrafos_otro) and parrafo == parrafos_otro[i]:
                    sospechosos.append(f"{clave}[{i}]: {parrafo[:60]}")

        assert sospechosos == [], (
            f"en {idioma} estos párrafos salen idénticos al castellano, así que "
            f"o no están marcados con _() o falta traducirlos: {sospechosos}"
        )

    def test_reclamacion_tambien(self, app, db):
        """Va aparte porque su texto no vive en un `_texto_del_correo`: se
        compone dentro de `avisar_al_respaldo`, que necesita un usuario."""
        from app.models import Rol, Usuario
        from app.services import reclamacion

        rol = db.session.query(Rol).filter_by(nombre="docente").first()
        u = Usuario(correo="otra@ies.es", nombre="Otra", id_rol=rol.id_rol)
        u.set_password(CLAVE)
        u.correo_respaldo = PERSONAL
        u.correo_respaldo_verificado_en = datetime.now(timezone.utc)
        db.session.add(u)
        db.session.commit()

        from flask_babel import force_locale

        textos = {}
        for idioma in ("es", "ca"):
            with app.test_request_context(), force_locale(idioma):
                with patch("app.tasks.encolar") as encolar:
                    reclamacion.avisar_al_respaldo(u)
                    textos[idioma] = encolar.call_args.kwargs["texto"]

        assert textos["es"] != textos["ca"]


class TestLoQueNoDebeCambiar:
    def test_el_enlace_sale_intacto_en_todos_los_idiomas(self, app):
        """Una traducción puede llevarse por delante un marcador y dejar el
        correo sin enlace utilizable. Es el fallo más caro posible aquí: el
        mensaje llega, se lee, y no se puede hacer nada con él."""
        from app.services import restablecimiento

        from flask_babel import force_locale

        for idioma in ("es", "ca", "gl", "eu"):
            with app.test_request_context(), force_locale(idioma):
                texto, html = restablecimiento._texto_del_correo("http://awebo/t?token=abc", 1)
            assert "http://awebo/t?token=abc" in texto, idioma
            assert 'href="http://awebo/t?token=abc"' in html, idioma

    def test_los_numeros_no_se_pierden_al_traducir(self, app):
        """El plazo es la otra pieza que no puede evaporarse: sin él, quien
        recibe el correo no sabe si tiene media hora o una semana."""
        from app.services import baja

        from flask_babel import force_locale

        for idioma in ("es", "ca", "gl", "eu"):
            with app.test_request_context(), force_locale(idioma):
                texto, _html = baja._texto_del_correo("http://x/t", 30, True)
            assert "30" in texto, f"{idioma}: {texto[:200]}"
