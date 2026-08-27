"""`flask seed curriculo --borrar-sobrantes`: quitar lo que ya no existe.

EL PROBLEMA
------------
El seed hace UPSERT: añade y actualiza, y **nunca borra**. Es lo correcto por
defecto —equivocarse de directorio no cuesta nada— pero deja un rastro cuando
un extractor mejora.

Pasó con Cataluña el 14/08: al arreglar el extractor cambiaron los códigos de
algunos saberes, y las filas viejas se quedaron. **52 filas** de currículo que
ya no están en el decreto, indistinguibles de las buenas, y ofreciéndose en los
desplegables como si lo estuvieran.

LO QUE ESTE FICHERO VIGILA, Y ES LO DELICADO
---------------------------------------------
Que borrar no rompa una SdA existente. Las tablas de enlace declaran
``ondelete="RESTRICT"``, así que la base de datos abortaría la carga entera con
un IntegrityError; pero la razón de fondo no es técnica: **borrar el saber que
una situación cita rompe esa situación**. El documento pasaría a decir «(no
encontrado en el currículo)» donde antes había texto, sin que el docente haya
tocado nada.

Así que las filas obsoletas que alguien esté usando se conservan y se informan.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.extensions import db as _db
from app.models import CriterioEvaluacion, Rol, SaberBasico, SituacionAprendizaje, Usuario
from app.seeds.seed_curriculo import seed_curriculo


def _json(comunidad: str, materia: str, *, saberes: list[tuple[str, str]],
          criterio: str = "1.1") -> dict:
    return {
        "materia_oficial": materia,
        "materia": materia,
        "etapa": "ESO",
        "ciclo": "1º ESO",
        "itinerario": None,
        "cursos_aplicables": ["1º ESO"],
        "comunidad": comunidad,
        "idioma": "es",
        "competencias_especificas": [
            {"codigo": "1", "descripcion": "Interpretar.", "descriptores": ["CD2"]},
        ],
        "criterios_evaluacion": [
            {"codigo": criterio, "competencia": "1", "descripcion": "Analizar."},
        ],
        "saberes_basicos": [
            {
                "codigo": "A",
                "bloque": "A. Bloque",
                "titulo": "Bloque",
                "items": [texto for _, texto in saberes],
                "codigos_items": [cod for cod, _ in saberes],
            },
        ],
    }


def _escribir(carpeta, datos, nombre="materia__1.json"):
    (carpeta / nombre).write_text(json.dumps(datos, ensure_ascii=False),
                                  encoding="utf-8")
    return carpeta


def _saberes(comunidad="cataluna") -> set[str]:
    """`select()` y no `Model.query`: es el estilo del proyecto entero y además
    `Model.query` está deprecado en Flask-SQLAlchemy 3."""
    return set(_db.session.scalars(
        select(SaberBasico.codigo).where(SaberBasico.comunidad == comunidad)
    ).all())


def _criterios(comunidad="cataluna") -> set[str]:
    return set(_db.session.scalars(
        select(CriterioEvaluacion.codigo).where(
            CriterioEvaluacion.comunidad == comunidad
        )
    ).all())


class TestSinLaOpcionNoSeBorraNada:
    """El comportamiento de siempre, que sigue siendo el de por defecto."""

    def test_las_filas_viejas_se_quedan(self, app, db, tmp_path):
        """Es el fallo de origen: recargar con códigos cambiados deja las dos
        versiones conviviendo, y nada distingue la buena de la caduca."""
        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.1", "Viejo saber")]))
        seed_curriculo(tmp_path)

        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.9", "Nuevo saber")]))
        seed_curriculo(tmp_path)

        assert _saberes() == {"A.1", "A.9"}


class TestConLaOpcionSeLimpia:
    def test_lo_que_ya_no_esta_se_borra(self, app, db, tmp_path):
        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.1", "Viejo saber")]))
        seed_curriculo(tmp_path)

        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.9", "Nuevo saber")]))
        seed_curriculo(tmp_path, borrar_sobrantes=True)

        assert _saberes() == {"A.9"}

    def test_no_toca_las_demas_comunidades(self, app, db, tmp_path):
        """EL RIESGO MAYOR de esta opción. Sin filtrar por las comunidades que
        la carga ha tocado, recargar Cataluña se llevaría por delante el
        currículo de Andalucía entero —2.400 filas— sin decir nada."""
        _escribir(tmp_path, _json("andalucia", "Mates", saberes=[("BYG.1.A.1", "De Andalucía")]),
                  "and__1.json")
        seed_curriculo(tmp_path)

        otra = tmp_path / "cat"
        otra.mkdir()
        _escribir(otra, _json("cataluna", "Mates", saberes=[("A.1", "De Cataluña")]))
        seed_curriculo(otra, borrar_sobrantes=True)

        assert _saberes("andalucia") == {"BYG.1.A.1"}
        assert _saberes("cataluna") == {"A.1"}

    def test_es_idempotente(self, app, db, tmp_path):
        """A la segunda no debe borrar nada: si borrara, sería que no reconoce
        como «vistas» las filas que acaba de escribir."""
        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.1", "Saber")]))
        seed_curriculo(tmp_path, borrar_sobrantes=True)
        seed_curriculo(tmp_path, borrar_sobrantes=True)

        assert _saberes() == {"A.1"}

    def test_tambien_limpia_criterios_y_competencias(self, app, db, tmp_path):
        """Las tres tablas, no solo los saberes. Olvidar una dejaría sobrantes
        de un tipo y no de otro, que es más difícil de ver que no limpiar."""
        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.1", "S")],
                                  criterio="1.1"))
        seed_curriculo(tmp_path)

        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.1", "S")],
                                  criterio="9.9"))
        seed_curriculo(tmp_path, borrar_sobrantes=True)

        assert _criterios() == {"9.9"}


class TestElOrdenDeBorradoImporta:
    """Las claves ajenas entre las tres tablas son RESTRICT, no CASCADE."""

    def test_una_competencia_con_sus_criterios_se_borra_entera(self, app, db, tmp_path):
        """EL FALLO QUE ESTE TEST FIJA: el primer borrador recorría las tablas
        en orden competencia → criterio → saber.

        `CriterioEvaluacion.id_competencia` tiene ``ondelete="RESTRICT"``, así
        que borrar la competencia antes que sus criterios lanza IntegrityError
        y **aborta la carga entera**, no solo el borrado. Se recorre al revés:
        saberes, criterios y por último competencias.

        Aquí cambia la materia, así que la competencia vieja y todos sus
        criterios sobran a la vez — el caso exacto que se estrellaba."""
        _escribir(tmp_path, _json("cataluna", "Vieja", saberes=[("A.1", "S")]))
        seed_curriculo(tmp_path)

        (tmp_path / "materia__1.json").unlink()
        _escribir(tmp_path, _json("cataluna", "Nueva", saberes=[("A.1", "S")]),
                  "nueva__1.json")
        seed_curriculo(tmp_path, borrar_sobrantes=True)

        materias = set(db.session.scalars(
            select(SaberBasico.materia).where(SaberBasico.comunidad == "cataluna")
        ).all())
        assert materias == {"Nueva"}
        assert _criterios() == {"1.1"}


class TestNoRompeLasSituacionesQueYaExisten:
    """La parte que importa de verdad."""

    @pytest.fixture()
    def sda_citando(self, app, db, tmp_path):
        """Una SdA que cita el saber que luego va a desaparecer del boletín."""
        _escribir(tmp_path, _json("cataluna", "Mates", saberes=[("A.1", "Saber citado")]))
        seed_curriculo(tmp_path)

        rol = db.session.scalar(select(Rol).where(Rol.nombre == Rol.DOCENTE))
        usuario = Usuario(id_rol=rol.id_rol, correo="ana@ies.es", nombre="Ana")
        usuario.set_password("Segura1234")
        db.session.add(usuario)
        db.session.flush()

        sa = SituacionAprendizaje(
            id_usuario=usuario.id_usuario, titulo="Prueba",
            curso="1º ESO", materia="Mates", comunidad_autonoma="Cataluña",
        )
        sa.saberes = list(db.session.scalars(
            select(SaberBasico).where(SaberBasico.codigo == "A.1")
        ).all())
        db.session.add(sa)
        db.session.commit()
        return tmp_path

    def test_el_saber_citado_no_se_borra(self, app, db, sda_citando):
        """Borrarlo dejaría el documento de esa SdA diciendo «(no encontrado en
        el currículo)» donde antes había texto, sin que nadie haya tocado nada.

        Y técnicamente ni siquiera se puede: el enlace es RESTRICT, así que el
        intento abortaría la carga entera con un IntegrityError."""
        _escribir(sda_citando, _json("cataluna", "Mates", saberes=[("A.9", "Otro")]))

        seed_curriculo(sda_citando, borrar_sobrantes=True)

        assert _saberes() == {"A.1", "A.9"}, "se borró un saber en uso"

    def test_se_informa_de_lo_que_se_conserva(self, app, db, sda_citando):
        """Callarlo haría que el recuento no cuadrara con el boletín y nadie
        supiera por qué."""
        _escribir(sda_citando, _json("cataluna", "Mates", saberes=[("A.9", "Otro")]))

        total = seed_curriculo(sda_citando, borrar_sobrantes=True)

        assert total["saber_en_uso"] == 1
        assert total["saber_borradas"] == 0

    def test_lo_conservado_se_retira_de_la_oferta(self, app, db, sda_citando):
        """EL CICLO QUE ESTO ROMPE.

        Conservar la fila tal cual la deja **en el catálogo que ve el modelo**,
        y entonces no hay salida: pasó el 27/08 con el País Vasco, donde seis
        saberes con el texto mal extraído sobrevivieron porque una SdA los
        citaba, siguieron ofreciéndose, y al regenerar esa misma SdA el modelo
        volvió a citarlos. A la carga siguiente seguían en uso.

        Vaciar `cursos_aplicables` los saca del contexto sin borrarlos:
        `contexto.py` filtra con el operador `?` de JSONB, que con la lista
        vacía no casa con ningún curso.
        """
        _escribir(sda_citando, _json("cataluna", "Mates", saberes=[("A.9", "Otro")]))

        seed_curriculo(sda_citando, borrar_sobrantes=True)

        viejo = db.session.scalar(
            select(SaberBasico).where(SaberBasico.codigo == "A.1")
        )
        assert viejo is not None, "no se ha borrado, que es lo que se quería"
        assert viejo.cursos_aplicables == [], (
            "sigue ofreciéndose al modelo: se volverá a citar y no habrá "
            "forma de retirarlo nunca"
        )

    def test_pero_el_texto_sigue_ahi_para_quien_lo_cita(self, app, db, sda_citando):
        """La SdA que ya lo cita no se entera: la exportación lee el texto por
        la relación ya enlazada y no vuelve a filtrar por curso.

        Sin esta comprobación, el arreglo de arriba podría haber dejado el
        documento diciendo «(no encontrado en el currículo)», que es justo lo
        que se quería evitar al conservar la fila."""
        _escribir(sda_citando, _json("cataluna", "Mates", saberes=[("A.9", "Otro")]))

        seed_curriculo(sda_citando, borrar_sobrantes=True)

        sa = db.session.scalar(select(SituacionAprendizaje))
        assert [s.descripcion for s in sa.saberes] == ["Saber citado"]

    def test_la_carga_no_falla_por_intentarlo(self, app, db, sda_citando):
        """Si se intentara borrar sin comprobar el enlace, PostgreSQL lanzaría
        IntegrityError y **se perdería la carga entera**, no solo el borrado."""
        _escribir(sda_citando, _json("cataluna", "Mates", saberes=[("A.9", "Otro")]))

        total = seed_curriculo(sda_citando, borrar_sobrantes=True)

        assert total["ficheros"] == 1
        assert "A.9" in _saberes(), "la carga se perdió al fallar el borrado"
