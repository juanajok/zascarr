# ruff: noqa: E501, F811
"""#233 / BL-R4 sobre PostgreSQL y ficheros reales: el rescan NUNCA cambia una relación protegida.

Una relación `confirmada` (metadata.vinculo válido) o `manual_sin_comprobante` (manual sin comprobante)
no cambia ni se vacía: se actualizan bytes/hash/metadatos no relacionales y se registra la discrepancia
con el destino propuesto (incluida «ninguna publicación»). Una automática sí se re-tría como hasta
ahora. «Mantener lo mio» deja comprobante inmutable e es idempotente. Sin efectos en archivos.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from tests.test_rescan_biblioteca_pg import (  # noqa: F401  (fixtures/ayudas compartidas)
    _cbz,
    _filas,
    _n_runs,
    _rescan,
    _sembrar_issue,
    _serie_id,
    mundo,
    url_bd,
)
from zascarr.models import File, FileFormat, VinculacionOperacion
from zascarr.services.discrepancias import mantener_lo_mio
from zascarr.services.tokens_revision import MantenerFirmada, crear_token_mantener

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

SECRETO = "clave-de-prueba-para-mantener"
FECHA = "2026-11-09T00:00:00+00:00"


async def _crear_relacion(mundo, *, propuesto="02", actual="01", manual=True, con_vinculo=True,
                          existe_propuesta=True):
    """Una fila registrada con relación (protegida o automática) cuyo archivo, al re-tríarse, propone
    otra publicación. `file_mtime_ns=None` fuerza el re-triaje de la misma fila."""
    serie = await _serie_id(mundo, "Saga del Faro")
    issue_actual = await _sembrar_issue(mundo, "Saga del Faro", actual)
    issue_propuesto = None
    if existe_propuesta and propuesto != actual:
        issue_propuesto = await _sembrar_issue(mundo, "Saga del Faro", propuesto)
    ruta = mundo.lib / "Nuevos" / f"Saga del Faro {propuesto}.cbz"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    mundo.contenido[ruta] = _cbz(ruta, f"protegida-{propuesto}-{uuid4().hex[:6]}")
    meta = {"match_status": "direct", "ajuste_manual": "no-tocar"}
    if con_vinculo:
        meta["vinculo"] = {"version": 1, "operacion_id": str(uuid4()), "serie_id": str(serie),
                           "fecha": FECHA, "numero": actual, "formato": "single_issue"}
    async with mundo.fabrica() as s:
        fila = File(
            id=uuid4(), file_path=str(ruta), file_name=ruta.name, file_format=FileFormat.CBZ,
            file_size_bytes=1, sha256_hash=None, file_mtime_ns=None, issue_id=issue_actual,
            metadata_source="manual" if manual else "comicinfo_xml", metadata_=meta,
        )
        s.add(fila)
        await s.commit()
    return ruta, fila.id, issue_actual, issue_propuesto


def _discrepancias(fila) -> list[dict]:
    return (fila.metadata_ or {}).get("discrepancias") or []


async def test_confirmada_no_cambia_ni_se_vacia_y_deja_discrepancia(mundo):
    ruta, file_id, issue_actual, issue_propuesto = await _crear_relacion(mundo)
    bytes_antes = ruta.read_bytes()
    vinculo_antes = (await _filas(mundo))[str(ruta)].metadata_["vinculo"]
    informe = await _rescan(mundo)
    fila = (await _filas(mundo))[str(ruta)]
    assert str(fila.issue_id) == issue_actual                      # ni cambia ni se vacía
    assert fila.metadata_source == "manual"                        # no se toca la procedencia
    assert fila.metadata_["ajuste_manual"] == "no-tocar"
    assert fila.metadata_["vinculo"] == vinculo_antes
    assert fila.file_mtime_ns is not None and fila.sha256_hash is not None
    assert ruta.read_bytes() == bytes_antes                        # sin efectos en archivos
    assert informe.re_triados_protegidos == 1 and informe.discrepancias_registradas == 1
    (d,) = _discrepancias(fila)
    assert d["estado"] == "pendiente" and d["propuesta"]["issue_destino_uuid"] == str(issue_propuesto)
    assert d["propuesta"]["numero"] == "02" and d["relacion"]["issue_id"] == issue_actual
    # No se ha creado ni cambiado ningún Issue: la propuesta no se aplica.
    async with mundo.fabrica() as s:
        assert await _comprobantes_de(s, file_id) == 0


async def test_manual_sin_comprobante_tambien_se_protege(mundo):
    ruta, *_ = await _crear_relacion(mundo, con_vinculo=False)
    informe = await _rescan(mundo)
    fila = (await _filas(mundo))[str(ruta)]
    assert fila.issue_id is not None and fila.metadata_source == "manual"
    assert informe.re_triados_protegidos == 1
    assert _discrepancias(fila)[0]["relacion"]["operacion_id"] is None


async def test_automatica_si_se_re_tria_y_no_registra_discrepancia(mundo):
    ruta, file_id, issue_actual, issue_propuesto = await _crear_relacion(mundo, manual=False, con_vinculo=False)
    informe = await _rescan(mundo)
    fila = (await _filas(mundo))[str(ruta)]
    assert str(fila.issue_id) == issue_propuesto                    # la automática sí cambia
    assert _discrepancias(fila) == [] and informe.discrepancias_registradas == 0


async def test_ninguna_publicacion_tambien_es_una_discrepancia(mundo):
    ruta, file_id, issue_actual, _ = await _crear_relacion(mundo, propuesto="99", existe_propuesta=False)
    informe = await _rescan(mundo)
    fila = (await _filas(mundo))[str(ruta)]
    assert str(fila.issue_id) == issue_actual
    (d,) = _discrepancias(fila)
    assert d["propuesta"]["issue_destino_uuid"] is None
    assert d["propuesta"]["numero"] == "99" and d["estado"] == "pendiente"
    assert informe.re_triados_protegidos == 1


async def test_dedupe_y_repetir_el_rescan_no_duplica_ni_cambia(mundo):
    ruta, *_ = await _crear_relacion(mundo)
    await _rescan(mundo)
    fila1 = (await _filas(mundo))[str(ruta)]
    clave = _discrepancias(fila1)[0]["clave"]
    # Otros bytes, misma afirmación: el rescan vuelve a re-triar y debe reutilizar la entrada.
    _cbz(ruta, "otra-marca-sin-cambiar-la-afirmacion")
    await _rescan(mundo)
    fila2 = (await _filas(mundo))[str(ruta)]
    (d,) = _discrepancias(fila2)
    assert d["clave"] == clave and len(_discrepancias(fila2)) == 1
    assert fila1.id == fila2.id                                     # la MISMA fila


async def test_mantener_lo_mio_deja_comprobante_e_es_idempotente(mundo):
    ruta, file_id, issue_actual, issue_propuesto = await _crear_relacion(mundo)
    await _rescan(mundo)
    fila = (await _filas(mundo))[str(ruta)]
    (d,) = _discrepancias(fila)

    def token(*, operacion=None, relacion=None):
        rel = relacion or d["relacion"]
        return crear_token_mantener(MantenerFirmada(
            file_id=str(file_id), clave=d["clave"], issue_id=rel["issue_id"], serie_id=rel["serie_id"],
            vinculo_operacion=rel["operacion_id"] or "00000000-0000-0000-0000-000000000000",
            operacion=str(operacion or uuid4())), SECRETO)

    async with mundo.fabrica() as s:
        r = await mantener_lo_mio(s, token(), secret=SECRETO)
    assert r.resultado == "mantenida"
    fila = (await _filas(mundo))[str(ruta)]
    assert (fila.metadata_["discrepancias"][0]["estado"]) == "mantenida"
    assert str(fila.issue_id) == issue_actual and ruta.read_bytes()
    async with mundo.fabrica() as s:
        assert await _comprobantes_de(s, file_id) == 1

    # Mismo token (respuesta perdida) y token NUEVO de la misma clave: ambos idempotentes.
    async with mundo.fabrica() as s:
        assert (await mantener_lo_mio(s, token(), secret=SECRETO)).resultado == "ya_mantenida"
        nuevo = token()
        assert (await mantener_lo_mio(s, nuevo, secret=SECRETO)).resultado == "ya_mantenida"
        assert await _comprobantes_de(s, file_id) == 1

    # Otra relación (el vínculo cambió): no se puede mantener la propuesta vieja.
    otra = {"issue_id": issue_propuesto, "serie_id": d["relacion"]["serie_id"], "operacion_id": None}
    async with mundo.fabrica() as s:
        r = await mantener_lo_mio(s, token(relacion=otra), secret=SECRETO)
    assert r.resultado == "omitido" and r.motivo == "cambio_desde_la_vista_previa"
    assert (await _filas(mundo))[str(ruta)].metadata_["discrepancias"][0]["estado"] == "mantenida"


async def test_mutacion_quitar_el_guardian_cambiaria_el_vinculo(mundo, monkeypatch):
    """Prueba de mutación: si el guardián no protegiera, el MISMO rescan cambiaría la relación. Asegura
    que la prueba anterior mide el guardián y no otra cosa."""
    import zascarr.services.library_adopter as adopter
    monkeypatch.setattr(adopter, "es_protegida", lambda estado: False)
    ruta, file_id, issue_actual, issue_propuesto = await _crear_relacion(mundo)
    await _rescan(mundo)
    fila = (await _filas(mundo))[str(ruta)]
    # La mutación desactiva la protección: el vínculo sí cambia y no hay discrepancia.
    assert str(fila.issue_id) == issue_propuesto
    assert _discrepancias(fila) == []


async def test_el_informe_persiste_el_contador(mundo):
    await _crear_relacion(mundo)
    informe = await _rescan(mundo)
    assert informe.re_triados_protegidos == 1 and informe.discrepancias_registradas == 1
    async with mundo.fabrica() as s:
        details = (await s.execute(text(
            "SELECT details FROM import_runs WHERE details->>'kind' = 'rescan'"))).scalar_one()
    assert details["re_triados_protegidos"] == 1 and details["discrepancias_registradas"] == 1


async def _comprobantes_de(s, file_id) -> int:
    return (await s.execute(select(func.count()).select_from(VinculacionOperacion).where(
        VinculacionOperacion.resultado["file_id"].astext == str(file_id)))).scalar()
