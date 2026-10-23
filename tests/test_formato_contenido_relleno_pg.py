# ruff: noqa: E501
"""#307 (D5) — relleno de `files.metadata["formato_contenido"]` en los `.cbr`/`.cb7` ya registrados, sobre Postgres REAL.

Lo que pidió la revisión de #325: que conserve las demás claves de `metadata` **también frente a escritores concurrentes**, que no reprocese las mismas
filas, que el lote esté acotado y que no escriba en los ficheros. Se saltan sin `TEST_DATABASE_URL`."""
from __future__ import annotations

import asyncio
import hashlib
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import File, FileFormat
from zascarr.services.importer import Importer

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

RAR5 = b"Rar!\x1a\x07\x01\x00" + b"\0" * 64


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    yield b
    await b.cerrar()


def un_zip(ruta: Path, paginas: int = 12) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        for i in range(paginas):
            z.writestr(f"p{i:03d}.jpg", b"x" * 100)
    return ruta


def huella(p: Path) -> tuple[str, int]:
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns


async def registrar(banco, ruta: Path, meta: dict | None = None, formato=FileFormat.CBR, ausente=False) -> UUID:
    fid = uuid4()
    async with banco.fabrica() as s:
        s.add(File(id=fid, file_path=str(ruta), file_name=ruta.name, file_format=formato, is_missing=ausente, metadata_=meta or {}))
        await s.commit()
    return fid


async def metadata_de(banco, fid: UUID) -> dict:
    async with banco.fabrica() as s:
        return (await s.execute(select(File.metadata_).where(File.id == fid))).scalar_one()


async def rellenar(banco, **kw) -> int:
    """Rellenadas en esta ejecución (el resultado completo, en `ejecutar`)."""
    return (await ejecutar(banco, **kw)).rellenadas


async def ejecutar(banco, **kw):
    async with banco.fabrica() as s:
        r = await Importer(s).rellenar_formato_contenido(**kw)
        await s.commit()
        return r


@pytest.fixture(autouse=True)
def _sin_ajustes_de_importer(monkeypatch):
    """`Importer.__init__` lee la configuración (rutas); aquí no hace falta nada de eso."""
    import zascarr.services.importer as mod
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(
        library_path=Path("/nada"), transmission_download_dir="/nada", amule_incoming_dir="/nada", downloads_path=Path("/nada")))


class TestRelleno:

    @pytest.mark.asyncio
    async def test_rellena_una_vez_conserva_las_demas_claves_y_no_toca_los_ficheros(self, banco, tmp_path):
        z, r = un_zip(tmp_path / "A.cbr"), tmp_path / "B.cbr"
        r.write_bytes(RAR5)
        antes = (huella(z), huella(r))
        a = await registrar(banco, z)
        b = await registrar(banco, r, meta={"match_status": "matched", "vinculo": {"operacion_id": "x", "n": 3}})
        assert await rellenar(banco) == 2
        assert await metadata_de(banco, a) == {"formato_contenido": {"firma": "zip", "contrato": 1, "clase": "tebeo"}}
        assert await metadata_de(banco, b) == {"match_status": "matched", "vinculo": {"operacion_id": "x", "n": 3},
                                               "formato_contenido": {"firma": "rar", "contrato": 1}}
        assert (huella(z), huella(r)) == antes
        assert await rellenar(banco) == 0                                      # idempotente: nada más que leer ni escribir

    @pytest.mark.asyncio
    async def test_una_fila_sin_metadata_nula_tambien_se_rellena(self, banco, tmp_path):
        fid = await registrar(banco, un_zip(tmp_path / "N.cbr"))
        async with banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = NULL WHERE id = :i"), {"i": fid})
            await s.commit()
        assert await rellenar(banco) == 1
        assert (await metadata_de(banco, fid))["formato_contenido"]["firma"] == "zip"

    @pytest.mark.asyncio
    async def test_solo_cbr_y_cb7_presentes_y_el_lote_esta_acotado(self, banco, tmp_path):
        for i in range(5):
            await registrar(banco, un_zip(tmp_path / f"{i}.cbr"))
        cbz = await registrar(banco, un_zip(tmp_path / "x.cbz"), formato=FileFormat.CBZ)
        falta = await registrar(banco, tmp_path / "falta.cbr", ausente=True)
        assert [await rellenar(banco, limite=2) for _ in range(4)] == [2, 2, 1, 0]
        assert await metadata_de(banco, cbz) == {} and await metadata_de(banco, falta) == {}

    @pytest.mark.asyncio
    async def test_un_fichero_ilegible_no_se_marca_y_se_reintenta(self, banco, tmp_path):
        ruta = tmp_path / "no_esta.cbr"
        fid = await registrar(banco, ruta)
        assert await rellenar(banco) == 0 and await metadata_de(banco, fid) == {}
        un_zip(ruta)                                                           # reaparece (p. ej. el disco vuelve a montarse)
        assert await rellenar(banco) == 1

    @pytest.mark.asyncio
    async def test_un_grupo_de_ilegibles_no_deja_sin_rellenar_al_resto(self, banco, tmp_path):
        """El lote se elige AL AZAR entre las pendientes: si fueran siempre las mismas, 6 ilegibles ocuparían el lote de 3 para siempre."""
        for i in range(6):
            await registrar(banco, tmp_path / f"roto{i}.cbr")                  # no existen: ilegibles
        buenos = [await registrar(banco, un_zip(tmp_path / f"ok{i}.cbr")) for i in range(3)]
        for _ in range(40):                                                    # con azar real, 40 intentos rellenan los 3 con probabilidad ≈ 1
            await rellenar(banco, limite=3)
        for b in buenos:
            assert "formato_contenido" in await metadata_de(banco, b)


class TestConcurrencia:

    @pytest.mark.asyncio
    async def test_un_escritor_que_cambia_metadata_entre_la_lectura_y_la_escritura_no_pierde_su_clave(self, banco, tmp_path):
        """La carrera que la versión anterior (leer el diccionario, añadir una clave, reescribirlo entero) perdía."""
        fid = await registrar(banco, un_zip(tmp_path / "C.cbr"), meta={"match_status": "unsorted"})
        async with banco.fabrica() as s:
            imp = Importer(s)
            candidatas = await imp._candidatas_formato(10)                     # el relleno ya ha leído la fila...
            async with banco.fabrica() as otro:                               # ...y OTRO proceso escribe una clave nueva (p. ej. un vínculo de BL-R1)
                await otro.execute(text("UPDATE files SET metadata = metadata || CAST(:j AS jsonb) WHERE id = :i"),
                                   {"j": '{"vinculo": {"operacion_id": "abc"}}', "i": fid})
                await otro.commit()
            formatos = [{"firma": "zip", "contrato": 1, "clase": "tebeo"}]
            assert await imp._aplicar_formato(candidatas, formatos) == 1       # ...y el relleno escribe después
            await s.commit()
        assert await metadata_de(banco, fid) == {"match_status": "unsorted", "vinculo": {"operacion_id": "abc"},
                                                 "formato_contenido": {"firma": "zip", "contrato": 1, "clase": "tebeo"}}

    @pytest.mark.asyncio
    async def test_dos_rellenos_solapados_no_se_pisan_ni_cuentan_doble(self, banco, tmp_path):
        ids = [await registrar(banco, un_zip(tmp_path / f"{i}.cbr")) for i in range(8)]
        r = await asyncio.gather(rellenar(banco, limite=8), rellenar(banco, limite=8))
        assert sum(r) == 8                                                     # cada fila se rellena exactamente una vez
        for fid in ids:
            assert (await metadata_de(banco, fid))["formato_contenido"]["clase"] == "tebeo"

    @pytest.mark.asyncio
    async def test_la_clave_ya_presente_no_se_sobrescribe(self, banco, tmp_path):
        fid = await registrar(banco, un_zip(tmp_path / "D.cbr"), meta={"formato_contenido": {"firma": "rar", "contrato": 1}})
        assert await rellenar(banco) == 0
        assert (await metadata_de(banco, fid))["formato_contenido"] == {"firma": "rar", "contrato": 1}


class TestOperacionADemanda:
    """D5 (PO, 2026-10-23): a demanda, acotada y con resultado identificable; sin automatismo."""

    @pytest.mark.asyncio
    async def test_el_resultado_es_identificable(self, banco, tmp_path):
        for i in range(3):
            await registrar(banco, un_zip(tmp_path / f"{i}.cbr"))
        for i in range(2):
            await registrar(banco, tmp_path / f"falta{i}.cbr")                       # ilegibles: no existen
        r = await ejecutar(banco, limite=10)
        assert (r.limite, r.pendientes_antes, r.leidas, r.rellenadas, r.ilegibles, r.pendientes_despues) == (10, 5, 5, 3, 2, 2)
        r2 = await ejecutar(banco, limite=10)                                         # los ilegibles siguen pendientes y se reintentan
        assert (r2.leidas, r2.rellenadas, r2.ilegibles, r2.pendientes_despues) == (2, 0, 2, 2)

    @pytest.mark.asyncio
    async def test_contar_pendientes_no_lee_ningun_fichero(self, banco, tmp_path, monkeypatch):
        await registrar(banco, un_zip(tmp_path / "a.cbr"))
        import zascarr.services.importer as mod
        monkeypatch.setattr(mod, "formato_real_de", lambda *a, **k: (_ for _ in ()).throw(AssertionError("leyó un fichero")))
        async with banco.fabrica() as s:
            assert await Importer(s).contar_pendientes_formato() == 1

    @pytest.mark.asyncio
    async def test_el_cli_por_defecto_solo_cuenta_y_no_escribe(self, banco, tmp_path, monkeypatch):
        from argparse import Namespace

        from zascarr.cli import rellenar_formato as cli
        monkeypatch.setattr(cli, "async_session_factory", banco.fabrica)
        fid = await registrar(banco, un_zip(tmp_path / "a.cbr"))
        res, codigo = await cli._ejecutar(Namespace(apply=False, limite=100, json=False))
        assert res == {"modo": "solo_cuenta", "pendientes": 1} and codigo == 0
        assert await metadata_de(banco, fid) == {}                                      # no escribió nada
        assert "No se ha leído ni escrito nada" in cli._texto(res)

    @pytest.mark.asyncio
    async def test_el_cli_con_apply_rellena_un_lote_y_el_codigo_de_salida_avisa_de_los_ilegibles(self, banco, tmp_path, monkeypatch):
        from argparse import Namespace

        from zascarr.cli import rellenar_formato as cli
        monkeypatch.setattr(cli, "async_session_factory", banco.fabrica)
        bueno = await registrar(banco, un_zip(tmp_path / "ok.cbr"))
        res, codigo = await cli._ejecutar(Namespace(apply=True, limite=100, json=False))
        assert res["modo"] == "aplicado" and res["rellenadas"] == 1 and res["ilegibles"] == 0 and codigo == 0
        assert "clase" in (await metadata_de(banco, bueno))["formato_contenido"]
        await registrar(banco, tmp_path / "no_esta.cbr")
        res2, codigo2 = await cli._ejecutar(Namespace(apply=True, limite=100, json=False))
        assert res2["ilegibles"] == 1 and res2["pendientes_despues"] == 1 and codigo2 == 1        # un cron no lo da por completo
        assert "ilegibles 1 (siguen pendientes)" in cli._texto(res2)

    def test_un_limite_invalido_se_rechaza_antes_de_tocar_nada(self):
        from zascarr.cli import rellenar_formato as cli
        assert cli.main(["--apply", "--limite", "0"]) == 2
