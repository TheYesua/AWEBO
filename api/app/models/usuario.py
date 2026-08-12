"""Entidad Usuario."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import bcrypt
from flask_login import UserMixin
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    from .rol import Rol
    from .situacion import SituacionAprendizaje


class Usuario(db.Model, UserMixin):
    """Usuario registrado en el sistema (docente o administrador)."""

    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    id_rol: Mapped[int] = mapped_column(
        ForeignKey("rol.id_rol", ondelete="RESTRICT"), nullable=False, index=True
    )

    correo: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    contrasena_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # ----- Correo de respaldo (tarea 13) -----
    #
    # Una dirección **personal**, distinta de la del centro. Existe porque los
    # correos institucionales se reciclan: `jperez@ies.es` puede ser de otra
    # persona al curso siguiente, y entonces la dirección deja de identificar a
    # nadie. El respaldo sobrevive al cambio de centro, así que es el único
    # ancla de identidad estable que tiene una cuenta.
    #
    # NO es único a propósito. Dos cuentas pueden compartir una dirección
    # personal —una pareja de docentes, por ejemplo—, y prohibirlo tendría
    # además un efecto feo: al rechazar «esa dirección ya está en uso» se
    # estaría contando que existe una cuenta con ese respaldo. Cuando una
    # dirección corresponde a varias cuentas, cada una recibe su propio enlace.
    correo_respaldo: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    #: Cuándo se confirmó el respaldo. **Un respaldo sin verificar no sirve
    #: para nada**, y eso cierra un agujero: si contara sin más, cualquiera
    #: podría poner como respaldo la dirección de otra persona y provocar que
    #: le lleguen a esa persona enlaces de restablecimiento de una cuenta
    #: ajena. Confuso en el mejor caso, y una palanca de engaño en el peor.
    correo_respaldo_verificado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    centro_educativo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    especialidad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comunidad_autonoma: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Preferencia de IA. NULL en ambos = «usar el del sistema», que es el
    # valor de partida de toda cuenta y el comportamiento histórico.
    # Se validan contra el catálogo en cada uso, no solo al guardarlos: si un
    # proveedor desaparece del .env, la cuenta vuelve al del sistema en lugar
    # de quedarse inservible.
    proveedor_ia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    modelo_ia: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Idioma de la INTERFAZ, no del contenido de las situaciones. NULL = se
    # deduce del navegador. Va en el perfil y no en una cookie porque el
    # idioma es propiedad de la persona: nadie lee en catalán en el portátil
    # y en castellano en el móvil. El tema sí es del dispositivo, y por eso
    # aquel vive en una cookie.
    idioma_interfaz: Mapped[str | None] = mapped_column(String(5), nullable=True)

    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ultima_sesion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Lápida: la cuenta está dada de baja pero la fila sigue aquí. NULL = viva.
    #
    # Por qué una marca y no borrar la fila: ``SituacionAprendizaje.id_usuario``
    # es NOT NULL con ondelete CASCADE. Conservar el contenido de alguien que
    # se da de baja obligaría a hacer esa clave ajena nullable, y entonces toda
    # consulta que filtre por propietario tendría que contemplar el caso NULL.
    # Se perdería la invariante que hoy hace segura la aplicación: toda SA
    # tiene dueño.
    #
    # Con la lápida no se pierde nada. La cuenta no puede iniciar sesión, el
    # contenido sigue ligado como siempre, y la unicidad de ``correo`` se
    # mantiene — que es justo lo que permite detectar un intento de volver a
    # registrarse con ese correo y ofrecer la reclamación. Al vencer el plazo,
    # purgar es un DELETE normal sobre ``usuario``: el CASCADE que ya existe
    # hace exactamente lo correcto, sin añadir nada.
    #
    # Indexada porque el purgado periódico filtra por ella.
    eliminado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Solicitud de recuperar el contenido de esta cuenta, a la espera de que un
    # administrador la apruebe. NULL = no hay ninguna.
    #
    # Guarda los datos con los que la persona quiere entrar (nombre, centro,
    # y el **hash** de la contraseña, nunca la contraseña) sin aplicarlos. Si
    # se aplicaran ya, rechazar la solicitud dejaría machacados los datos de la
    # persona anterior, que es a quien se está protegiendo.
    #
    # Un JSONB y no una tabla aparte: el dato es corto, efímero y siempre se
    # consulta junto a su usuario, así que una tabla añadiría una clave ajena y
    # un borrado en cascada más a cambio de nada. Encaja además con cómo el
    # proyecto ya guarda `permisos`, `contenido` y `cursos_aplicables`.
    reclamacion_pendiente: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    rol: Mapped["Rol"] = relationship(back_populates="usuarios", lazy="joined")
    situaciones: Mapped[list["SituacionAprendizaje"]] = relationship(
        back_populates="usuario",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # ----- Flask-Login -----
    def get_id(self) -> str:  # noqa: D401
        """Identificador como string requerido por Flask-Login."""
        return str(self.id_usuario)

    # ----- Contraseñas -----
    def set_password(self, plain: str) -> None:
        """Genera y almacena el hash bcrypt de la contraseña en claro."""
        self.contrasena_hash = bcrypt.hashpw(
            plain.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, plain: str) -> bool:
        """Comprueba una contraseña contra el hash almacenado."""
        if not self.contrasena_hash:
            return False
        return bcrypt.checkpw(
            plain.encode("utf-8"), self.contrasena_hash.encode("utf-8")
        )

    def touch_last_seen(self) -> None:
        """Marca el momento del último acceso del usuario."""
        self.ultima_sesion = datetime.now(timezone.utc)

    # ----- Baja lógica -----
    #: Plazo durante el cual el contenido de una cuenta dada de baja sigue
    #: siendo reclamable. En días y no en meses a propósito: «tres meses» no
    #: dura lo mismo en febrero que en agosto, y aquí no hay ninguna razón para
    #: heredar esa ambigüedad. Son 90 días.
    DIAS_DE_GRACIA = 90

    @property
    def tiene_respaldo(self) -> bool:
        """Si esta cuenta puede probar su identidad por otra vía.

        Exige las dos cosas: dirección **y** verificación. Preguntar solo por
        la dirección daría por bueno un respaldo que alguien escribió y nunca
        confirmó, que es exactamente el caso que no debe contar.
        """
        return bool(self.correo_respaldo) and self.correo_respaldo_verificado_en is not None

    @property
    def esta_eliminado(self) -> bool:
        return self.eliminado_en is not None

    def marcar_eliminado(self) -> None:
        """Da de baja la cuenta conservando su contenido."""
        self.eliminado_en = datetime.now(timezone.utc)

    @property
    def gracia_vencida(self) -> bool:
        """Si el plazo de reclamación ya pasó y el contenido puede purgarse."""
        if self.eliminado_en is None:
            return False
        marca = self.eliminado_en
        # Postgres devuelve el valor con zona, pero un objeto recién creado en
        # memoria puede no tenerla. Comparar naive con aware lanza TypeError.
        if marca.tzinfo is None:
            marca = marca.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - marca >= timedelta(days=self.DIAS_DE_GRACIA)

    # ----- Helpers de rol -----
    @property
    def es_administrador(self) -> bool:
        return self.rol is not None and self.rol.nombre == "administrador"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario id={self.id_usuario} correo={self.correo!r}>"
