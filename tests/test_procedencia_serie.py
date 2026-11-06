"""MIT-M6-US01 (#127): procedencia y protección por campo, sin inventar origen."""
from __future__ import annotations

from uuid import uuid4

from zascarr.models import MetadataSource, Series
from zascarr.services.procedencia import CAMPOS_GESTIONADOS, procedencia_de_serie


def serie(**kw) -> Series:
    datos = {
        "id": uuid4(), "title": "Thorgal", "start_year": 1977,
        "description": "Una serie de aventuras.", "cover_url": "https://example.invalid/c.jpg",
        "total_issues": 5, "metadata_": {}, "metadata_source": None, "locked_fields": [],
    }
    datos.update(kw)
    return Series(**datos)


def por_clave(proc):
    return {c.clave: c for c in proc.campos}


def test_sin_procedencia_no_atribuye_nada():
    proc = procedencia_de_serie(serie(metadata_={}, metadata_source=None))
    assert proc.hay_datos is False
    assert "No hay procedencia registrada" in proc.resumen
    assert all(c.origen is None for c in proc.campos)
    assert not any(c.manual for c in proc.campos)


def test_alta_manual_es_manual_y_con_fecha():
    proc = procedencia_de_serie(serie(
        metadata_={"alta": {"origen": "manual", "fuente": None,
                            "fecha": "2026-11-06T10:00:00+00:00"}},
        metadata_source=MetadataSource.MANUAL.value,
    ))
    campos = por_clave(proc)
    assert campos["title"].origen == "Introducido a mano"
    assert campos["title"].manual is True
    assert campos["total_issues"].manual is True
    assert "2026-11-06" in proc.resumen


def test_alta_desde_fuente_atribuye_solo_los_campos_del_alta():
    proc = procedencia_de_serie(serie(
        metadata_={"alta": {"origen": "descubrir", "fuente": "comic_vine", "id_externo": "777",
                            "fecha": "2026-11-06T10:00:00+00:00"}},
        metadata_source=MetadataSource.COMIC_VINE.value,
        comic_vine_id=777,
    ))
    campos = por_clave(proc)
    assert campos["title"].origen == "Alta desde Comic Vine"
    assert campos["start_year"].origen == "Alta desde Comic Vine"
    assert campos["identidad"].origen == "Alta desde Comic Vine"
    assert campos["identidad"].valor == "Identificador registrado"
    assert campos["total_issues"].origen == "Enriquecido desde Comic Vine"
    assert campos["title"].manual is False


def test_enriquecimiento_sin_alta_no_atribuye_titulo_ni_ano():
    proc = procedencia_de_serie(serie(metadata_source=MetadataSource.ANILIST.value, anilist_id=42))
    campos = por_clave(proc)
    assert campos["description"].origen == "Enriquecido desde AniList"
    assert campos["identidad"].origen == "Enriquecido desde AniList"
    assert campos["title"].origen is None
    assert campos["start_year"].origen is None


def test_campo_bloqueado_se_marca_y_no_expone_el_id():
    proc = procedencia_de_serie(serie(
        metadata_source=MetadataSource.COMIC_VINE.value, comic_vine_id=777,
        locked_fields=["comic_vine_id", "description"],
    ))
    campos = por_clave(proc)
    assert campos["identidad"].bloqueado is True
    assert campos["description"].bloqueado is True
    assert "Protegido: el enriquecimiento no lo sobrescribe." in campos["identidad"].observaciones
    assert "777" not in " ".join(c.valor for c in proc.campos)


def test_bloqueo_sin_procedencia_es_dato_visible_sin_origen_inventado():
    proc = procedencia_de_serie(serie(locked_fields=["description"]))
    campo = por_clave(proc)["description"]
    assert campo.bloqueado is True
    assert campo.origen is None
    assert proc.hay_datos is True


def test_los_campos_son_los_del_contrato_y_en_orden():
    proc = procedencia_de_serie(serie())
    assert [c.clave for c in proc.campos] == [c[0] for c in CAMPOS_GESTIONADOS]


def test_la_sinopsis_larga_se_recorta_y_la_portada_no_muestra_url():
    proc = procedencia_de_serie(serie(description="x" * 400, cover_url="https://example.invalid/p.jpg"))
    campos = por_clave(proc)
    assert len(campos["description"].valor) <= 160
    assert campos["cover_url"].valor == "Portada guardada"
    assert "example.invalid" not in campos["cover_url"].valor


def test_si_todos_los_campos_tienen_origen_el_resumen_no_dice_algunos():
    proc = procedencia_de_serie(serie(
        metadata_source=MetadataSource.COMIC_VINE.value, comic_vine_id=777,
        metadata_={"alta": {"origen": "descubrir", "fuente": "comic_vine",
                            "id_externo": "777", "fecha": "2026-11-06T10:00:00+00:00"}},
    ))
    assert all(c.origen is not None for c in proc.campos)
    assert "todos los datos visibles" in proc.resumen
    assert "algunos datos" not in proc.resumen
