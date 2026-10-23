# ruff: noqa: E501
"""`scripts/medicion/evaluacion_rar/banco_rar2.py` (spike #308, 2ª tanda): las funciones PURAS y la mecánica de `ejecutar` (tiempo, límites, grupo de procesos)
con órdenes de Python, sin `unar`/`lsar`/`unrar`. El listado `lsar -j` es una réplica del esquema documentado de The Unarchiver: la 1ª ejecución en la Pi lo contrasta."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import zlib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
KIT = RAIZ / "scripts" / "medicion" / "evaluacion_rar"
sys.path.insert(0, str(KIT))
_spec = importlib.util.spec_from_file_location("banco_rar2", KIT / "banco_rar2.py")
b = importlib.util.module_from_spec(_spec)
sys.modules["banco_rar2"] = b
_spec.loader.exec_module(b)


def png(w=8, h=8) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


LSAR = json.dumps({"lsarFormatName": "RAR", "lsarContents": [
    {"XADFileName": "Tomo/", "XADIsDirectory": True, "XADIndex": 0},
    {"XADFileName": "Tomo/10.png", "XADFileSize": 100, "XADIndex": 3, "RARCRC32": 0xDEADBEEF},
    {"XADFileName": "Tomo/2.png", "XADFileSize": 50, "XADIndex": 2},
    {"XADFileName": "Tomo/ComicInfo.xml", "XADFileSize": 20, "XADIndex": 1, "XADIsEncrypted": False}]})


class TestListado:

    def test_entradas_indices_crc_y_esquema(self):
        es, meta = b.parsear_lsar_json(LSAR)
        assert meta["formato"] == "RAR" and meta["claves"] == ["XADFileName", "XADIndex", "XADIsDirectory"]
        d = {e.nombre: e for e in es}
        assert d["Tomo/10.png"].crc == 0xDEADBEEF and d["Tomo/10.png"].indice == 3 and d["Tomo/2.png"].crc is None
        assert d["Tomo/"].directorio and d["Tomo/ComicInfo.xml"].cifrada is False

    def test_primera_y_ultima_en_orden_natural_y_sin_directorios(self):
        es, _ = b.parsear_lsar_json(LSAR)
        pr, ul = b.paginas(es)
        assert (pr.nombre, ul.nombre) == ("Tomo/2.png", "Tomo/10.png")          # 2 antes que 10

    def test_sin_imagenes(self):
        assert b.paginas([]) == (None, None)

    def test_un_bool_no_se_toma_por_un_crc_ni_por_un_tamano(self):
        es, _ = b.parsear_lsar_json(json.dumps({"lsarContents": [{"XADFileName": "a.png", "XADFileSize": True, "XADHasCRC": True}]}))
        assert es[0].crc is None and es[0].tam is None


class TestValidar:

    def test_pagina_buena_con_crc_y_tamano(self):
        d = png()
        e = b.Entrada(0, "a.png", len(d), False, None, zlib.crc32(d) & 0xFFFFFFFF)
        assert b.validar(d, e)["ok"] is True

    def test_crc_distinto_es_fallo_aunque_decodifique(self):
        d = png()
        assert b.validar(d, b.Entrada(0, "a.png", len(d), False, None, 1))["ok"] is False

    def test_tamano_distinto_es_fallo(self):
        d = png()
        assert b.validar(d, b.Entrada(0, "a.png", len(d) + 1, False, None, None))["ok"] is False

    def test_sin_crc_en_el_listado_se_dice_y_no_invalida(self):
        d = png()
        v = b.validar(d, b.Entrada(0, "a.png", len(d), False, None, None))
        assert v["crc_ok"] is None and v["ok"] is True

    def test_truncada_no_decodifica_con_load_aunque_verify_pudiera_aceptarla(self):
        d = png(64, 64)
        assert b.validar(d[: len(d) // 2], b.Entrada(0, "a.png", None, False, None, None))["decodifica"] is False


class TestClasificarSalida:

    @pytest.mark.parametrize("r,valida,esperado", [
        ({"rc": 0}, True, "OK_SIN_DANO_EN_LA_PAGINA"),
        ({"rc": 0}, False, "SILENCIOSO (rc 0 con página no válida)"),
        ({"rc": 2, "stderr": "Checksum failed"}, False, "ERROR_CLARO"),
        ({"rc": 2, "stderr": " "}, False, "ERROR_SIN_MENSAJE"),
        ({"rc": -11}, False, "CRASH (señal 11)"),
        ({"rc": 139}, False, "CRASH (señal 11)"),
        ({"rc": -9}, False, "OOM"),
        ({"rc": 1, "timeout": True}, False, "TIMEOUT"),
        ({"rc": -998}, False, "ERROR_DEL_BANCO"),
        ({"rc": -997}, False, "ERROR_DEL_BANCO"),
    ])
    def test_casos(self, r, valida, esperado):
        assert b.clasificar_salida(r, valida) == esperado

    def test_el_mensaje_puede_venir_por_la_salida_estandar(self):
        """En la Pi, `unar` falló con rc≠0 y stderr vacío: sus mensajes van por stdout."""
        assert b.clasificar_salida({"rc": 1, "stderr": "", "stdout_cabeza": "x.png: Failed! (Checksum error)"}, False) == "ERROR_CLARO"
        assert b.clasificar_salida({"rc": 1, "stderr": "", "stdout_cabeza": ""}, False) == "ERROR_SIN_MENSAJE"
        assert b.mensaje({"stderr": "", "stdout_cabeza": "texto"}) == "texto"

    def test_rc_0_sin_escribir_nada_no_es_exito(self):
        """Hallazgo de la prueba corta en la Pi: `unar` devuelve 0 cuando la entrada pedida no existe y no escribe nada."""
        assert b.clasificar_salida({"rc": 0}, valida=False, hay_datos=False).startswith("SIN_SALIDA_CON_RC_0")
        assert b.clasificar_salida({"rc": 0}, valida=False, hay_datos=False) not in b.ACEPTABLES

    def test_oom_del_cgroup_gana_a_un_error_normal(self):
        assert b.clasificar_salida({"rc": 2, "stderr": "x"}, False, oom=True) == "OOM"

    def test_solo_error_claro_sin_dano_y_nada_que_pedir_son_aceptables(self):
        assert b.ACEPTABLES == ("OK_SIN_DANO_EN_LA_PAGINA", "ERROR_CLARO", "SIN_PAGINA_QUE_PEDIR")

    def test_la_peor_de_varias_clases(self):
        assert b.peor(["OK_SIN_DANO_EN_LA_PAGINA", "ERROR_CLARO"]) == "ERROR_CLARO"
        assert b.peor(["ERROR_CLARO", "SILENCIOSO (rc 0 con página no válida)", "SIN_PAGINA_QUE_PEDIR"]).startswith("SILENCIOSO")
        assert b.peor(["SIN_SALIDA_CON_RC_0 (x)", "ERROR_SIN_MENSAJE"]).startswith("SIN_SALIDA")
        assert b.peor(["OK_SIN_DANO_EN_LA_PAGINA", "CRASH (señal 11)", "TIMEOUT"]).startswith("CRASH")


class TestDanos:

    def test_variantes_deterministas_y_dentro_del_fichero(self):
        v = b.variantes(1000)
        assert v == b.variantes(1000) and [x[0] for x in v] == ["truncado_50", "truncado_cabecera", "byte_cabecera", "byte_medio", "ceros_medio", "byte_final"]
        assert all(0 <= p <= 1000 for _, _, p in v)

    def test_cada_dano_cambia_la_copia_y_nunca_el_original(self, tmp_path):
        o = tmp_path / "o"
        o.write_bytes(bytes(range(256)) * 40)
        antes = o.read_bytes()
        for nombre, tipo, p in b.variantes(len(antes)):
            d = tmp_path / f"d_{nombre}"
            b.danar(o, d, tipo, p)
            assert d.read_bytes() != antes, nombre
            assert o.read_bytes() == antes
        assert (tmp_path / "d_truncado_50").stat().st_size == len(antes) // 2
        assert (tmp_path / "d_ceros_medio").read_bytes()[len(antes) // 2: len(antes) // 2 + 4096] == b"\0" * 4096


class TestDanoEnPagina:

    def test_la_comprimida_se_lee_del_listado(self):
        j = json.dumps({"lsarContents": [{"XADFileName": "a.png", "XADFileSize": 9, "XADCompressedSize": 5}]})
        assert b.parsear_lsar_json(j)[0][0].comprimido == 5

    def test_offset_cae_en_la_mitad_de_los_datos_de_esa_entrada(self):
        es = [b.Entrada(i, f"{i:02d}.png", 1000, False, None, None, comprimido=1000) for i in range(10)]
        for k in (0, 4, 9):
            o = b.offset_en_pagina(es, k)
            inicio = 20 + k * (64 + 6 + 1000) + 64 + 6              # ver la fórmula: cabecera estimada + nombre (6) + datos
            assert inicio <= o <= inicio + 1000                       # dentro de los datos de la entrada k
        assert b.offset_en_pagina(es, 5) > b.offset_en_pagina(es, 4)

    def test_el_dano_en_esa_posicion_cambia_los_bytes_de_esa_zona(self, tmp_path):
        es = [b.Entrada(i, f"{i:02d}.png", 100, False, None, None, comprimido=100) for i in range(5)]
        o = tmp_path / "o"
        o.write_bytes(bytes(range(256)) * 10)
        d = tmp_path / "d"
        pos = b.offset_en_pagina(es, 2)
        b.danar(o, d, "ceros", pos)
        assert d.read_bytes()[pos:pos + 100] == b"\0" * 100 and d.read_bytes()[:pos] == o.read_bytes()[:pos]


class TestEjecutar:
    """La mecánica que mide tiempo, límites y grupo de procesos, con órdenes de Python (sin las herramientas RAR)."""

    def test_salida_codigo_y_pico(self, tmp_path):
        r = b.ejecutar([sys.executable, "-c", "import sys;sys.stdout.write('x'*10);sys.stderr.write('aviso');sys.exit(3)"], stdout_a=str(tmp_path / "o"))
        assert (r["rc"], r["bytes_stdout"], r["stderr"], r["timeout"]) == (3, 10, "aviso", False) and r["pico_kib"] > 0
        assert (tmp_path / "o").read_bytes() == b"x" * 10

    def test_stdin_esta_cerrado_y_no_se_espera_contrasena(self):
        r = b.ejecutar([sys.executable, "-c", "import sys;sys.exit(0 if sys.stdin.read()=='' else 9)"], timeout=10)
        assert r["rc"] == 0 and not r["timeout"]

    def test_timeout_mata_tambien_a_los_nietos(self, tmp_path):
        marca = tmp_path / "vivo"
        nieto = f"import time,pathlib;time.sleep(2);pathlib.Path({str(marca)!r}).write_text('x')"
        padre = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{nieto!r}]);time.sleep(30)"
        r = b.ejecutar([sys.executable, "-c", padre], timeout=0.5)
        assert r["timeout"] is True
        import time
        time.sleep(2.5)
        assert not marca.exists()                         # el nieto murió con el grupo de procesos

    def test_tope_de_tamano_de_fichero_corta_la_escritura(self, tmp_path):
        destino = tmp_path / "grande"
        r = b.ejecutar([sys.executable, "-c", f"open({str(destino)!r},'wb').write(b'0'*200000)"], rlimits={"RLIMIT_FSIZE": 10000})
        assert r["rc"] != 0 and destino.stat().st_size <= 10000
