"""Tests de integración para adaptaciones curriculares (CU-10, Fase 5)."""
from __future__ import annotations

import pytest


SA_BASE = {
    "titulo": "Las plantas y su entorno",
    "curso": "2º ESO",
    "materia": "Matemáticas",
    "idioma": "es",
    "num_sesiones": 4,
    "duracion_sesion_minutos": 50,
}

@pytest.fixture(autouse=True)
def _curriculo_disponible(sembrar_curriculo):
    """Las SA de este módulo son de «Matemáticas · 2º ESO».

    Generar exige currículo al que anclarse, así que sin esto todas las
    peticiones de generación devolverían 422. Antes de esa comprobación, estos
    tests creaban SA sin catálogo y pasaban igualmente.
    """
    sembrar_curriculo()


PERFIL_ALUMNADO = (
    "Alumno con TDAH y dificultades de atención sostenida. "
    "Necesita tareas fragmentadas y refuerzos visuales frecuentes."
)


def _login(client, correo="adapt@test.com"):
    client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "ContraSegura1!",
            "nombre": "Docente",
            "centro_educativo": "IES Test",
        },
    )


def _crear_sa_generada(client, db):
    """Crea una SA y la genera en modo eager."""
    res = client.post("/api/situaciones", json={**SA_BASE, "generar": True})
    assert res.status_code == 202
    return res.get_json()["id_situacion"]


# ---------------------------------------------------------------------------
# POST /api/situaciones/{id}/adaptaciones
# ---------------------------------------------------------------------------


def test_crear_adaptacion_acns_devuelve_202(client, db):
    _login(client)
    id_sa = _crear_sa_generada(client, db)

    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "no_significativa",
            "perfil_alumnado": PERFIL_ALUMNADO,
        },
    )
    assert res.status_code == 202
    body = res.get_json()
    assert "task_id" in body
    assert body["tipo_adaptacion"] == "no_significativa"
    assert body["id_situacion_origen"] == id_sa


def test_crear_adaptacion_acs_devuelve_202(client, db):
    _login(client, "adapt2@test.com")
    id_sa = _crear_sa_generada(client, db)

    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "significativa",
            "perfil_alumnado": PERFIL_ALUMNADO,
            "titulo": "Adaptación ACS personalizada",
        },
    )
    assert res.status_code == 202
    body = res.get_json()
    assert body["tipo_adaptacion"] == "significativa"
    assert body["titulo"] == "Adaptación ACS personalizada"


def test_adaptacion_se_genera_en_modo_eager(client, db):
    _login(client, "adapt3@test.com")
    id_sa = _crear_sa_generada(client, db)

    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "no_significativa",
            "perfil_alumnado": PERFIL_ALUMNADO,
        },
    )
    assert res.status_code == 202
    id_adapt = res.get_json()["id_situacion"]

    # En modo eager la tarea se ejecuta sincrónicamente
    detalle = client.get(f"/api/situaciones/{id_adapt}").get_json()
    assert detalle["estado"] == "generada"
    assert detalle["id_situacion_origen"] == id_sa
    assert detalle["tipo_adaptacion"] == "no_significativa"
    # La SA adaptada tiene las MISMAS 6 secciones LOMLOE que una SA normal,
    # pero generadas con el contexto de adaptación inyectado.
    for seccion in (
        "descripcion",
        "objetivos",
        "conexion_curricular",
        "secuencia_sesiones",
        "evaluacion",
        "atencion_diversidad",
    ):
        assert seccion in detalle["contenido"], f"Falta sección {seccion}"


def test_adaptacion_titulo_autogenerado_contiene_tipo(client, db):
    _login(client, "adapt4@test.com")
    id_sa = _crear_sa_generada(client, db)

    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "significativa",
            "perfil_alumnado": PERFIL_ALUMNADO,
        },
    )
    assert res.status_code == 202
    assert "[ACS]" in res.get_json()["titulo"]


def test_perfil_alumnado_demasiado_corto_devuelve_400(client, db):
    _login(client, "adapt5@test.com")
    id_sa = _crear_sa_generada(client, db)

    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "no_significativa",
            "perfil_alumnado": "corto",
        },
    )
    assert res.status_code == 400


def test_tipo_adaptacion_invalido_devuelve_400(client, db):
    _login(client, "adapt6@test.com")
    id_sa = _crear_sa_generada(client, db)

    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "invalido",
            "perfil_alumnado": PERFIL_ALUMNADO,
        },
    )
    assert res.status_code == 400


def test_crear_adaptacion_sin_sesion_devuelve_401(client, db):
    res = client.post(
        "/api/situaciones/999/adaptaciones",
        json={
            "tipo_adaptacion": "no_significativa",
            "perfil_alumnado": PERFIL_ALUMNADO,
        },
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/situaciones/{id}/adaptaciones
# ---------------------------------------------------------------------------


def test_listar_adaptaciones_devuelve_lista(client, db):
    _login(client, "adapt7@test.com")
    id_sa = _crear_sa_generada(client, db)

    # Crear dos adaptaciones
    for tipo in ("no_significativa", "significativa"):
        client.post(
            f"/api/situaciones/{id_sa}/adaptaciones",
            json={"tipo_adaptacion": tipo, "perfil_alumnado": PERFIL_ALUMNADO},
        )

    res = client.get(f"/api/situaciones/{id_sa}/adaptaciones")
    assert res.status_code == 200
    lista = res.get_json()
    assert len(lista) == 2
    for item in lista:
        assert item["es_adaptacion"] is True


def test_perfil_alumnado_se_guarda_en_perfil_aula_de_la_sa_hija(client, db):
    """Regresión: el texto del alumno no se pierde; queda en perfil_aula."""
    _login(client, "adapt8@test.com")
    id_sa = _crear_sa_generada(client, db)

    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "no_significativa",
            "perfil_alumnado": PERFIL_ALUMNADO,
        },
    )
    assert res.status_code == 202
    body = res.get_json()
    # El perfil_aula de la SA hija debe contener exactamente el texto aportado.
    assert body["perfil_aula"] == PERFIL_ALUMNADO
    # El metadato de trazabilidad también debe estar presente.
    assert body["perfil_alumnado"] == PERFIL_ALUMNADO


def test_contexto_de_sa_adaptada_marca_es_adaptacion(client, db, app):
    """El builder de contexto debe detectar adaptación y rellenar campos."""
    _login(client, "adapt9@test.com")
    id_sa = _crear_sa_generada(client, db)
    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "significativa",
            "perfil_alumnado": PERFIL_ALUMNADO,
        },
    )
    id_adapt = res.get_json()["id_situacion"]

    with app.app_context():
        from app.models import SituacionAprendizaje
        from app.extensions import db as _db
        from app.prompts import construir_contexto

        sa_adapt = _db.session.get(SituacionAprendizaje, id_adapt)
        ctx = construir_contexto(sa_adapt)
        assert ctx.es_adaptacion is True
        assert ctx.tipo_adaptacion == "significativa"
        assert ctx.perfil_alumnado == PERFIL_ALUMNADO
        assert ctx.titulo_origen is not None
        assert ctx.contenido_origen_resumen
        assert "descripcion" in ctx.contenido_origen_resumen


def test_bloque_adaptacion_aparece_en_el_prompt(client, db, app):
    """El prompt de cualquier sección incluye el bloque de adaptación."""
    _login(client, "ctxprompt@test.com")
    id_sa = _crear_sa_generada(client, db)
    perfil = "Alumno con dislexia, requiere apoyos visuales."
    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={"tipo_adaptacion": "significativa", "perfil_alumnado": perfil},
    )
    id_adapt = res.get_json()["id_situacion"]

    with app.app_context():
        from app.models import SituacionAprendizaje
        from app.extensions import db as _db
        from app.prompts import construir_contexto
        from app.prompts.secciones import descripcion_v1

        sa_adapt = _db.session.get(SituacionAprendizaje, id_adapt)
        ctx = construir_contexto(sa_adapt)
        peticion = descripcion_v1.build(ctx)
        assert "INSTRUCCIONES DE ADAPTACIÓN CURRICULAR" in peticion.user
        assert "ADAPTACIÓN CURRICULAR SIGNIFICATIVA" in peticion.user
        assert "dislexia" in peticion.user


def test_listar_adaptaciones_sin_sesion_devuelve_401(client, db):
    res = client.get("/api/situaciones/1/adaptaciones")
    assert res.status_code == 401
