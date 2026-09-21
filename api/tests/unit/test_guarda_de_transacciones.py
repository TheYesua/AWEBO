"""La guarda que impide que un test deje una transacción abierta.

QUÉ PROTEGE
-----------
El 20/09/2026 la batería se colgó al 74 %, sin mensaje, dos veces seguidas.
La causa estaba ocho ficheros antes del test que se paraba: uno nuevo llamaba
a un servicio que consulta la base de datos **sin pedir el fixture `db`**, cosa
que puede hacer porque el fixture `app` es de ámbito sesión y mantiene abierto
un contexto de aplicación durante toda la batería. La transacción se quedó
viva con su `ACCESS SHARE`, y el `TRUNCATE ... CASCADE` del siguiente `db` se
puso a esperar ese bloqueo indefinidamente.

POR QUÉ ESTE FICHERO EXISTE
---------------------------
Porque la guarda es un fixture `autouse`, y un fixture `autouse` solo se
observa por sus efectos: si no detectara nada, la batería se pondría verde
igual y nadie se enteraría hasta el siguiente cuelgue. Una guarda que no se ha
visto en rojo no se sabe qué mide.

De ahí que la detección viva en `cerrar_transaccion_colgada()`, una función
normal, y que aquí se la llame a mano con una transacción abierta de verdad.
"""
from __future__ import annotations

from sqlalchemy import text

from app.extensions import db as _db
from tests.conftest import cerrar_transaccion_colgada


class TestLaDeteccion:
    def test_ve_la_transaccion_que_deja_una_consulta(self, app):
        """El caso exacto del 20/09: una consulta suelta, sin `db` de por
        medio, deja la sesión dentro de una transacción."""
        _db.session.remove()
        _db.session.execute(text("SELECT 1"))

        assert cerrar_transaccion_colgada() is True

    def test_despues_de_cerrarla_ya_no_hay_nada(self, app):
        """Y la cierra de verdad, que es lo que impide el cuelgue. Si solo
        avisara, el `TRUNCATE` siguiente seguiría esperando."""
        _db.session.remove()
        _db.session.execute(text("SELECT 1"))
        cerrar_transaccion_colgada()

        assert cerrar_transaccion_colgada() is False

    def test_sin_sesion_no_dice_que_la_hay(self, app):
        """El control negativo. Sin él, una función que devolviera `True`
        siempre pasaría los dos tests de arriba."""
        _db.session.remove()

        assert cerrar_transaccion_colgada() is False

    def test_no_crea_la_sesion_al_mirar(self, app):
        """Consultar `_db.session` la crea. Si la guarda lo hiciera, dejaría
        detrás exactamente lo que vino a vigilar."""
        _db.session.remove()
        cerrar_transaccion_colgada()

        assert not _db.session.registry.has()


class TestQueDeVerasEstaPuesta:
    def test_la_guarda_se_aplica_a_todos_los_tests(self, request):
        """Que la función sea correcta no sirve de nada si el fixture no está
        cableado — y un `autouse` que se cae de `conftest.py` no rompe nada
        visible. `request.fixturenames` trae los que de verdad se aplican a
        este test, autouse incluidos."""
        assert "_ninguna_transaccion_se_queda_abierta" in request.fixturenames

    def test_este_mismo_fichero_termina_limpio(self, app):
        """Y la comprobación más barata de todas: si la guarda funciona, los
        tests de arriba —que abren transacciones a propósito— no han dejado
        rastro para este."""
        assert not _db.session.registry.has()
