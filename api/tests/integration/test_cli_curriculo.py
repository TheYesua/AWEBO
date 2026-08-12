"""El comando `flask curriculo enlazar`, ejecutado de verdad.

POR QUÉ EXISTE ESTE FICHERO
----------------------------
Porque el comando salió roto a la primera ejecución real, con un
`NameError: name 'select' is not defined`, y **nada lo detectó**.

La comprobación que se había hecho era `python -c "import app.cli"`, que
devolvió «importa» y pareció suficiente. No lo es: importar un módulo ejecuta
su cuerpo, no el de sus funciones. Un nombre que solo se usa dentro de una
función no falta hasta que alguien la llama, así que un import olvidado en un
comando de CLI sobrevive intacto a cualquier comprobación de importación.

Es la regla 9 de `docs/CLAUDE.md` en su versión más literal: no dar una
instrucción sin haber recorrido el camino entero. Se dio el comando por bueno
y se puso en unas instrucciones de despliegue sin haberlo ejecutado nunca.

LO QUE SE PRUEBA
----------------
Que el comando **corre**. El comportamiento de la sincronización ya lo cubre
`test_enlaces_curriculares.py`; aquí lo que importa es lo que aquellos tests no
pueden ver, porque llaman a la función directamente y se saltan la capa de
click: los imports del comando, sus opciones y lo que imprime.
"""
from __future__ import annotations

import pytest


MATERIA = "Matemáticas A"
CURSO = "4º ESO"


@pytest.fixture
def sda_con_codigos(db):
    from app.models import Competencia, Rol, SituacionAprendizaje, Usuario

    db.session.add(Competencia(
        codigo="CE1", tipo=Competencia.ESPECIFICA, materia=MATERIA,
        cursos_aplicables=[CURSO], descriptores=[], descripcion="Resolver",
    ))
    rol = db.session.query(Rol).filter_by(nombre="docente").first()
    u = Usuario(correo="cli@ies.es", nombre="CLI", id_rol=rol.id_rol)
    u.set_password("ContrasenaCli1")
    db.session.add(u)
    db.session.commit()

    s = SituacionAprendizaje(
        titulo="Del CLI", materia=MATERIA, curso=CURSO, id_usuario=u.id_usuario,
        contenido={"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}, {"codigo": "INVENTADO"}],
        }},
    )
    db.session.add(s)
    db.session.commit()
    return s


class TestElComandoCorre:
    """El test que habría ahorrado el fallo. Es el más tonto y el que faltaba."""

    def test_no_revienta(self, app, db, sda_con_codigos):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert resultado.exit_code == 0, resultado.output
        assert resultado.exception is None, resultado.exception

    def test_sin_situaciones_lo_dice_y_no_falla(self, app, db):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar"])

        assert resultado.exit_code == 0
        assert "No hay situaciones" in resultado.output


class TestSimularNoEscribe:
    """La opción existe para poder mirar antes de tocar. Si escribiera igual,
    sería peor que no tenerla: daría una confianza que no corresponde."""

    def test_con_simular_los_enlaces_no_se_guardan(self, app, db, sda_con_codigos):
        app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        db.session.expire_all()
        assert sda_con_codigos.competencias == []

    def test_sin_simular_si(self, app, db, sda_con_codigos):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar"])

        assert resultado.exit_code == 0, resultado.output
        db.session.expire_all()
        assert [c.codigo for c in sda_con_codigos.competencias] == ["CE1"]

    def test_se_avisa_de_que_fue_simulado(self, app, db, sda_con_codigos):
        """Sin esta marca en la salida, las dos ejecuciones se ven idénticas y
        es fácil creer que ya se ha aplicado cuando no."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "simulado" in resultado.output


class TestInformaDeLosInventados:
    def test_los_lista_con_su_situacion(self, app, db, sda_con_codigos):
        """Es la razón principal de correr esto con `--simular` antes: ver
        cuántos códigos se está inventando el modelo."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "INVENTADO" in resultado.output
        assert str(sda_con_codigos.id_situacion) in resultado.output

    def test_no_los_llama_error(self, app, db, sda_con_codigos):
        """Un código inventado no es un fallo del comando: es un hallazgo. Si
        terminara en error, la salida legítima parecería una ejecución rota."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert resultado.exit_code == 0


class TestNoConfundeLasDosCausas:
    """El comando dijo «17 situaciones citan códigos que el modelo se inventó»
    y ninguna lo hacía. Este es el test que faltaba."""

    @pytest.fixture
    def sda_sin_curriculo(self, db, sda_con_codigos):
        sda_con_codigos.materia = "Materia Que No Existe"
        db.session.commit()
        return sda_con_codigos

    def test_sin_curriculo_no_se_llama_inventado(self, app, db, sda_sin_curriculo):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "No son códigos inventados" in resultado.output
        assert "el modelo se inventó" not in resultado.output

    def test_se_agrupa_por_pareja_y_no_por_situacion(self, app, db, sda_sin_curriculo):
        """Con 17 SdA repartidas en tres parejas, listarlas una a una esconde
        justo lo que hay que ver: que el problema son tres materias, no
        diecisiete situaciones."""
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "Materia Que No Existe · 4º ESO" in resultado.output

    def test_inventarse_codigos_de_verdad_sí_se_llama_así(self, app, db, sda_con_codigos):
        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])

        assert "el modelo se inventó" in resultado.output
        assert "INVENTADO" in resultado.output

    def test_cuando_todo_casa_se_dice(self, app, db, sda_con_codigos):
        """Sin este mensaje, una ejecución limpia y una a medias se distinguen
        solo por la ausencia de texto, que es difícil de ver."""
        sda_con_codigos.contenido = {"conexion_curricular": {
            "competencias": [{"codigo": "CE1"}],
        }}
        db.session.commit()

        resultado = app.test_cli_runner().invoke(args=["curriculo", "enlazar", "--simular"])
        assert "Todos los códigos casan" in resultado.output
