"""Carga los 17 Objetivos de Desarrollo Sostenible de la Agenda 2030 de la ONU."""
from __future__ import annotations

from sqlalchemy import select

from ..extensions import db
from ..models import ODS


ODS_OFICIALES: list[dict] = [
    {
        "numero": 1,
        "nombre": "Fin de la pobreza",
        "descripcion": "Poner fin a la pobreza en todas sus formas y en todo el mundo.",
    },
    {
        "numero": 2,
        "nombre": "Hambre cero",
        "descripcion": (
            "Poner fin al hambre, lograr la seguridad alimentaria y la mejora "
            "de la nutrición y promover la agricultura sostenible."
        ),
    },
    {
        "numero": 3,
        "nombre": "Salud y bienestar",
        "descripcion": "Garantizar una vida sana y promover el bienestar para todos en todas las edades.",
    },
    {
        "numero": 4,
        "nombre": "Educación de calidad",
        "descripcion": (
            "Garantizar una educación inclusiva, equitativa y de calidad y "
            "promover oportunidades de aprendizaje durante toda la vida para todos."
        ),
    },
    {
        "numero": 5,
        "nombre": "Igualdad de género",
        "descripcion": "Lograr la igualdad entre los géneros y empoderar a todas las mujeres y las niñas.",
    },
    {
        "numero": 6,
        "nombre": "Agua limpia y saneamiento",
        "descripcion": "Garantizar la disponibilidad de agua y su gestión sostenible y el saneamiento para todos.",
    },
    {
        "numero": 7,
        "nombre": "Energía asequible y no contaminante",
        "descripcion": (
            "Garantizar el acceso a una energía asequible, segura, sostenible "
            "y moderna para todos."
        ),
    },
    {
        "numero": 8,
        "nombre": "Trabajo decente y crecimiento económico",
        "descripcion": (
            "Promover el crecimiento económico sostenido, inclusivo y sostenible, "
            "el empleo pleno y productivo y el trabajo decente para todos."
        ),
    },
    {
        "numero": 9,
        "nombre": "Industria, innovación e infraestructura",
        "descripcion": (
            "Construir infraestructuras resilientes, promover la industrialización "
            "inclusiva y sostenible y fomentar la innovación."
        ),
    },
    {
        "numero": 10,
        "nombre": "Reducción de las desigualdades",
        "descripcion": "Reducir la desigualdad en y entre los países.",
    },
    {
        "numero": 11,
        "nombre": "Ciudades y comunidades sostenibles",
        "descripcion": (
            "Lograr que las ciudades y los asentamientos humanos sean inclusivos, "
            "seguros, resilientes y sostenibles."
        ),
    },
    {
        "numero": 12,
        "nombre": "Producción y consumo responsables",
        "descripcion": "Garantizar modalidades de consumo y producción sostenibles.",
    },
    {
        "numero": 13,
        "nombre": "Acción por el clima",
        "descripcion": "Adoptar medidas urgentes para combatir el cambio climático y sus efectos.",
    },
    {
        "numero": 14,
        "nombre": "Vida submarina",
        "descripcion": (
            "Conservar y utilizar sosteniblemente los océanos, los mares y los "
            "recursos marinos para el desarrollo sostenible."
        ),
    },
    {
        "numero": 15,
        "nombre": "Vida de ecosistemas terrestres",
        "descripcion": (
            "Proteger, restablecer y promover el uso sostenible de los ecosistemas "
            "terrestres, gestionar sosteniblemente los bosques, luchar contra la "
            "desertificación, detener e invertir la degradación de las tierras y "
            "detener la pérdida de biodiversidad."
        ),
    },
    {
        "numero": 16,
        "nombre": "Paz, justicia e instituciones sólidas",
        "descripcion": (
            "Promover sociedades pacíficas e inclusivas para el desarrollo sostenible, "
            "facilitar el acceso a la justicia para todos y construir instituciones "
            "eficaces, responsables e inclusivas a todos los niveles."
        ),
    },
    {
        "numero": 17,
        "nombre": "Alianzas para lograr los objetivos",
        "descripcion": (
            "Fortalecer los medios de implementación y revitalizar la Alianza "
            "Mundial para el Desarrollo Sostenible."
        ),
    },
]


def seed_ods() -> dict[str, int]:
    """Inserta los 17 ODS si no existen. Idempotente."""
    creados = 0
    actualizados = 0
    for data in ODS_OFICIALES:
        ods = db.session.scalar(select(ODS).where(ODS.numero == data["numero"]))
        if ods is None:
            ods = ODS(**data)
            db.session.add(ods)
            creados += 1
        else:
            ods.nombre = data["nombre"]
            ods.descripcion = data["descripcion"]
            actualizados += 1
    db.session.commit()
    return {"creados": creados, "actualizados": actualizados}
