"""
tests/test_medicion_portadas.py

Banco de portadas de BL-PORT1 (#300, AC-12). Dos propiedades que decidió QA:

  - La exención «p95 ≤ 600 ms si el original supera 12 Mpx» tiene que mirar el
    tamaño **real** de la primera página, no el de la salida ya reducida (un
    4000×4000 se mide a 600×600: si se usa ese 360 000, la exención es letra
    muerta).
  - La evidencia de AC-12 se versiona en `docs/design/`: el JSON y la consola
    no pueden publicar rutas del disco (ni la carpeta base ni rutas por
    archivo), solo nombres de fichero y recuentos.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from scripts.medicion import banco_portadas


def _cbz(destino: Path, ancho: int, alto: int) -> Path:
    """CBZ mínimo con una página del tamaño pedido (no importa el contenido)."""
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=(40, 80, 120)).save(buf, format="JPEG")
    with zipfile.ZipFile(destino, "w") as zf:
        zf.writestr("001.jpg", buf.getvalue())
    return destino


class TestPixelesOriginal:
    def test_imagen_grande_usa_el_tamano_real_y_cuenta_como_grande(self, tmp_path):
        path = _cbz(tmp_path / "grande.cbz", 4000, 4000)

        caso, motivo = banco_portadas._medir_archivo(path, 600, 1)

        assert motivo is None and caso is not None
        assert caso["pixeles_original"] == 16_000_000, "se está midiendo la salida, no el original"
        assert caso["pixeles_salida"] == 600 * 600
        resumen = banco_portadas._resumen([caso], 600)
        assert resumen["n_archivos_grandes"] == 1, "la exención de 600 ms quedaría muerta"

    def test_imagen_pequena_no_es_grande_y_no_se_amplia(self, tmp_path):
        path = _cbz(tmp_path / "pequena.cbz", 400, 600)

        caso, motivo = banco_portadas._medir_archivo(path, 600, 1)

        assert motivo is None and caso is not None
        assert caso["pixeles_original"] == 240_000
        assert caso["ancho_salida"] == 400
        assert banco_portadas._resumen([caso], 600)["n_archivos_grandes"] == 0


class TestEvidenciaSinRutas:
    def test_el_json_y_la_consola_no_publican_rutas(self, tmp_path, capsys):
        carpeta = tmp_path / "Comics" / "Serie privada"
        carpeta.mkdir(parents=True)
        _cbz(carpeta / "comic 01.cbz", 400, 600)
        (carpeta / "roto.cbz").write_bytes(b"esto no es un zip")
        destino = tmp_path / "informe.json"

        codigo = banco_portadas.main([
            "--carpeta", str(carpeta), "--muestra", "5", "--repeticiones", "1",
            "--json", str(destino),
        ])

        texto = destino.read_text(encoding="utf-8")
        datos = json.loads(texto)

        assert codigo == 0
        assert str(tmp_path) not in texto, "el JSON de evidencia no debe llevar ruta absoluta"
        assert datos["carpeta_relativa"] == "."
        assert datos["n_fallos"] == 1 and datos["motivos"] == {"sin_lectura": 1}
        for nombre in [caso["archivo"] for caso in datos["casos"]["600"]]:
            assert "/" not in nombre and "\\" not in nombre
        for fallo in datos["fallos"]:
            assert "/" not in fallo["archivo"] and "\\" not in fallo["archivo"]
        salida = capsys.readouterr().out
        assert str(tmp_path) not in salida, "la consola (que se adjunta) no debe llevar rutas"
        assert "Aviso" in salida, "1 archivo medido de una muestra de 5 debe avisar"

    def test_codigo_de_salida_1_si_algo_no_cumple(self, tmp_path, monkeypatch):
        _cbz(tmp_path / "comic.cbz", 400, 600)
        monkeypatch.setattr(banco_portadas, "UMBRAL_P95_MS", {240: 0.0, 600: 0.0})

        codigo = banco_portadas.main([
            "--carpeta", str(tmp_path), "--muestra", "1", "--repeticiones", "1",
        ])

        assert codigo == 1, "un FAIL del banco debe salir con código 1"


# ═══════════════════════════════════════════════════════════════════════════════
# Censo de portadas por debajo del objetivo (#411, BL-PORT1 3/3; FR-13/FR-14)
# ═══════════════════════════════════════════════════════════════════════════════

from scripts.medicion import censo_portadas as censo  # noqa: E402


def _cbz_de(destino: Path, ancho: int, alto: int) -> Path:
    return _cbz(destino, ancho, alto)


def _fichero(path: Path, formato=None) -> censo.FicheroResumen:
    return censo.FicheroResumen(str(path), formato_contenido=formato)


def _sonda(ancho: int | None, extraible: bool = True) -> censo.Sonda:
    return censo.Sonda(mide=ancho is not None, ancho=ancho, alto=None, extraible=extraible)


class TestClasificadorPuro:
    """Las seis clases con un probe inyectado: ni BD ni disco (AC-16)."""

    def _clase(self, serie, ficheros, sondas):
        return censo.clasificar(serie, ficheros, lambda f: sondas[f.ruta])

    def test_ya_en_objetivo(self):
        serie = censo.SerieResumen("s1", hay_v2=True, ancho_v2=600)
        assert self._clase(serie, [], {}) == censo.Clase.YA_EN_OBJETIVO

    def test_regenerable_al_pedir(self):
        ficheros = [censo.FicheroResumen("a")]
        serie = censo.SerieResumen("s2")
        assert self._clase(serie, ficheros, {"a": _sonda(1600)}) == censo.Clase.REGENERABLE_AL_PEDIR

    def test_extraible_mas_adelante(self):
        """El primero no se extrae, el segundo sí: no es «sin extractor» (AC-16)."""
        ficheros = [censo.FicheroResumen("cbr"), censo.FicheroResumen("cbz")]
        serie = censo.SerieResumen("s3")
        sondas = {"cbr": _sonda(None, extraible=False), "cbz": _sonda(1600)}
        assert self._clase(serie, ficheros, sondas) == censo.Clase.EXTRAIBLE_MAS_ADELANTE

    def test_original_pequeno(self):
        ficheros = [censo.FicheroResumen("a")]
        serie = censo.SerieResumen("s4")
        assert self._clase(serie, ficheros, {"a": _sonda(400)}) == censo.Clase.ORIGINAL_PEQUENO

    def test_sin_extractor(self):
        ficheros = [censo.FicheroResumen("cbr")]
        serie = censo.SerieResumen("s5")
        sondas = {"cbr": _sonda(None, extraible=False)}
        assert self._clase(serie, ficheros, sondas) == censo.Clase.SIN_EXTRACTOR

    def test_sin_fuente(self):
        assert self._clase(censo.SerieResumen("s6"), [], {}) == censo.Clase.SIN_FUENTE

    def test_solo_cover_url_sin_file_es_sin_extractor(self):
        """«Sin fuente» exige no tener NI File no ausente NI cover_url (FR-14)."""
        serie = censo.SerieResumen("s7", cover_url="https://x/y.jpg")
        assert self._clase(serie, [], {}) == censo.Clase.SIN_EXTRACTOR

    def test_un_file_ausente_no_cuenta_y_cae_al_siguiente(self):
        ficheros = [censo.FicheroResumen("ausente", is_missing=True), censo.FicheroResumen("cbz")]
        serie = censo.SerieResumen("s8")
        sondas = {"ausente": _sonda(None, extraible=False), "cbz": _sonda(1600)}
        assert self._clase(serie, ficheros, sondas) == censo.Clase.REGENERABLE_AL_PEDIR

    def test_el_primero_pequeno_no_se_arregla_con_el_segundo(self):
        """La cascada solo mira el primero: un segundo grande no cambia la clase."""
        ficheros = [censo.FicheroResumen("pequeno"), censo.FicheroResumen("grande")]
        serie = censo.SerieResumen("s9")
        sondas = {"pequeno": _sonda(400), "grande": _sonda(1600)}
        assert self._clase(serie, ficheros, sondas) == censo.Clase.ORIGINAL_PEQUENO


class TestCifraYRecuento:
    def test_regenerable_no_cuenta_como_queda_por_debajo(self):
        clases = {
            "a": censo.Clase.REGENERABLE_AL_PEDIR,
            "b": censo.Clase.ORIGINAL_PEQUENO,
            "c": censo.Clase.EXTRAIBLE_MAS_ADELANTE,
            "d": censo.Clase.SIN_EXTRACTOR,
            "e": censo.Clase.SIN_FUENTE,
        }
        conteo = censo.recuento(clases)
        assert conteo[censo.Clase.REGENERABLE_AL_PEDIR] == 1
        assert censo.cifra_bl_port2(conteo) == 4   # no incluye regenerable

    def test_cada_serie_cae_en_una_sola_clase_y_hay_seis(self):
        assert len(censo.ORDEN_CLASES) == 6
        assert len(set(censo.ORDEN_CLASES)) == 6
        assert set(censo.ORDEN_CLASES) == {c for c in censo.Clase}

    def test_el_json_solo_tiene_ids_y_clases_sin_rutas(self):
        clases = {"11111111-1111-1111-1111-111111111111": censo.Clase.ORIGINAL_PEQUENO}
        info = censo.informe_json(clases)
        assert set(info) == {"generado", "objetivo_px", "total", "clases",
                             "cifra_bl_port2", "estado", "series"}
        assert info["series"] == [{"serie_id": "11111111-1111-1111-1111-111111111111",
                                   "clase": "original_pequeno"}]
        serializado = json.dumps(info, ensure_ascii=False)
        assert "/tmp/" not in serializado and "file_path" not in serializado
        assert ".cbz" not in serializado and "cover_url" not in serializado
        assert info["estado"]["decision_BL_PORT2"] == "NOT RUN"
        assert info["cifra_bl_port2"] == 1


class TestProbeReal:
    """Mismo predicado que la cascada, con CBZ reales mínimos; sin red ni escritura de caché."""

    def test_cbz_grande_mide_su_primera_pagina_y_es_extraible(self, tmp_path):
        path = _cbz_de(tmp_path / "grande.cbz", 1600, 2400)
        sonda = censo.probe_fichero(_fichero(path))
        assert (sonda.mide, sonda.ancho, sonda.alto, sonda.extraible) == (True, 1600, 2400, True)

    def test_cbz_pequeno_mide_pero_no_llega_al_objetivo(self, tmp_path):
        path = _cbz_de(tmp_path / "pequeno.cbz", 400, 600)
        sonda = censo.probe_fichero(_fichero(path))
        assert (sonda.mide, sonda.ancho, sonda.extraible) == (True, 400, True)

    def test_cbr_sin_extractor_no_se_abre(self, tmp_path):
        path = tmp_path / "real.cbr"
        path.write_bytes(b"Rar!\x1a\x07\x00contenido")
        sonda = censo.probe_fichero(_fichero(path))
        assert sonda.extraible is False and sonda.mide is False

    def test_un_ausente_no_se_abre(self, tmp_path):
        sonda = censo.probe_fichero(_fichero(tmp_path / "no-existe.cbz"))
        assert sonda.extraible is False

    def test_un_fichero_que_no_es_zip_con_extension_cbz_no_es_extraible(self, tmp_path):
        path = tmp_path / "falso.cbz"
        path.write_bytes(b"no es un zip")
        sonda = censo.probe_fichero(_fichero(path))
        assert sonda.extraible is False


class TestCensoCompleto:
    """Clasificación de principio a fin con caché temporal y probe real (sin BD)."""

    def _censo(self, tmp_path, series):
        covers = tmp_path / "covers"
        covers.mkdir(exist_ok=True)
        return censo.clasificar_series(series, covers)

    def _v2(self, tmp_path, serie_id: str, ancho: int):
        v2 = tmp_path / "covers" / censo.CACHE_VERSION
        v2.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        Image.new("RGB", (ancho, ancho * 2), color=(10, 20, 30)).save(buf, format="JPEG")
        (v2 / f"{serie_id}.jpg").write_bytes(buf.getvalue())

    def test_las_seis_clases_en_una_pasada(self, tmp_path):
        big = _cbz_de(tmp_path / "big.cbz", 1600, 2400)
        small = _cbz_de(tmp_path / "small.cbz", 400, 600)
        cbr = tmp_path / "real.cbr"
        cbr.write_bytes(b"Rar!\x1a\x07\x00")
        series = [
            censo.SerieCenso("ya", None, []),
            censo.SerieCenso("regen", None, [censo.FicheroResumen(str(big))]),
            censo.SerieCenso("adelante", None, [censo.FicheroResumen(str(cbr)),
                                                 censo.FicheroResumen(str(big))]),
            censo.SerieCenso("pequena", None, [censo.FicheroResumen(str(small))]),
            censo.SerieCenso("sin_extractor", None, [censo.FicheroResumen(str(cbr))]),
            censo.SerieCenso("sin_fuente", None, []),
        ]
        self._v2(tmp_path, "ya", 600)
        clases = self._censo(tmp_path, series)
        assert clases == {
            "ya": censo.Clase.YA_EN_OBJETIVO,
            "regen": censo.Clase.REGENERABLE_AL_PEDIR,
            "adelante": censo.Clase.EXTRAIBLE_MAS_ADELANTE,
            "pequena": censo.Clase.ORIGINAL_PEQUENO,
            "sin_extractor": censo.Clase.SIN_EXTRACTOR,
            "sin_fuente": censo.Clase.SIN_FUENTE,
        }
        assert len(set(clases.values())) == 6
        assert censo.cifra_bl_port2(censo.recuento(clases)) == 4

    def test_una_v2_pequena_no_cuenta_como_objetivo(self, tmp_path):
        big = _cbz_de(tmp_path / "big.cbz", 1600, 2400)
        self._v2(tmp_path, "s", 400)
        clases = self._censo(tmp_path, [censo.SerieCenso("s", None, [_fichero(big)])])
        assert clases["s"] == censo.Clase.REGENERABLE_AL_PEDIR

    def test_escribir_json_y_csv_no_publica_rutas(self, tmp_path):
        big = _cbz_de(tmp_path / "big.cbz", 1600, 2400)
        clases = {"id-1": censo.Clase.REGENERABLE_AL_PEDIR}
        json_path, csv_path = tmp_path / "informe.json", tmp_path / "informe.csv"
        censo.escribir_salida(clases, json_path=str(json_path), csv_path=str(csv_path))
        texto = json_path.read_text(encoding="utf-8")
        assert str(big) not in texto and "file_path" not in texto
        assert json.loads(texto)["series"] == [
            {"serie_id": "id-1", "clase": "regenerable_al_pedir"}]
        assert csv_path.read_text(encoding="utf-8") == (
            "serie_id,clase\nid-1,regenerable_al_pedir\n")


class TestEstadosDelInforme:
    """PASS/FAIL/NOT RUN separados (AC-15) y sin efectos sobre la caché."""

    def test_sin_database_url_es_fail(self, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
        assert censo.main([]) == 2
        assert "Falta DATABASE_URL" in capsys.readouterr().err

    def test_una_base_vacia_es_not_run_y_no_escribe_en_la_cache(
            self, tmp_path, monkeypatch, capsys):
        async def vacia(_url):
            return []
        monkeypatch.setattr(censo, "leer_series", vacia)
        covers = tmp_path / "covers"
        covers.mkdir()
        json_path = tmp_path / "informe.json"
        rc = censo.main(["--database-url", "postgresql://x", "--covers", str(covers),
                         "--json", str(json_path)])
        assert rc == 0
        info = json.loads(json_path.read_text(encoding="utf-8"))
        assert info["estado"]["lectura"] == "NOT RUN"
        assert info["estado"]["clasificacion"] == "NOT RUN"
        assert info["series"] == []
        assert list(covers.iterdir()) == []          # no se escribió nada en la caché
        salida = capsys.readouterr().out
        assert "NOT RUN" in salida and "decisión BL-PORT2" in salida
