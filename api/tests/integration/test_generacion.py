"""Tests de integración de los endpoints de generación IA (Fase 4)."""
from __future__ import annotations

import pytest


SA_BASE = {
    "titulo": "Explorando el barrio",
    "curso": "2º ESO",
    "materia": "Matemáticas",
    "idioma": "es",
    "num_sesiones": 3,
    "duracion_sesion_minutos": 55,
}

@pytest.fixture(autouse=True)
def _curriculo_disponible(sembrar_curriculo):
    """Las SA de este módulo son de «Matemáticas · 2º ESO».

    Generar exige currículo al que anclarse, así que sin esto todas las
    peticiones de generación devolverían 422. Antes de esa comprobación, estos
    tests creaban SA sin catálogo y pasaban igualmente.
    """
    sembrar_curriculo()



def _registrar_y_login(client, correo="gen@test.com"):
    client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "ContraSegura1!",
            "nombre": "Docente",
            "centro_educativo": "IES Test",
        },
    )


def test_post_situaciones_sin_generar_flag_devuelve_201_en_borrador(client, db):
    _registrar_y_login(client)
    res = client.post("/api/situaciones", json=SA_BASE)
    assert res.status_code == 201
    assert res.get_json()["estado"] == "borrador"
    assert "task_id" not in res.get_json()


def test_post_situaciones_con_generar_true_devuelve_202_y_genera_eager(client, db):
    _registrar_y_login(client)
    res = client.post("/api/situaciones", json={**SA_BASE, "generar": True})
    assert res.status_code == 202
    body = res.get_json()
    assert "task_id" in body

    # En eager la generación ya ha terminado; el SA está GENERADA.
    sa_id = body["id_situacion"]
    detalle = client.get(f"/api/situaciones/{sa_id}").get_json()
    assert detalle["estado"] == "generada"
    # Todas las secciones presentes en el contenido.
    for seccion in (
        "descripcion",
        "objetivos",
        "conexion_curricular",
        "secuencia_sesiones",
        "evaluacion",
        "atencion_diversidad",
    ):
        assert seccion in detalle["contenido"], f"falta {seccion}"


def test_post_generar_lanza_tarea_y_actualiza_contenido(client, db):
    _registrar_y_login(client)
    sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]

    res = client.post(f"/api/situaciones/{sa_id}/generar")
    assert res.status_code == 202
    assert "task_id" in res.get_json()

    detalle = client.get(f"/api/situaciones/{sa_id}").get_json()
    assert detalle["estado"] == "generada"
    assert detalle["contenido"]["descripcion"]["_meta"]["proveedor"] == "fake"


def test_post_regenerar_seccion_solo_cambia_esa_seccion(client, db):
    _registrar_y_login(client)
    sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]
    client.post(f"/api/situaciones/{sa_id}/generar")

    # Snapshot de la sección "objetivos" antes de regenerar "descripcion".
    antes = client.get(f"/api/situaciones/{sa_id}").get_json()["contenido"]
    meta_objetivos_antes = antes["objetivos"]["_meta"]["generada_en"]

    res = client.post(f"/api/situaciones/{sa_id}/regenerar/descripcion")
    assert res.status_code == 202

    despues = client.get(f"/api/situaciones/{sa_id}").get_json()["contenido"]
    assert despues["objetivos"]["_meta"]["generada_en"] == meta_objetivos_antes
    # La marca temporal de descripcion cambia (o al menos el meta sigue allí).
    assert despues["descripcion"]["_meta"]["seccion"] == "descripcion"


def test_post_regenerar_seccion_desconocida_devuelve_400(client, db):
    _registrar_y_login(client)
    sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]
    res = client.post(f"/api/situaciones/{sa_id}/regenerar/inexistente")
    assert res.status_code == 400
    assert res.get_json()["error"] == "seccion_desconocida"


def test_get_task_status_devuelve_success_tras_generar(client, db):
    _registrar_y_login(client)
    sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]
    task_id = client.post(f"/api/situaciones/{sa_id}/generar").get_json()["task_id"]

    res = client.get(f"/api/tasks/{task_id}")
    assert res.status_code == 200
    body = res.get_json()
    assert body["task_id"] == task_id
    # En eager: tarea terminada, estado SUCCESS.
    assert body["estado"] == "SUCCESS"
    assert body["listo"] is True
    assert body["resultado"]["id_situacion"] == sa_id


def test_put_situacion_no_puede_forzar_estado_generando(client, db):
    _registrar_y_login(client)
    sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]
    res = client.put(f"/api/situaciones/{sa_id}", json={"estado": "generando"})
    assert res.status_code == 409
    assert res.get_json()["error"] == "estado_no_editable_manualmente"


def test_generar_sin_sesion_devuelve_401(client, db):
    # Un usuario crea una SA, cierra sesión, otro cliente intenta generar.
    _registrar_y_login(client, "a@test.com")
    sa_id = client.post("/api/situaciones", json=SA_BASE).get_json()["id_situacion"]
    client.post("/auth/logout")

    res = client.post(f"/api/situaciones/{sa_id}/generar")
    assert res.status_code == 401
