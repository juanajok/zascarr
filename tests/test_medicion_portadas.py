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
