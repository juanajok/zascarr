"""Contratos de los enums de dominio migrados a `enum.StrEnum` (ruff UP042).

Diez son columnas de Postgres (`Enum(..., values_callable=lambda obj: [e.value for e in obj])`): la
BD guarda y compara el `.value`, nunca el nombre, así que la migración no toca el esquema ni los
datos. `DownloadBackend` (orquestador) no es columna. Estas pruebas fijan lo que NO puede cambiar
(los valores, que son los tipos de Postgres de las migraciones) y documentan lo que sí cambia frente
a `(str, enum.Enum)`: `str(miembro)` y las f-strings devuelven el valor (`"manga"`) y no el nombre
cualificado (`"ComicTradition.MANGA"`). Auditado: el código siempre usa `.value` para formatear y
ninguna plantilla ni prueba dependía del nombre cualificado. Mismo patrón que
`test_formato_enums_strenum.py` (#307).
"""

import enum as pyenum
import json

import pytest
from sqlalchemy import Enum as SAEnum

from zascarr.models import (
    AsignacionEstado,
    Base,
    ComicTradition,
    CreatorRole,
    FileFormat,
    IssueFormat,
    MetadataSource,
    ReadingStatus,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.orchestrator import DownloadBackend

MIEMBROS = {
    ComicTradition: {
        "AMERICAN": "american",
        "FRANCO_BELGIAN": "franco_belgian",
        "MANGA": "manga",
        "TEBEO": "tebeo",
        "FUMETTI": "fumetti",
        "MANHWA": "manhwa",
        "MANHUA": "manhua",
        "BRITISH": "british",
        "OTHER": "other",
    },
    CreatorRole: {
        "WRITER": "writer",
        "PENCILER": "penciler",
        "INKER": "inker",
        "COLORIST": "colorist",
        "LETTERER": "letterer",
        "COVER_ARTIST": "cover_artist",
        "EDITOR": "editor",
        "TRANSLATOR": "translator",
    },
    IssueFormat: {
        "SINGLE_ISSUE": "single_issue",
        "TRADE_PAPERBACK": "trade_paperback",
        "HARDCOVER": "hardcover",
        "OMNIBUS": "omnibus",
        "GRAPHIC_NOVEL": "graphic_novel",
        "ALBUM": "album",
        "MANGA_TANKOBON": "manga_tankobon",
        "DIGITAL": "digital",
    },
    FileFormat: {"CBZ": "cbz", "CBR": "cbr", "CB7": "cb7", "PDF": "pdf", "EPUB": "epub"},
    WishlistStatus: {
        "WANTED": "wanted",
        "SEARCHING": "searching",
        "DOWNLOADING": "downloading",
        "DOWNLOADED": "downloaded",
        "IMPORTED": "imported",
        "FAILED": "failed",
        "RETIRADO": "retirado",
    },
    WishlistPolicy: {
        "NONE": "ninguno",
        "MISSING": "faltantes",
        "FUTURE": "futuros",
        "ALL": "todos",
    },
    WishlistOrigin: {"MANUAL": "manual", "POLICY": "politica"},
    ReadingStatus: {
        "UNREAD": "unread",
        "READING": "reading",
        "COMPLETED": "completed",
        "ON_HOLD": "on_hold",
        "DROPPED": "dropped",
    },
    MetadataSource: {
        "COMIC_VINE": "comic_vine",
        "GCD": "gcd",
        "ANILIST": "anilist",
        "TEBEOSFERA": "tebeosfera",
        "COMICINFO_XML": "comicinfo_xml",
        "MANUAL": "manual",
    },
    AsignacionEstado: {
        "PREPARADA": "preparada",
        "CONFIRMADA": "confirmada",
        "LIMPIADA": "limpiada",
        "CANCELADA": "cancelada",
    },
    DownloadBackend: {"TRANSMISSION": "transmission", "AMULE": "amule"},
}


@pytest.mark.parametrize("tipo", MIEMBROS)
def test_es_strenum(tipo):
    assert issubclass(tipo, pyenum.StrEnum)


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_value_no_cambia(tipo, miembros):
    assert {m.name: m.value for m in tipo} == miembros


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_construccion_desde_valor_e_identidad(tipo, miembros):
    for nombre, valor in miembros.items():
        assert tipo(valor) is getattr(tipo, nombre)


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_str_y_fstring_devuelven_el_valor(tipo, miembros):
    # Diferencia aceptada: antes `str(ComicTradition.MANGA)` era "ComicTradition.MANGA".
    for nombre, valor in miembros.items():
        miembro = getattr(tipo, nombre)
        assert str(miembro) == valor
        assert f"{miembro}" == valor


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_comparacion_hash_y_json_con_texto(tipo, miembros):
    for nombre, valor in miembros.items():
        miembro = getattr(tipo, nombre)
        assert miembro == valor
        assert {valor: "ok"}[miembro] == "ok"
        assert json.dumps(miembro) == json.dumps(valor)


def _columnas_enum():
    for tabla in Base.metadata.tables.values():
        for col in tabla.columns:
            if isinstance(col.type, SAEnum) and col.type.enum_class in MIEMBROS:
                yield f"{tabla.name}.{col.name}", col.type


def test_hay_columnas_enum_que_comprobar():
    assert len(list(_columnas_enum())) >= 10


@pytest.mark.parametrize(
    "columna,tipo_sa", list(_columnas_enum()), ids=lambda x: x if isinstance(x, str) else ""
)
def test_la_columna_guarda_los_valores_y_no_los_nombres(columna, tipo_sa):
    """Regresión del mecanismo que haría daño: sin `values_callable`, SQLAlchemy guarda el NOMBRE
    (`MANGA`) y los tipos de Postgres de las migraciones tienen el valor (`manga`)."""
    assert list(tipo_sa.enums) == [m.value for m in tipo_sa.enum_class], columna
