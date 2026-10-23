# ruff: noqa: E501
"""#307 — ¿qué recorrido existe de verdad para que ZascArr incorpore un fichero que el usuario arregla o vuelve a descargar? Importador REAL sobre
Postgres real y ficheros sintéticos. Es la verificación que pidió UX antes de poner en un aviso «prueba a descargarlo de nuevo» o «déjalo en tu
carpeta de descargas»: (a) ¿lo recorre el importador?; (b) ¿entra aunque el dañado siga en la biblioteca?; (c) ¿adónde va? Se saltan sin `TEST_DATABASE_URL`."""
from __future__ import annotations

import hashlib
import io
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, File, FileFormat, Issue, IssueFormat, Series
from zascarr.services import importer as mod
from zascarr.services.importer import Importer

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def _jpeg(i: int) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (200, 300), (i * 20 % 255, 90, 160)).save(b, "JPEG")
    return b.getvalue()


def un_zip(ruta: Path, paginas: int = 12) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        for i in range(paginas):
            z.writestr(f"p{i:03d}.jpg", _jpeg(i))
    return ruta


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def ent(url_bd, tmp_path, monkeypatch):
    b = Banco(url_bd)
    await b.limpiar()
    lib, descargas = tmp_path / "biblioteca", tmp_path / "descargas"
    lib.mkdir()
    descargas.mkdir()
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(
        library_path=lib, transmission_download_dir=str(tmp_path / "transmission"), amule_incoming_dir=str(tmp_path / "amule"), downloads_path=descargas))
    yield SimpleNamespace(banco=b, lib=lib, descargas=descargas)
    await b.cerrar()


async def serie_con_numero(ent, titulo="Flash", anio=1987, numero="23") -> tuple:
    async with ent.banco.fabrica() as s:
        serie = Series(id=uuid4(), title=titulo, start_year=anio, tradition=ComicTradition.AMERICAN)
        s.add(serie)
        await s.flush()
        issue = Issue(series_id=serie.id, issue_number=numero, format=IssueFormat.SINGLE_ISSUE)
        s.add(issue)
        await s.commit()
        return serie.id, issue.id


async def importar(ent):
    async with ent.banco.fabrica() as s:
        informe = await Importer(s).scan_and_import()
        await s.commit()
        return informe


async def filas(ent) -> list[File]:
    async with ent.banco.fabrica() as s:
        return list((await s.execute(select(File).order_by(File.file_name))).scalars().all())


class TestDescargarDeNuevoUnDanado:                                                          # (a) (b) (c)

    @pytest.mark.asyncio
    async def test_la_copia_buena_entra_aunque_el_danado_siga_en_la_biblioteca_y_va_a_su_serie(self, ent):
        _serie, issue = await serie_con_numero(ent)
        roto = ent.lib / "Comics" / "Flash (1987)" / "Flash 023.cbz"
        roto.parent.mkdir(parents=True)
        roto.write_bytes(b"PK\x03\x04 esto es una descarga incompleta")
        async with ent.banco.fabrica() as s:
            s.add(File(id=uuid4(), issue_id=issue, file_path=str(roto), file_name=roto.name, file_format=FileFormat.CBZ, sha256_hash=None,
                       metadata_={"match_status": "matched"}))
            await s.commit()
        antes = roto.read_bytes()
        nueva = un_zip(ent.descargas / "Flash 023 (1987).cbz")                                  # (a) la carpeta de descargas que recorre el importador
        huella = sha(nueva)

        informe = await importar(ent)

        todas = await filas(ent)
        assert len(todas) == 2 and not informe.errors                                          # (b) entra una fila nueva; no se confunde con el dañado
        nuevo = next(f for f in todas if f.sha256_hash == huella)
        assert not nueva.exists() and Path(nuevo.file_path).exists() and Path(nuevo.file_path).is_relative_to(ent.lib)    # el importador MUEVE la copia buena a la biblioteca
        assert roto.read_bytes() == antes                                                       # el dañado no se toca, ni se borra, ni se sustituye
        assert nuevo.metadata_.get("match_status") != "unsorted" and nuevo.issue_id == issue    # (c) a su serie y número
        assert "_Unsorted" not in nuevo.file_path

    @pytest.mark.asyncio
    async def test_sin_serie_conocida_va_a_por_revisar(self, ent):
        nueva = un_zip(ent.descargas / "Tebeo Raro 07.cbz")
        informe = await importar(ent)
        (f,) = await filas(ent)
        assert len(informe.unsorted) == 1 and "_Unsorted" in f.file_path and f.metadata_["match_status"] == "unsorted" and not nueva.exists()

    @pytest.mark.asyncio
    async def test_un_rar_dañado_o_no_es_un_tebeo_arreglado_fuera(self, ent):
        """El hash de un fichero que NO se pudo leer es `None`, así que no choca con ninguna otra fila."""
        roto = ent.lib / "Flash 023.cbz"
        roto.write_bytes(b"basura que no es ningun contenedor")
        async with ent.banco.fabrica() as s:
            s.add(File(id=uuid4(), file_path=str(roto), file_name=roto.name, file_format=FileFormat.CBZ, sha256_hash=None, metadata_={}))
            await s.commit()
        un_zip(ent.descargas / "Flash 023.cbz")
        await importar(ent)
        assert len(await filas(ent)) == 2


class TestDejarloEnLaCarpetaDeDescargas:                                                     # la línea propuesta para la cabecera de «No reconocidos»

    @pytest.mark.asyncio
    async def test_un_zip_sin_extension_en_la_biblioteca_no_se_registra_pero_su_copia_renombrada_en_descargas_si(self, ent):
        original = un_zip(ent.lib / "Comics" / "Barrio")                                         # el caso real: un ZIP sin extensión DENTRO de la biblioteca
        antes = (original.read_bytes(), original.stat().st_mtime_ns)
        copia = ent.descargas / "Barrio 01.cbz"
        copia.write_bytes(original.read_bytes())                                                # «cambiarle el nombre» a una COPIA y dejarla en descargas

        await importar(ent)

        (f,) = await filas(ent)
        assert f.file_name == "Barrio 01.cbz" and not copia.exists() and Path(f.file_path).is_relative_to(ent.lib)
        assert (original.read_bytes(), original.stat().st_mtime_ns) == antes                    # el original sigue ahí: ahora hay DOS copias en disco
        assert not [x for x in await filas(ent) if x.file_path == str(original)]                # y el original sigue sin estar registrado

    @pytest.mark.asyncio
    async def test_un_fichero_sin_extension_dejado_en_descargas_no_se_importa(self, ent):
        un_zip(ent.descargas / "Barrio")
        await importar(ent)
        assert await filas(ent) == []

    @pytest.mark.asyncio
    async def test_una_copia_de_un_fichero_ya_registrado_se_descarta_y_se_queda_en_descargas(self, ent):
        """Si el fichero arreglado es idéntico a uno ya registrado, el importador lo descarta como duplicado y NO lo borra ni lo mueve."""
        registrado = un_zip(ent.lib / "Comics" / "X 01.cbz")
        async with ent.banco.fabrica() as s:
            s.add(File(id=uuid4(), file_path=str(registrado), file_name=registrado.name, file_format=FileFormat.CBZ, sha256_hash=sha(registrado), metadata_={}))
            await s.commit()
        copia = ent.descargas / "X 01 copia.cbz"
        copia.write_bytes(registrado.read_bytes())
        informe = await importar(ent)
        assert len(informe.duplicates) == 1 and copia.exists() and len(await filas(ent)) == 1

    @pytest.mark.asyncio
    async def test_un_pack_descomprimido_en_descargas_se_importa_numero_a_numero(self, ent):
        """«lo descomprimes»: los números que salen del pack (`.cbz` dentro de subcarpetas) los recorre el importador (recursivo) y los mueve a la biblioteca."""
        pack = ent.lib / "Comics" / "Pack Completo.zip"
        pack.parent.mkdir(parents=True)
        with zipfile.ZipFile(pack, "w", zipfile.ZIP_STORED) as z:
            for n in (1, 2):
                tmp = un_zip(ent.descargas.parent / f"_t{n}.cbz", paginas=3 + n)
                z.write(tmp, f"Serie/Serie {n:02d}.cbz")
        with zipfile.ZipFile(pack) as z:
            z.extractall(ent.descargas)                                                     # lo que haría el usuario con otro programa
        await importar(ent)
        nombres = sorted(f.file_name for f in await filas(ent))
        assert nombres == ["Serie 01.cbz", "Serie 02.cbz"] and not list(ent.descargas.rglob("*.cbz"))
        assert pack.exists()                                                                # el pack original sigue donde estaba
