"""Tests de los endpoints del catálogo curricular (``/api/curriculo/...``)."""
from __future__ import annotations

import pytest

from app.models import Competencia, CriterioEvaluacion, SaberBasico


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


def _registrar_y_login(client, correo="curr@test.com"):
    client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "ContraSegura1!",
            "nombre": "Docente",
            "centro_educativo": "IES Test",
        },
    )


@pytest.fixture()
def catalogo_minimo(db):
    """Siembra un pequeño catálogo para probar filtros sin depender del seed."""
    ce_mat = Competencia(
        codigo="CE1",
        tipo=Competencia.ESPECIFICA,
        materia="Matemáticas",
        cursos_aplicables=["1º ESO", "2º ESO", "3º ESO"],
        descriptores=["STEM1", "STEM2"],
        descripcion="Interpretar situaciones con matemáticas.",
    )
    ce_leng = Competencia(
        codigo="CE1",
        tipo=Competencia.ESPECIFICA,
        materia="Lengua",
        cursos_aplicables=["1º ESO", "2º ESO", "3º ESO", "4º ESO"],
        descriptores=["CCL1"],
        descripcion="Describir variedades lingüísticas.",
    )
    db.session.add_all([ce_mat, ce_leng])
    db.session.flush()

    db.session.add_all(
        [
            CriterioEvaluacion(
                codigo="1.1",
                id_competencia=ce_mat.id_competencia,
                materia="Matemáticas",
                cursos_aplicables=["1º ESO", "2º ESO", "3º ESO"],
                descripcion="Resuelve problemas numéricos.",
            ),
            CriterioEvaluacion(
                codigo="1.1",
                id_competencia=ce_leng.id_competencia,
                materia="Lengua",
                cursos_aplicables=["1º ESO"],
                descripcion="Reconoce variedades en 1º ESO.",
            ),
            CriterioEvaluacion(
                codigo="1.1",
                id_competencia=ce_leng.id_competencia,
                materia="Lengua",
                cursos_aplicables=["4º ESO"],
                descripcion="Reconoce variedades en 4º ESO.",
            ),
            SaberBasico(
                codigo="A.1",
                bloque="Sentido numérico",
                materia="Matemáticas",
                cursos_aplicables=["1º ESO", "2º ESO", "3º ESO"],
                descripcion="Estrategias de recuento.",
            ),
            SaberBasico(
                codigo="B.1",
                bloque="Sentido de la medida",
                materia="Matemáticas",
                cursos_aplicables=["1º ESO"],
                descripcion="Medida de magnitudes en 1º.",
            ),
        ]
    )
    db.session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sin_sesion_devuelve_401(client, catalogo_minimo):
    res = client.get("/api/curriculo/materias")
    assert res.status_code == 401


def test_listar_materias(client, catalogo_minimo):
    _registrar_y_login(client)
    res = client.get("/api/curriculo/materias")
    assert res.status_code == 200
    assert res.get_json() == ["Lengua", "Matemáticas"]


def test_competencias_filtradas_por_materia(client, catalogo_minimo):
    _registrar_y_login(client)
    res = client.get("/api/curriculo/competencias?materia=Matem%C3%A1ticas")
    body = res.get_json()
    assert res.status_code == 200
    assert len(body) == 1
    assert body[0]["codigo"] == "CE1"
    assert body[0]["materia"] == "Matemáticas"
    assert body[0]["descriptores"] == ["STEM1", "STEM2"]
    assert body[0]["cursos_aplicables"] == ["1º ESO", "2º ESO", "3º ESO"]


def test_competencias_filtradas_por_curso(client, catalogo_minimo):
    _registrar_y_login(client)
    res = client.get("/api/curriculo/competencias?curso=4%C2%BA%20ESO")
    body = res.get_json()
    assert res.status_code == 200
    # Solo la de Lengua aplica a 4º ESO.
    assert [c["materia"] for c in body] == ["Lengua"]


def test_criterios_filtrados_por_curso_devuelven_el_del_curso(client, catalogo_minimo):
    """Aunque dos criterios compartan codigo '1.1', sólo devuelve el del curso."""
    _registrar_y_login(client)
    res = client.get("/api/curriculo/criterios?materia=Lengua&curso=1%C2%BA%20ESO")
    body = res.get_json()
    assert res.status_code == 200
    assert len(body) == 1
    assert body[0]["descripcion"] == "Reconoce variedades en 1º ESO."


def test_criterios_filtrados_por_competencia(client, catalogo_minimo, db):
    _registrar_y_login(client)
    ce_mat = db.session.query(Competencia).filter_by(materia="Matemáticas").one()
    res = client.get(
        f"/api/curriculo/criterios?competencia_id={ce_mat.id_competencia}"
    )
    body = res.get_json()
    assert res.status_code == 200
    assert len(body) == 1
    assert body[0]["id_competencia"] == ce_mat.id_competencia


def test_saberes_filtrados_por_materia_y_curso(client, catalogo_minimo):
    _registrar_y_login(client)
    res = client.get(
        "/api/curriculo/saberes?materia=Matem%C3%A1ticas&curso=1%C2%BA%20ESO"
    )
    body = res.get_json()
    assert res.status_code == 200
    # A.1 aplica a 1-3º y B.1 solo a 1º → ambos aparecen filtrados por 1º ESO.
    codigos = sorted(s["codigo"] for s in body)
    assert codigos == ["A.1", "B.1"]


def test_saberes_filtrados_por_bloque(client, catalogo_minimo):
    _registrar_y_login(client)
    res = client.get(
        "/api/curriculo/saberes?materia=Matem%C3%A1ticas&bloque=Sentido%20num%C3%A9rico"
    )
    body = res.get_json()
    assert res.status_code == 200
    assert len(body) == 1
    assert body[0]["codigo"] == "A.1"
