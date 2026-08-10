"""Tests de la síntesis de voz (tarea 8b).

El primero es el que importa, igual que en el correo: que el proveedor por
defecto **no llame a nadie**. Allí el riesgo era mandar un correo real a una
dirección de prueba; aquí es gastar dinero, porque la síntesis se factura por
caracteres y una SA completa ronda los diez mil.

Lo demás son comodidades. Esa no.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.voz import Audio, Locucion, VozError, obtener_proveedor
from app.voz.nulo import ProveedorNulo
from app.voz.openai_voz import LIMITE_CARACTERES, ProveedorOpenAI


@pytest.fixture
def locucion():
    return Locucion(texto="Sesión 1: presentación del reto.", idioma="gl")


class TestElDefectoNoGenera:
    def test_sin_configurar_nada_el_proveedor_es_el_nulo(self, app):
        with app.test_request_context():
            app.config.pop("VOZ_PROVEEDOR", None)
            assert isinstance(obtener_proveedor(), ProveedorNulo)

    def test_el_nulo_no_abre_ninguna_conexion(self, app, locucion):
        """No basta con que no genere: hay que ver que no toca la red."""
        with app.test_request_context():
            with patch("openai.OpenAI") as cliente:
                with pytest.raises(VozError):
                    ProveedorNulo().sintetizar(locucion)
            cliente.assert_not_called()

    def test_el_nulo_falla_en_vez_de_devolver_silencio(self, app, locucion):
        """La tentación es devolver un MP3 mudo para que «no falle».

        Sería la misma trampa que un mock que no comprueba nada: todo verde y
        nada funcionando, y quien pulsara el botón oiría silencio sin saber por
        qué. El error dice qué variable falta.
        """
        with app.test_request_context():
            with pytest.raises(VozError, match="VOZ_PROVEEDOR"):
                ProveedorNulo().sintetizar(locucion)

    def test_un_nombre_desconocido_cae_al_nulo_y_avisa(self, app, caplog):
        import logging

        with app.test_request_context():
            app.config["VOZ_PROVEEDOR"] = "elevenlabs-typo"
            with caplog.at_level(logging.WARNING, logger="voz.factoria"):
                proveedor = obtener_proveedor()

        assert isinstance(proveedor, ProveedorNulo)
        assert "elevenlabs-typo" in caplog.text


class TestProveedorOpenAI:
    def test_se_puede_pedir_explicitamente(self, app):
        with app.test_request_context():
            app.config["VOZ_PROVEEDOR"] = "openai"
            assert isinstance(obtener_proveedor(), ProveedorOpenAI)

    def test_sin_clave_falla_claro(self, app, locucion):
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = ""
            with pytest.raises(VozError, match="OPENAI_API_KEY"):
                ProveedorOpenAI().sintetizar(locucion)

    def test_un_texto_vacio_no_llega_a_pedirse(self, app):
        """Con cadena vacía el proveedor devolvía un audio de cero bytes, que
        en el navegador es un reproductor que no suena y no explica nada."""
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = "sk-loquesea"
            with patch("openai.OpenAI") as cliente:
                with pytest.raises(VozError, match="texto"):
                    ProveedorOpenAI().sintetizar(Locucion(texto="   ", idioma="es"))
            cliente.assert_not_called()

    def test_pasado_el_limite_se_dice_cuanto_sobra(self, app):
        """El 400 del proveedor llega envuelto en varias capas y no dice
        cuántos caracteres sobran, que es lo único que hace falta saber."""
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = "sk-loquesea"
            largo = "a" * (LIMITE_CARACTERES + 1)
            with patch("openai.OpenAI") as cliente:
                with pytest.raises(VozError) as exc:
                    ProveedorOpenAI().sintetizar(Locucion(texto=largo, idioma="es"))
            cliente.assert_not_called()
            assert str(LIMITE_CARACTERES) in str(exc.value)
            assert str(len(largo)) in str(exc.value)

    def test_devuelve_los_bytes_que_da_el_proveedor(self, app, locucion):
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = "sk-loquesea"
            with patch("openai.OpenAI") as OpenAI:
                respuesta = MagicMock()
                respuesta.read.return_value = b"ID3-esto-es-un-mp3"
                OpenAI.return_value.audio.speech.create.return_value = respuesta
                audio = ProveedorOpenAI().sintetizar(locucion)

        assert audio.datos == b"ID3-esto-es-un-mp3"
        assert audio.formato == "mp3"
        assert audio.tipo_mime == "audio/mpeg"

    def test_un_audio_vacio_se_trata_como_fallo(self, app, locucion):
        """Un MP3 de cero bytes es un botón que no hace nada."""
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = "sk-loquesea"
            with patch("openai.OpenAI") as OpenAI:
                respuesta = MagicMock()
                respuesta.read.return_value = b""
                OpenAI.return_value.audio.speech.create.return_value = respuesta
                with pytest.raises(VozError, match="vacío"):
                    ProveedorOpenAI().sintetizar(locucion)

    def test_un_fallo_del_proveedor_se_traduce_a_VozError(self, app, locucion):
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = "sk-loquesea"
            with patch("openai.OpenAI") as OpenAI:
                OpenAI.return_value.audio.speech.create.side_effect = RuntimeError("boom")
                with pytest.raises(VozError):
                    ProveedorOpenAI().sintetizar(locucion)

    def test_el_error_registrado_no_lleva_el_texto(self, app, caplog):
        """Estos registros acaban en sitios donde no debería haber contenido
        de las situaciones de nadie, y los mensajes de error de los clientes
        HTTP suelen incluir el cuerpo de la petición."""
        import logging

        secreto = "Reto sobre el consumo de agua en el centro"
        with app.test_request_context():
            app.config["OPENAI_API_KEY"] = "sk-loquesea"
            with caplog.at_level(logging.ERROR, logger="voz.openai"):
                with patch("openai.OpenAI") as OpenAI:
                    OpenAI.return_value.audio.speech.create.side_effect = RuntimeError(secreto)
                    with pytest.raises(VozError):
                        ProveedorOpenAI().sintetizar(Locucion(texto=secreto, idioma="es"))

        assert secreto not in caplog.text


class TestElTipoMime:
    def test_cada_formato_tiene_el_suyo(self):
        assert Audio(b"x", "mp3").tipo_mime == "audio/mpeg"
        assert Audio(b"x", "wav").tipo_mime == "audio/wav"

    def test_un_formato_desconocido_no_miente(self):
        """Devolver `audio/mpeg` por defecto haría que el navegador intentara
        reproducir como MP3 algo que no lo es, y el fallo aparecería lejos."""
        assert Audio(b"x", "flac").tipo_mime == "application/octet-stream"


class TestAdaptarElTexto:
    """La normalización previa a la síntesis.

    EL FALLO QUE ORIGINÓ ESTE BLOQUE
    ---------------------------------
    La primera versión traducía la raya larga «—» por un guion «-» para que
    cupiera en ISO-8859-1. Al probar las cuatro lenguas, el catalán reventaba
    con `std::invalid_argument: stoll` dejando un WAV de 44 bytes —la cabecera
    sin una sola muestra—. Aislando frase a frase apareció el culpable: **un
    guion suelto entre espacios mata el proceso**, y solo en catalán, que es el
    único que usa espeak-ng como frente lingüístico.

    O sea: mi arreglo *provocaba* el fallo. Con el texto de ejemplo del README
    —«Hola, qué tal»— no habría aparecido nunca.
    """

    def test_la_raya_larga_se_vuelve_coma_y_no_guion(self):
        from app.voz.local import _adaptar

        salida = _adaptar("Sesión 1 — análisis del aula", "iso-8859-1")
        assert "," in salida
        assert " - " not in salida, "un guion suelto estrella el motor en catalán"

    def test_un_guion_suelto_de_entrada_tambien_se_neutraliza(self):
        """No basta con no crearlos: el texto puede traerlos ya escritos."""
        from app.voz.local import _adaptar

        assert " - " not in _adaptar("Sesión 1 - análisis", "utf-8")

    def test_el_guion_dentro_de_palabra_sobrevive(self):
        """`ikaskuntza-egoera` es el término oficial del decreto vasco.
        Convertirlo en «ikaskuntza, egoera» lo destrozaría, y el motor lo
        pronuncia bien tal cual: comprobado ejecutándolo."""
        from app.voz.local import _adaptar

        assert "ikaskuntza-egoera" in _adaptar("Uraren ikaskuntza-egoera", "iso-8859-1")

    def test_lo_que_no_cabe_en_latin1_no_revienta(self):
        """Guion largo, puntos suspensivos y comilla tipográfica son lo que
        escribe un modelo de lenguaje, y ninguno existe en ISO-8859-1. Antes de
        esta función, la primera SdA real habría fallado con
        `UnicodeEncodeError`."""
        from app.voz.local import _adaptar

        crudo = "El reto: «¿cuánta agua?» — sesión 1 … del alumnado’s"
        # Que no lance es la mitad; la otra es que se pueda codificar de verdad.
        _adaptar(crudo, "iso-8859-1").encode("iso-8859-1")

    def test_se_avisa_cuando_se_pierde_algo(self, caplog):
        """Descartar caracteres es aceptable; hacerlo en silencio, no: si
        empieza a pasar a menudo es que falta una entrada en la tabla."""
        import logging

        from app.voz.local import _adaptar

        with caplog.at_level(logging.WARNING, logger="voz.local"):
            _adaptar("Precio: 100 元 por unidad", "iso-8859-1")

        assert "descartado" in caplog.text


class TestProveedorLocal:
    """Lo que rodea a la llamada al binario.

    La síntesis de verdad se prueba aparte —hace falta aHoTTS entero, 250 MB
    fuera del repositorio—. Aquí van los caminos de error, que es donde han
    estado los fallos de este proyecto.
    """

    def test_un_idioma_sin_voz_se_dice_con_los_que_hay(self, app, tmp_path):
        from app.voz.local import ProveedorLocal

        with app.test_request_context():
            app.config["VOZ_AHOTTS_DIR"] = str(tmp_path)
            with pytest.raises(VozError) as exc:
                ProveedorLocal().sintetizar(Locucion(texto="hola", idioma="fr"))

        assert "fr" in str(exc.value)
        assert "ca" in str(exc.value) and "eu" in str(exc.value)

    def test_sin_el_binario_se_dice_dónde_va(self, app, tmp_path):
        from app.voz.local import ProveedorLocal

        with app.test_request_context():
            app.config["VOZ_AHOTTS_DIR"] = str(tmp_path)
            with pytest.raises(VozError) as exc:
                ProveedorLocal().sintetizar(Locucion(texto="hola", idioma="es"))

        assert "aHoTTS" in str(exc.value) and str(tmp_path) in str(exc.value)

    def test_el_diccionario_es_un_prefijo_no_un_fichero(self, app, tmp_path):
        """`es_dicc` no existe en el disco: existen `es_dicc.dic` y
        `es_dicc_mx.dic`. Comprobarlo con `.exists()` daba «falta el
        diccionario» teniéndolo delante."""
        from app.voz.local import ProveedorLocal

        (tmp_path / "ahotts").mkdir()
        (tmp_path / "ahotts" / "tts").write_bytes(b"\x7fELF")
        voz = tmp_path / "ahotts" / "voices" / "es"
        voz.mkdir(parents=True)
        (voz / "vits.onnx").write_bytes(b"x")
        dicts = tmp_path / "ahotts" / "dicts" / "es"
        dicts.mkdir(parents=True)
        (dicts / "es_dicc.dic").write_text("x", encoding="utf-8")

        with app.test_request_context():
            app.config["VOZ_AHOTTS_DIR"] = str(tmp_path)
            with pytest.raises(VozError) as exc:
                ProveedorLocal().sintetizar(Locucion(texto="hola", idioma="es"))

        # Pasa la comprobación del diccionario y falla más adelante, al ejecutar
        # el ELF de mentira. Lo que importa es que NO se queje del diccionario.
        assert "diccionario" not in str(exc.value)

    def test_el_texto_no_viaja_como_argumento(self, app, tmp_path, monkeypatch):
        """Los argumentos de un proceso los ve cualquiera que liste procesos, y
        aquí el argumento sería el contenido de una situación de aprendizaje."""
        import subprocess

        from app.voz import local

        (tmp_path / "ahotts").mkdir()
        (tmp_path / "ahotts" / "tts").write_bytes(b"\x7fELF")
        voz = tmp_path / "ahotts" / "voices" / "gl"
        voz.mkdir(parents=True)
        (voz / "vits.onnx").write_bytes(b"x")
        (tmp_path / "ahotts" / "dicts" / "gl" / "cotovia").mkdir(parents=True)

        vistos = {}

        def espia(orden, **kwargs):
            vistos["orden"] = orden
            vistos["entrada"] = kwargs.get("input")
            raise OSError("no ejecutamos nada de verdad")

        monkeypatch.setattr(subprocess, "run", espia)
        secreto = "Reto sobre el consumo de agua en el centro"
        with app.test_request_context():
            app.config["VOZ_AHOTTS_DIR"] = str(tmp_path)
            with pytest.raises(VozError):
                local.ProveedorLocal().sintetizar(Locucion(texto=secreto, idioma="gl"))

        assert secreto not in " ".join(vistos["orden"]), "el texto acabó en la línea de órdenes"
        assert secreto.encode("utf-8") in vistos["entrada"], "debe ir por la entrada estándar"
