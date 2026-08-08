"""Tests de la cobertura curricular: qué parejas materia/curso son utilizables.

Origen: una SA de «Matemáticas · 4º ESO» generó `objetivos: []` y una conexión
curricular vacía. La combinación no existe en el currículo — en 4.º de la ESO
la materia se desdobla en los itinerarios A y B—, pero los dos desplegables del
formulario eran independientes y permitían elegirla. El modelo recibía un
listado curricular vacío y, obedeciendo la instrucción de no inventar códigos,
devolvía listas vacías. La SA quedaba en estado «generada», aparentemente
correcta.
"""
from __future__ import annotations

import pytest

from app.models import Competencia, CriterioEvaluacion, SaberBasico


CURSOS_1_A_3 = ["1º ESO", "2º ESO", "3º ESO"]


@pytest.fixture()
def catalogo(db):
    """Reproduce el desdoble real de Matemáticas en 4.º de la ESO."""

    def _tripleta(materia: str, cursos: list[str], codigo: str) -> None:
        """Competencia + criterio + saber: los tres hacen falta."""
        ce = Competencia(
            codigo=codigo,
            tipo=Competencia.ESPECIFICA,
            materia=materia,
            cursos_aplicables=cursos,
            descriptores=["STEM1"],
            descripcion=f"Competencia de {materia}",
        )
        db.session.add(ce)
        db.session.flush()
        db.session.add(
            CriterioEvaluacion(
                codigo=f"{codigo}.1",
                id_competencia=ce.id_competencia,
                materia=materia,
                cursos_aplicables=cursos,
                descripcion="Criterio",
            )
        )
        db.session.add(
            SaberBasico(
                codigo="A.1",
                bloque="Bloque A",
                materia=materia,
                cursos_aplicables=cursos,
                descripcion="Saber",
            )
        )

    _tripleta("Matemáticas", CURSOS_1_A_3, "CE1")
    _tripleta("Matemáticas A", ["4º ESO"], "CE1")
    _tripleta("Matemáticas B", ["4º ESO"], "CE1")

    # Materia con competencias pero SIN criterios ni saberes: no debe
    # ofrecerse, porque la conexión curricular saldría coja igualmente.
    db.session.add(
        Competencia(
            codigo="CE9",
            tipo=Competencia.ESPECIFICA,
            materia="Materia Incompleta",
            cursos_aplicables=["1º ESO"],
            descriptores=[],
            descripcion="Solo competencias",
        )
    )
    db.session.commit()


def _registrar(client, correo="cobertura@test.com"):
    res = client.post(
        "/auth/register",
        json={"correo": correo, "contrasena": "ContraSegura1!", "nombre": "Docente"},
    )
    assert res.status_code in (200, 201)


@pytest.fixture()
def docente(client, catalogo):
    _registrar(client)


def _cobertura(client) -> dict[str, list[str]]:
    res = client.get("/api/curriculo/cobertura")
    assert res.status_code == 200
    return {c["materia"]: c["cursos"] for c in res.get_json()}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class TestEndpointCobertura:
    def test_requiere_sesion(self, client, db):
        assert client.get("/api/curriculo/cobertura").status_code == 401

    def test_matematicas_no_llega_a_cuarto(self, client, docente):
        """El caso exacto que destapó el fallo."""
        cobertura = _cobertura(client)
        assert "4º ESO" not in cobertura["Matemáticas"]
        assert cobertura["Matemáticas"] == CURSOS_1_A_3

    def test_en_cuarto_estan_los_itinerarios(self, client, docente):
        cobertura = _cobertura(client)
        assert cobertura["Matemáticas A"] == ["4º ESO"]
        assert cobertura["Matemáticas B"] == ["4º ESO"]

    def test_una_materia_incompleta_no_se_ofrece(self, client, docente):
        """Con competencias pero sin criterios ni saberes, no vale."""
        assert "Materia Incompleta" not in _cobertura(client)


# ---------------------------------------------------------------------------
# Guarda del servidor
# ---------------------------------------------------------------------------


SA_SIN_CURRICULO = {
    "titulo": "Situación sin currículo",
    "curso": "4º ESO",
    "materia": "Matemáticas",
}
SA_CON_CURRICULO = {**SA_SIN_CURRICULO, "materia": "Matemáticas A"}


class TestGuardaAlGenerar:
    def test_no_se_genera_sin_curriculo(self, client, docente):
        creada = client.post("/api/situaciones", json=SA_SIN_CURRICULO)
        assert creada.status_code == 201
        id_sa = creada.get_json()["id_situacion"]

        res = client.post(f"/api/situaciones/{id_sa}/generar")
        assert res.status_code == 422
        assert res.get_json()["error"] == "sin_curriculo"

    def test_el_mensaje_nombra_las_alternativas(self, client, docente):
        """Decir que falta algo no basta: hay que decir qué sí hay."""
        creada = client.post("/api/situaciones", json=SA_SIN_CURRICULO)
        id_sa = creada.get_json()["id_situacion"]

        mensaje = client.post(f"/api/situaciones/{id_sa}/generar").get_json()["mensaje"]
        assert "Matemáticas A" in mensaje
        assert "Matemáticas B" in mensaje

    def test_con_curriculo_si_se_genera(self, client, docente):
        creada = client.post("/api/situaciones", json=SA_CON_CURRICULO)
        id_sa = creada.get_json()["id_situacion"]

        res = client.post(f"/api/situaciones/{id_sa}/generar")
        assert res.status_code == 202

    def test_la_creacion_con_generar_avisa_pero_conserva_la_sa(self, client, docente):
        """No se pierde el trabajo: la SA queda en borrador para corregirla."""
        res = client.post("/api/situaciones", json={**SA_SIN_CURRICULO, "generar": True})
        assert res.status_code == 422

        listado = client.get("/api/situaciones").get_json()["situaciones"]
        assert any(s["titulo"] == SA_SIN_CURRICULO["titulo"] for s in listado), (
            "la situación debe conservarse aunque no se pueda generar"
        )

    def test_tampoco_se_regenera_una_seccion_sin_curriculo(self, client, docente):
        creada = client.post("/api/situaciones", json=SA_SIN_CURRICULO)
        id_sa = creada.get_json()["id_situacion"]

        res = client.post(f"/api/situaciones/{id_sa}/regenerar/objetivos")
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------


class TestContextoTieneCurriculo:
    """La comprobación en la que se apoya la guarda del servidor.

    Sin ``with app.app_context()``: la fixture ``db`` ya opera dentro de uno,
    y anidar otro haría que ``db.session`` fuese una sesión distinta — el
    usuario recién insertado no existiría aún para ella y la clave ajena
    fallaría.
    """

    def test_detecta_la_falta(self, db, catalogo):
        from app.models import Rol, SituacionAprendizaje, Usuario
        from app.prompts.contexto import construir_contexto

        rol = db.session.query(Rol).filter_by(nombre="docente").one()
        u = Usuario(id_rol=rol.id_rol, correo="ctx@test.com", nombre="Ctx")
        u.set_password("ContraSegura1!")
        db.session.add(u)
        db.session.commit()

        sin = SituacionAprendizaje(
            id_usuario=u.id_usuario, titulo="Sin", curso="4º ESO",
            materia="Matemáticas",
        )
        con = SituacionAprendizaje(
            id_usuario=u.id_usuario, titulo="Con", curso="4º ESO",
            materia="Matemáticas A",
        )
        db.session.add_all([sin, con])
        db.session.commit()

        assert not construir_contexto(sin).tiene_curriculo()
        assert construir_contexto(con).tiene_curriculo()
