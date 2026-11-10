"""BL-INF6 (#592): elegir la portada de la serie (servicio, sin BD real)."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from zascarr.models import ComicTradition, Series
from zascarr.services import portada_serie


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    """Sesión mínima: devuelve las filas declaradas, en orden (cola estricta)."""

    def __init__(self, resultados):
        self._resultados = list(resultados)
        self.consultas = 0

    async def execute(self, *_a, **_k):
        self.consultas += 1
        return _Resultado(self._resultados.pop(0))


def _settings(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(covers_cache_path=tmp_path / "covers")


def _series(**extra) -> Series:
    serie = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                   metadata_source="comic_vine")
    for clave, valor in extra.items():
        setattr(serie, clave, valor)
    return serie


def _externa(tmp_path, serie, *, ancho: int = 600) -> Path:
    from PIL import Image
    ruta = tmp_path / "covers" / "externa" / f"{serie.id}.jpg"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (ancho, ancho * 2), (10, 90, 160)).save(ruta, "JPEG")
    return ruta


def _fila_numero(numero: str) -> tuple[UUID, str]:
    return (uuid4(), numero)


@pytest.mark.asyncio
async def test_candidatas_lista_los_numeros_con_archivo_y_la_externa(tmp_path):
    serie = _series(cover_url="https://comicvine.gamespot.com/a/x.jpg")
    _externa(tmp_path, serie)
    numeros = [_fila_numero(str(n)) for n in range(1, 14)]      # 13: la tanda es de 12
    filas_archivos = [(issue_id, uuid4(), f"/b/{numero}.cbz", None)
                      for issue_id, numero in numeros]
    sesion = _Sesion([numeros[:13], filas_archivos])

    candidatas = await portada_serie.candidatas_de_portada(
        sesion, serie, settings=_settings(tmp_path))

    assert [c.origen for c in candidatas.numeros[:2]] == [
        "Del archivo del nº 1", "Del archivo del nº 2"]
    assert len(candidatas.numeros) == 12
    assert candidatas.hay_mas is True
    assert candidatas.externa is not None
    assert candidatas.externa.tipo == "externa"
    assert candidatas.externa.miniatura.endswith(f"/ui/series/{serie.id}/portada/externa.jpg")
    assert candidatas.externa.url == serie.cover_url
    assert candidatas.numeros[0].miniatura == (
        f"/ui/series/{serie.id}/numero/{numeros[0][0]}/previa.jpg")
    assert candidatas.hay_portada_actual is True


@pytest.mark.asyncio
async def test_candidatas_sin_archivos_y_sin_externa_no_hay_portada_actual(tmp_path):
    serie = _series(cover_url=None)
    filas = await portada_serie.candidatas_de_portada(
        _Sesion([[], []]), serie, settings=_settings(tmp_path))
    assert filas.numeros == () and filas.externa is None and filas.hay_mas is False
    assert filas.hay_portada_actual is False


@pytest.mark.asyncio
async def test_la_externa_no_se_ofrece_si_es_la_imagen_de_relleno(tmp_path):
    serie = _series(
        cover_url="https://comicvine.gamespot.com/a/uploads/scale_medium/1/2/6373148-blank.png")
    _externa(tmp_path, serie)
    filas = await portada_serie.candidatas_de_portada(
        _Sesion([[], []]), serie, settings=_settings(tmp_path))
    assert filas.externa is None


@pytest.mark.asyncio
async def test_un_numero_cuyo_archivo_no_puede_dar_portada_no_se_ofrece(tmp_path):
    """Un archivo con `formato_contenido` que dice que no es un tebeo no pinta una miniatura que
    el navegador pediría para recibir un 404."""
    serie = _series()
    issue_id = uuid4()
    sesion = _Sesion([
        [(issue_id, "1")],
        [(issue_id, uuid4(), "/b/roto.cbz", {"firma": "otro", "clase": None})],
    ])
    candidatas = await portada_serie.candidatas_de_portada(
        sesion, serie, settings=_settings(tmp_path))
    assert candidatas.numeros == ()


@pytest.mark.asyncio
async def test_la_segunda_tanda_no_repite_la_externa_y_desplaza_el_orden(tmp_path):
    serie = _series(cover_url="https://example.com/x.jpg")
    _externa(tmp_path, serie)
    numeros = [_fila_numero(str(n)) for n in range(1, 14)]
    sesion = _Sesion([numeros[12:], [(numeros[12][0], uuid4(), "/b/13.cbz", None)]])
    candidatas = await portada_serie.candidatas_de_portada(
        sesion, serie, desde=12, settings=_settings(tmp_path))
    assert [c.origen for c in candidatas.numeros] == ["Del archivo del nº 13"]
    assert candidatas.externa is None
    assert candidatas.hay_mas is False


def test_guardar_eleccion_de_archivo_persiste_y_protege_cover_url():
    serie = _series(metadata_={"alta": {"origen": "manual"}}, locked_fields=["title"])
    file_id = uuid4()
    antes = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    portada_serie.guardar_eleccion(serie, tipo=portada_serie.TIPO_ARCHIVO,
                                   file_id=file_id, ahora=antes)

    assert serie.metadata_["portada"] == {
        "tipo": "archivo", "file_id": str(file_id), "fecha": antes.isoformat()}
    assert serie.metadata_["alta"] == {"origen": "manual"}      # el resto del JSONB se conserva
    assert serie.locked_fields == ["title", "cover_url"]
    # Idempotente: no duplica el campo protegido.
    portada_serie.guardar_eleccion(serie, tipo=portada_serie.TIPO_ARCHIVO,
                                   file_id=file_id, ahora=antes)
    assert serie.locked_fields == ["title", "cover_url"]


def test_guardar_eleccion_externa():
    serie = _series(metadata_={}, locked_fields=[])
    portada_serie.guardar_eleccion(serie, tipo=portada_serie.TIPO_EXTERNA,
                                   url="https://example.com/portada.jpg")
    assert serie.metadata_["portada"]["tipo"] == "externa"
    assert serie.metadata_["portada"]["url"] == "https://example.com/portada.jpg"
    assert "fecha" in serie.metadata_["portada"]
    assert "cover_url" in serie.locked_fields


@pytest.mark.parametrize("tipo,extra", [
    ("archivo", {}),
    ("externa", {}),
    ("inventado", {"file_id": uuid4()}),
])
def test_guardar_eleccion_rechaza_lo_incompleto(tipo, extra):
    serie = _series(metadata_={}, locked_fields=[])
    with pytest.raises(ValueError):
        portada_serie.guardar_eleccion(serie, tipo=tipo, **extra)


@pytest.mark.parametrize("portada", [
    {"tipo": "archivo", "file_id": "no-es-un-uuid", "fecha": "2026-11-10T10:00:00+00:00"},
    {"tipo": "archivo", "file_id": str(uuid4()), "fecha": "no-es-fecha"},
    {"tipo": "externa", "url": "", "fecha": "2026-11-10T10:00:00+00:00"},
    {"tipo": "raro", "fecha": "2026-11-10T10:00:00+00:00"},
    {"tipo": "archivo", "file_id": str(uuid4())},
    "no-es-un-dict",
])
def test_eleccion_de_portada_ignora_metadatos_invalidos(portada):
    serie = _series(metadata_={"portada": portada})
    assert portada_serie.eleccion_de_portada(serie) is None


def test_eleccion_de_portada_valida():
    file_id = uuid4()
    serie = _series(metadata_={"portada": {
        "tipo": "archivo", "file_id": str(file_id),
        "fecha": "2026-11-10T10:00:00+00:00"}})
    assert portada_serie.eleccion_de_portada(serie)["file_id"] == str(file_id)
    assert portada_serie.eleccion_de_portada(_series(metadata_=None)) is None


def test_quitar_eleccion_borra_la_clave_y_el_lock():
    file_id = uuid4()
    serie = _series(
        metadata_={"alta": {"origen": "manual"},
                   "portada": {"tipo": "archivo", "file_id": str(file_id),
                               "fecha": "2026-11-10T10:00:00+00:00"}},
        locked_fields=["title", "cover_url"])
    assert portada_serie.quitar_eleccion(serie) is True
    assert "portada" not in serie.metadata_
    assert serie.metadata_["alta"] == {"origen": "manual"}     # el resto del JSONB no se toca
    assert serie.locked_fields == ["title"]
    # Sin elección, no hay nada que quitar (y no reescribe la serie).
    assert portada_serie.quitar_eleccion(serie) is False


@pytest.mark.asyncio
async def test_archivos_de_numero_pone_primero_el_pedido():
    """El archivo que la persona vio en la miniatura se intenta primero; el resto queda de
    respaldo (un CBZ roto no impide usar el otro archivo del mismo número)."""
    serie = _series()
    issue_id = uuid4()
    primero, segundo = uuid4(), uuid4()
    sesion = _Sesion([[(primero, "/b/1.cbz", None), (segundo, "/b/2.cbz", None)]])
    archivos = await portada_serie.archivos_de_numero(
        sesion, serie.id, issue_id, file_id=segundo)
    assert [a[0] for a in archivos] == [segundo, primero]
    # La consulta pide por la serie y el número: un issue de otra serie no devuelve nada.
    assert sesion.consultas == 1


@pytest.mark.asyncio
async def test_archivo_de_portada_incluye_el_mtime_guardado():
    serie = _series()
    file_id = uuid4()
    sesion = _Sesion([[(file_id, "/b/1.cbz", None, 123456)]])
    filas = await portada_serie.archivo_de_portada(sesion, serie.id, file_id)
    assert filas == [(file_id, "/b/1.cbz", None, 123456)]


def test_el_origen_del_numero_en_llano():
    assert portada_serie._origen_del_numero("3") == "Del archivo del nº 3"
    assert portada_serie._origen_del_numero(None) == "Del archivo de un número sin número"
    assert portada_serie._origen_del_numero("  ") == "Del archivo de un número sin número"
