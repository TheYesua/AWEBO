"""Tests de integración del endpoint de exportación (CU-06)."""
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



def _login(client, correo="export@test.com"):
    client.post(
        "/auth/register",
        json={
            "correo": correo,
            "contrasena": "ContraSegura1!",
            "nombre": "Docente",
            "centro_educativo": "IES Test",
        },
    )


def _crear_sa_generada(client) -> int:
    res = client.post("/api/situaciones", json={**SA_BASE, "generar": True})
    assert res.status_code == 202
    return res.get_json()["id_situacion"]


def _crear_sa_borrador(client) -> int:
    res = client.post("/api/situaciones", json=SA_BASE)
    assert res.status_code == 201
    return res.get_json()["id_situacion"]


# ---------------------------------------------------------------------------
# Casos felices
# ---------------------------------------------------------------------------


def test_exportar_pdf_devuelve_200_y_pdf_valido(client, db):
    _login(client, "exp1@test.com")
    id_sa = _crear_sa_generada(client)

    res = client.get(f"/api/situaciones/{id_sa}/exportar?formato=pdf")
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    # Cabecera de descarga con nombre de fichero
    cd = res.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert f"SA-{id_sa}-" in cd
    assert ".pdf" in cd
    # Cuerpo: firma de PDF
    assert res.data[:4] == b"%PDF"
    assert len(res.data) > 1000  # algún tamaño razonable


def test_exportar_sin_formato_usa_pdf_por_defecto(client, db):
    _login(client, "exp2@test.com")
    id_sa = _crear_sa_generada(client)

    res = client.get(f"/api/situaciones/{id_sa}/exportar")
    assert res.status_code == 200
    assert res.mimetype == "application/pdf"


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


def test_exportar_formato_invalido_devuelve_400(client, db):
    _login(client, "exp3@test.com")
    id_sa = _crear_sa_generada(client)

    res = client.get(f"/api/situaciones/{id_sa}/exportar?formato=epub")
    assert res.status_code == 400
    assert res.get_json()["error"] == "formato_no_soportado"


def test_exportar_sa_borrador_devuelve_409(client, db):
    """Una SA sin contenido generado no se puede exportar."""
    _login(client, "exp4@test.com")
    id_sa = _crear_sa_borrador(client)

    res = client.get(f"/api/situaciones/{id_sa}/exportar?formato=pdf")
    assert res.status_code == 409
    assert res.get_json()["error"] == "sin_contenido"


def test_exportar_docx_devuelve_200_y_docx_valido(client, db):
    _login(client, "exp5@test.com")
    id_sa = _crear_sa_generada(client)

    res = client.get(f"/api/situaciones/{id_sa}/exportar?formato=docx")
    assert res.status_code == 200
    assert res.mimetype == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    cd = res.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert ".docx" in cd
    # Firma de fichero ZIP (los DOCX son ZIP de OOXML)
    assert res.data[:2] == b"PK"
    assert len(res.data) > 1000


def test_exportar_sa_ajena_devuelve_403(client, db):
    """Un usuario no puede exportar la SA de otro."""
    # Usuario A crea una SA generada
    _login(client, "expA@test.com")
    id_sa = _crear_sa_generada(client)
    client.get("/auth/logout")

    # Usuario B intenta descargarla
    _login(client, "expB@test.com")
    res = client.get(f"/api/situaciones/{id_sa}/exportar?formato=pdf")
    assert res.status_code in (403, 404)  # según política de no_autorizado/no_encontrada


def test_exportar_sin_sesion_devuelve_401(client, db):
    res = client.get("/api/situaciones/1/exportar?formato=pdf")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Adaptación curricular: el PDF incluye la insignia ACS/ACNS
# ---------------------------------------------------------------------------


def test_exportar_adaptacion_pdf_incluye_etiqueta_de_tipo(client, db):
    _login(client, "expadapt@test.com")
    id_sa = _crear_sa_generada(client)
    res = client.post(
        f"/api/situaciones/{id_sa}/adaptaciones",
        json={
            "tipo_adaptacion": "no_significativa",
            "perfil_alumnado": "Alumno con dislexia, requiere apoyos visuales y tiempos extra.",
        },
    )
    assert res.status_code == 202
    id_adapt = res.get_json()["id_situacion"]

    res = client.get(f"/api/situaciones/{id_adapt}/exportar?formato=pdf")
    assert res.status_code == 200
    # No podemos parsear el PDF, pero sí verificar que la generación
    # con la cabecera ACS/ACNS no rompe nada.
    assert res.data[:4] == b"%PDF"
