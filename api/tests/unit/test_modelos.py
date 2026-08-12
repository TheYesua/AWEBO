"""Tests unitarios de los modelos."""
from __future__ import annotations

from sqlalchemy import select

from app.models import (
    ODS,
    Competencia,
    CriterioEvaluacion,
    Rol,
    SaberBasico,
    SituacionAprendizaje,
    Usuario,
    Version,
)


# ---------------------------------------------------------------------------
# Rol
# ---------------------------------------------------------------------------


def test_seeds_cargan_roles_basicos(db):
    nombres = {r.nombre for r in db.session.scalars(select(Rol)).all()}
    assert {"docente", "administrador"}.issubset(nombres)


def test_seeds_cargan_los_17_ods(db):
    total = db.session.query(ODS).count()
    assert total == 17


# ---------------------------------------------------------------------------
# Usuario
# ---------------------------------------------------------------------------


def _crear_docente(db, correo: str = "test@example.com") -> Usuario:
    rol = db.session.scalar(select(Rol).where(Rol.nombre == "docente"))
    user = Usuario(
        id_rol=rol.id_rol,
        correo=correo,
        nombre="Profesor de prueba",
        comunidad_autonoma="Ceuta",
    )
    user.set_password("Secreto123!")
    db.session.add(user)
    db.session.commit()
    return user


def test_usuario_se_persiste_con_hash_bcrypt(db):
    user = _crear_docente(db)
    assert user.id_usuario is not None
    assert user.contrasena_hash != "Secreto123!"
    assert user.contrasena_hash.startswith("$2")  # firma bcrypt


def test_usuario_check_password_distingue_correctas_incorrectas(db):
    user = _crear_docente(db)
    assert user.check_password("Secreto123!") is True
    assert user.check_password("otra") is False


def test_usuario_correo_es_unico(db):
    _crear_docente(db, correo="dup@example.com")
    rol = db.session.scalar(select(Rol).where(Rol.nombre == "docente"))
    repe = Usuario(id_rol=rol.id_rol, correo="dup@example.com", nombre="Otro")
    repe.set_password("xx")
    db.session.add(repe)
    import sqlalchemy.exc

    try:
        db.session.commit()
        assert False, "Debería haber fallado por correo duplicado"
    except sqlalchemy.exc.IntegrityError:
        db.session.rollback()


def test_es_administrador_helper(db):
    rol_admin = db.session.scalar(select(Rol).where(Rol.nombre == "administrador"))
    user = Usuario(
        id_rol=rol_admin.id_rol, correo="admin@x.com", nombre="Admin"
    )
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    assert user.es_administrador is True


# ---------------------------------------------------------------------------
# Situación de Aprendizaje
# ---------------------------------------------------------------------------


def test_situacion_se_crea_con_valores_por_defecto(db):
    user = _crear_docente(db, correo="sa@example.com")
    sa = SituacionAprendizaje(
        id_usuario=user.id_usuario,
        titulo="Construyendo un puente",
        curso="2º ESO",
        materia="Tecnología",
    )
    db.session.add(sa)
    db.session.commit()

    assert sa.id_situacion is not None
    assert sa.estado == SituacionAprendizaje.BORRADOR
    assert sa.idioma == "es"
    assert sa.contenido == {}
    assert sa.es_adaptacion is False
    assert sa.fecha_creacion is not None


def test_situacion_de_adaptacion_apunta_a_origen(db):
    user = _crear_docente(db, correo="ad@example.com")
    original = SituacionAprendizaje(
        id_usuario=user.id_usuario,
        titulo="Original",
        curso="1º ESO",
        materia="Lengua",
    )
    db.session.add(original)
    db.session.commit()

    adaptada = SituacionAprendizaje(
        id_usuario=user.id_usuario,
        titulo="Original (adaptada)",
        curso="1º ESO",
        materia="Lengua",
        id_situacion_origen=original.id_situacion,
        tipo_adaptacion=SituacionAprendizaje.ADAPTACION_NO_SIGNIFICATIVA,
        perfil_alumnado="Alumnado con dislexia",
    )
    db.session.add(adaptada)
    db.session.commit()

    assert adaptada.es_adaptacion is True
    assert adaptada.situacion_origen.id_situacion == original.id_situacion
    assert original.adaptaciones[0].id_situacion == adaptada.id_situacion


def test_situacion_se_relaciona_con_el_curriculo(db):
    """Las tres relaciones que ahora se pueblan de verdad.

    Se llamaba `..._con_ods_y_currículo` y probaba también `sa.ods`. Esa
    relación se quitó el 11/08/2026: ningún prompt pide ODS, así que el JSONB
    nunca los trae y era una consulta garantizada a vacío en cada carga. La
    tabla `situacion_ods` y el catálogo de la ONU siguen ahí para cuando haya
    una sección que los pida.
    """
    user = _crear_docente(db, correo="rel@example.com")

    competencia = Competencia(
        codigo="STEM1",
        tipo=Competencia.ESPECIFICA,
        materia="Tecnología",
        cursos_aplicables=["1º ESO"],
        descriptores=["STEM1", "STEM2"],
        descripcion="Resolver problemas tecnológicos.",
    )
    db.session.add(competencia)
    db.session.flush()

    criterio = CriterioEvaluacion(
        codigo="1.1",
        id_competencia=competencia.id_competencia,
        cursos_aplicables=["1º ESO"],
        materia="Tecnología",
        descripcion="Identifica problemas y propone soluciones.",
    )
    saber = SaberBasico(
        codigo="A.1",
        bloque="Resolución de problemas",
        materia="Tecnología",
        cursos_aplicables=["1º ESO"],
        descripcion="Fases del proyecto técnico.",
    )
    sa = SituacionAprendizaje(
        id_usuario=user.id_usuario,
        titulo="Robótica básica",
        curso="1º ESO",
        materia="Tecnología",
    )
    sa.competencias.append(competencia)
    sa.criterios.append(criterio)
    sa.saberes.append(saber)
    db.session.add(sa)
    db.session.commit()

    assert len(sa.competencias) == 1
    assert sa.competencias[0].codigo == "STEM1"
    assert sa.criterios[0].codigo == "1.1"
    assert sa.saberes[0].bloque == "Resolución de problemas"


def test_situacion_versiones_se_ordenan(db):
    user = _crear_docente(db, correo="v@example.com")
    sa = SituacionAprendizaje(
        id_usuario=user.id_usuario,
        titulo="Con versiones",
        curso="3º ESO",
        materia="Matemáticas",
    )
    db.session.add(sa)
    db.session.flush()

    v1 = Version(
        id_situacion=sa.id_situacion,
        numero_version=1,
        contenido={"hola": "mundo"},
        descripcion_cambio="Inicial",
    )
    v2 = Version(
        id_situacion=sa.id_situacion,
        numero_version=2,
        contenido={"hola": "mundo!"},
        descripcion_cambio="Pequeño cambio",
    )
    db.session.add_all([v2, v1])  # añadidas en orden inverso a propósito
    db.session.commit()

    db.session.refresh(sa)
    assert [v.numero_version for v in sa.versiones] == [1, 2]


class TestIdiomasDeUnaSituacion:
    """La lista de idiomas de redacción vive en un solo sitio.

    Estuvo repetida en cuatro: el modelo, el ``Literal`` del esquema, el
    diccionario del prompt de traducción y los ``<option>`` de dos plantillas.
    Con cuatro copias, añadir un idioma en una sola deja el formulario
    ofreciendo una opción que el validador rechaza con un 422 — y el mensaje
    de error no dice nada de listas desincronizadas.

    Ahora la definición es ``SituacionAprendizaje.IDIOMAS`` y el resto la
    referencia. La única copia que queda es el ``Literal``, que necesita
    valores literales para ser legible y para que el editor ayude; estos tests
    son lo que la mantiene honesta.
    """

    def test_el_esquema_acepta_exactamente_los_del_modelo(self):
        from typing import get_args

        from app.models import SituacionAprendizaje
        from app.schemas.situacion import IdiomaLiteral

        assert set(get_args(IdiomaLiteral)) == set(SituacionAprendizaje.IDIOMAS)

    def test_el_prompt_de_traduccion_usa_la_misma_lista(self):
        from app.models import SituacionAprendizaje
        from app.prompts.operaciones import IDIOMAS

        assert IDIOMAS is SituacionAprendizaje.IDIOMAS

    def test_los_desplegables_ofrecen_todos_y_solo_esos(self, app):
        """Las plantillas se comprueban leyendo su HTML.

        Es lo único que ata el formulario a la lista: un ``<option>`` de más
        se rechazaría al guardar, y uno de menos deja un idioma inalcanzable
        aunque el backend lo admita.
        """
        import re
        from pathlib import Path

        from app.models import SituacionAprendizaje

        raiz = Path(app.jinja_loader.searchpath[0]) / "situaciones"
        esperados = set(SituacionAprendizaje.IDIOMAS)

        for nombre in ("nueva.html", "detalle.html"):
            html = (raiz / nombre).read_text(encoding="utf-8")
            # El <select id="idioma"> y sus opciones, hasta el cierre.
            bloque = re.search(
                r'<select id="idioma".*?</select>', html, re.S
            )
            assert bloque, f"{nombre}: no se encuentra el selector de idioma"
            ofrecidos = set(re.findall(r'<option value="(\w+)"', bloque.group(0)))
            assert ofrecidos == esperados, (
                f"{nombre} ofrece {sorted(ofrecidos)} y el modelo admite "
                f"{sorted(esperados)}"
            )

    def test_se_puede_crear_una_situacion_en_una_lengua_cooficial(self, client, db):
        """El caso que motivó ampliar la lista: hasta ahora una docente podía
        tener la interfaz en catalán pero no redactar en catalán."""
        client.post(
            "/auth/register",
            json={
                "correo": "cat@test.com",
                "contrasena": "Segura1234",
                "nombre": "Docent",
            },
        )
        res = client.post(
            "/api/situaciones",
            json={
                "titulo": "L'Antàrtida",
                "curso": "3º ESO",
                "materia": "Matemáticas",
                "idioma": "ca",
            },
        )
        assert res.status_code == 201, res.get_json()
        assert res.get_json()["idioma"] == "ca"
