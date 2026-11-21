# ruff: noqa: E402, F401, F811
"""UXA-09 (#1126): botón principal de lectura de la ficha de serie.

La regla es una función pura (`elegir_destino_de_serie`); aquí se prueba con los casos de la
historia: continuar, leer, tomo único, número perdido, lectura completa y varias ediciones.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from zascarr.models import ReadingStatus
from zascarr.services.lector import (
    CONTINUAR,
    ELEGIR,
    LEER,
    RELEER,
    ArchivoDeLectura,
    CandidatoDeLectura,
    DestinoDeSerie,
    elegir_destino_de_serie,
)

AHORA = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def _archivo(nombre="a.cbz"):
    return ArchivoDeLectura(str(uuid4()), nombre, "CBZ")


def _cand(numero, orden, estado=ReadingStatus.UNREAD, pagina=0, archivos=None,
          preferido=None, progreso=None, ultima=None):
    return CandidatoDeLectura(
        issue_id=f"issue-{numero}", numero=numero, orden=orden,
        archivos=archivos if archivos is not None else [_archivo(f"{numero}.cbz")],
        preferido=preferido, estado=estado, pagina=pagina,
        file_id_progreso=progreso, ultima_lectura=ultima)


def test_serie_sin_archivos_legibles_no_ofrece_lectura():
    assert elegir_destino_de_serie([]) is None


def test_continuar_gana_a_leer_cuando_hay_progreso_retomable():
    leyendo = _cand("3", 3.0, ReadingStatus.READING, pagina=7)
    destino = elegir_destino_de_serie([_cand("1", 1.0), _cand("2", 2.0), leyendo])
    assert destino.tipo == CONTINUAR
    assert (destino.issue_id, destino.pagina) == ("issue-3", 7)
    assert destino.archivo_id == str(leyendo.archivos[0].id)


def test_continuar_elige_la_lectura_mas_reciente():
    vieja = _cand("1", 1.0, ReadingStatus.READING, pagina=4, ultima=AHORA - timedelta(days=9))
    reciente = _cand("5", 5.0, ReadingStatus.READING, pagina=2, ultima=AHORA)
    sin_fecha = _cand("2", 2.0, ReadingStatus.READING, pagina=9)
    assert elegir_destino_de_serie([vieja, sin_fecha, reciente]).issue_id == "issue-5"


def test_leyendo_sin_pagina_no_es_retomable_y_se_ofrece_leer():
    destino = elegir_destino_de_serie([_cand("1", 1.0, ReadingStatus.READING, pagina=0)])
    assert destino.tipo == LEER and destino.pagina == 0


def test_leer_ofrece_el_primer_numero_sin_terminar_en_el_orden_de_la_serie():
    cands = [_cand("3", 3.0), _cand("1", 1.0, ReadingStatus.COMPLETED),
             _cand("2", 2.0, ReadingStatus.COMPLETED)]
    destino = elegir_destino_de_serie(cands)
    assert destino.tipo == LEER and destino.issue_id == "issue-3"


def test_numero_perdido_no_bloquea_el_destino():
    """Si el #2 no tiene archivo legible no está entre los candidatos: se ofrece el #3."""
    cands = [_cand("1", 1.0, ReadingStatus.COMPLETED), _cand("3", 3.0)]
    assert elegir_destino_de_serie(cands).issue_id == "issue-3"


def test_tomo_unico_ofrece_leer_sin_numero_en_la_cuenta():
    destino = elegir_destino_de_serie([_cand(None, None)])
    assert destino.tipo == LEER and destino.numero is None


def test_lectura_completa_ofrece_leer_de_nuevo_desde_el_primero():
    cands = [_cand("2", 2.0, ReadingStatus.COMPLETED), _cand("1", 1.0, ReadingStatus.COMPLETED)]
    destino = elegir_destino_de_serie(cands)
    assert destino.tipo == RELEER and destino.issue_id == "issue-1"


def test_numeros_sin_orden_van_al_final():
    cands = [_cand("X", None), _cand("1", 1.0)]
    assert elegir_destino_de_serie(cands).issue_id == "issue-1"


def test_varias_ediciones_con_preferida_abren_la_preferida():
    a, b = _archivo("a.cbz"), _archivo("b.cbz")
    destino = elegir_destino_de_serie([_cand("1", 1.0, archivos=[a, b], preferido=b.id)])
    assert destino.tipo == LEER and destino.archivo_id == str(b.id)


def test_varias_ediciones_con_progreso_reutilizan_el_archivo_del_progreso():
    a, b = _archivo("a.cbz"), _archivo("b.cbz")
    destino = elegir_destino_de_serie(
        [_cand("1", 1.0, ReadingStatus.READING, pagina=3, archivos=[a, b], progreso=b.id)])
    assert destino.tipo == CONTINUAR and destino.archivo_id == str(b.id)


def test_varias_ediciones_sin_preferida_ni_progreso_no_se_elige_por_la_persona():
    a, b = _archivo("a.cbz"), _archivo("b.cbz")
    destino = elegir_destino_de_serie([_cand("1", 1.0, archivos=[a, b])])
    assert destino.tipo == ELEGIR and destino.archivo_id is None
    assert destino.issue_id == "issue-1"


def test_preferida_que_ya_no_es_legible_cuenta_como_sin_desempate():
    a, b = _archivo("a.cbz"), _archivo("b.cbz")
    destino = elegir_destino_de_serie(
        [_cand("1", 1.0, archivos=[a, b], preferido=str(uuid4()))])
    assert destino.tipo == ELEGIR


# ── la ficha ──────────────────────────────────────────────────────────────────────────────

def _bloque(fuente, destino):
    """Renderiza aislado el botón de lectura y las acciones de la ficha (solo usan `series`)."""
    from jinja2 import Environment
    leer = fuente[fuente.index("{% if destino_lectura %}"):]
    leer = leer[:leer.index("{% endif %}\n    {#- «Completa»") + len("{% endif %}")]
    acciones = fuente[fuente.index('<p class="series-acciones">'):]
    acciones = acciones[:acciones.index("</p>") + 4]
    return Environment(autoescape=True).from_string(leer + acciones).render(
        series=type("S", (), {"id": "sid"})(), destino_lectura=destino)


@pytest.mark.parametrize("destino, esperado, no_esperado", [
    (DestinoDeSerie(CONTINUAR, "i", "12", "f1", 7), "Continuar el #12 (pág. 7)", "Leer el #12"),
    (DestinoDeSerie(LEER, "i", "1", "f1"), "Leer el #1", "Continuar"),
    (DestinoDeSerie(LEER, "i", None, "f1"), ">Leer<", "el #"),
    (DestinoDeSerie(RELEER, "i", "1", "f1"), "Leer de nuevo el #1", "Continuar"),
    (DestinoDeSerie(ELEGIR, "i", "4", None), "Elegir cómo leer el #4", "/ui/leer/"),
])
def test_plantilla_pinta_el_boton_segun_el_destino(destino, esperado, no_esperado):
    import re
    from pathlib import Path
    fuente = Path("src/zascarr/web/templates/series_detail.html").read_text()
    # El bloque de acciones se renderiza aislado: solo depende de `series`, `destino_lectura`.
    html = _bloque(fuente, destino)
    assert esperado in html, html
    assert no_esperado not in html, html
    assert len(re.findall(r'class="btn primary"', html)) == 1


def test_sin_destino_el_principal_es_anadir_numeros_del_disco():
    from pathlib import Path
    fuente = Path("src/zascarr/web/templates/series_detail.html").read_text()
    html = _bloque(fuente, None)
    assert 'class="btn primary" href="/ui/pendientes/carpetas?serie=sid">Añadir números' in html


# ── Postgres real: la consulta del servicio y la ficha completa ───────────────────────────

import os

from tests.test_asociar_fuente_b_pg import url_bd
from tests.test_vinculacion_previa_pg import cliente, entorno
from zascarr.models import File, FileFormat, Issue, ReadingProgress, Series
from zascarr.services.lector import destino_de_lectura_de_serie


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")
async def test_pg_destino_y_ficha_de_serie(entorno):
    sid, vacia = uuid4(), uuid4()
    i1, i2, i3 = uuid4(), uuid4(), uuid4()
    f1, f2, f3 = uuid4(), uuid4(), uuid4()
    async with entorno.banco.fabrica() as s:
        s.add_all([Series(id=sid, title="Con lectura"), Series(id=vacia, title="Vacia")])
        s.add_all([Issue(id=i1, series_id=sid, issue_number="1", volume=1, sort_order=1.0),
                   Issue(id=i2, series_id=sid, issue_number="2", volume=1, sort_order=2.0),
                   Issue(id=i3, series_id=sid, issue_number="3", volume=1, sort_order=3.0)])
        await s.flush()
        for iid, fid, nombre, perdido in ((i1, f1, "1.cbz", False), (i2, f2, "2.cbz", True),
                                          (i3, f3, "3.cbz", False)):
            s.add(File(id=fid, issue_id=iid, file_path=f"/tmp/{uuid4()}-{nombre}",
                       file_name=nombre, file_format=FileFormat.CBZ, metadata_={},
                       is_missing=perdido))
        await s.commit()

    async with entorno.banco.fabrica() as s:
        destino = await destino_de_lectura_de_serie(s, sid)
        # Sin progreso: «Leer» el primero; el #2 está perdido y no cuenta.
        assert (destino.tipo, destino.issue_id) == (LEER, str(i1))
        assert destino.archivo_id == str(f1)
        assert await destino_de_lectura_de_serie(s, vacia) is None

    async with entorno.banco.fabrica() as s:
        s.add(ReadingProgress(issue_id=i3, status=ReadingStatus.READING, current_page=5,
                              file_id=f3))
        s.add(ReadingProgress(issue_id=i1, status=ReadingStatus.COMPLETED, current_page=20))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        destino = await destino_de_lectura_de_serie(s, sid)
        assert (destino.tipo, destino.issue_id, destino.pagina) == (CONTINUAR, str(i3), 5)

    async with cliente() as c:
        con = await c.get(f"/ui/series/{sid}")
        assert con.status_code == 200
        assert f'href="/ui/leer/{f3}"' in con.text
        assert "Continuar el #3" in con.text
        sin = await c.get(f"/ui/series/{vacia}")
        assert sin.status_code == 200
        assert "/ui/leer/" not in sin.text
        assert 'class="btn primary" href="/ui/pendientes/carpetas?serie=' in sin.text
