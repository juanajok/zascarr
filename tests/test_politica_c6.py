"""C6 (PR 2): funciones puras de la cota y del motivo de «no calculable».

Sin base de datos: son las piezas que deciden qué se le dice a la persona
(FR-09/10/11/13), y conviene fijarlas con casos de frontera.
"""

from __future__ import annotations

from uuid import uuid4

from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.enricher import puede_enlazarse_con_comic_vine
from zascarr.services.politica import horas_minimas, texto_de_cota
from zascarr.services.series import MOTIVO_SIN_TOTAL, razon_de_no_calculable


def make_series(**kwargs) -> Series:
    datos = {
        "id": uuid4(),
        "title": "Serie",
        "tradition": ComicTradition.AMERICAN,
        "total_issues": 3,
        "metadata_source": MetadataSource.COMIC_VINE.value,
    }
    datos.update(kwargs)
    return Series(**datos)


class TestHorasMinimas:
    def test_redondea_hacia_arriba(self):
        assert horas_minimas(1, 2) == 1
        assert horas_minimas(3, 2) == 2
        assert horas_minimas(96, 2) == 48
        assert horas_minimas(97, 2) == 49

    def test_sin_pendientes_es_cero(self):
        assert horas_minimas(0, 2) == 0


class TestTextoCota:
    def test_una_hora(self):
        assert texto_de_cota(1) == "una hora"

    def test_horas(self):
        assert texto_de_cota(2) == "unas 2 horas"
        assert texto_de_cota(48) == "unas 48 horas"

    def test_dias_hacia_abajo(self):
        """H=49 son 2 días y unas horas: decir «3 días» afirmaría un mínimo falso."""
        assert texto_de_cota(49) == "unos 2 días"
        assert texto_de_cota(96) == "unos 4 días"


class TestRazonDeNoCalculable:
    def test_sin_total_issues(self):
        razon = razon_de_no_calculable(make_series(total_issues=None))
        assert razon is not None
        assert razon.motivo == MOTIVO_SIN_TOTAL
        assert razon.fuente is None

    def test_fuente_con_nombre_publico(self):
        razon = razon_de_no_calculable(
            make_series(total_issues=120, metadata_source=MetadataSource.ANILIST.value)
        )
        assert razon is not None
        assert "viene de AniList" in razon.motivo
        assert razon.fuente == "anilist"

    def test_manual(self):
        razon = razon_de_no_calculable(
            make_series(total_issues=120, metadata_source=MetadataSource.MANUAL.value)
        )
        assert razon is not None
        assert "alta a mano" in razon.motivo
        assert razon.fuente == "manual"

    def test_fuente_desconocida(self):
        razon = razon_de_no_calculable(make_series(total_issues=120, metadata_source="fuente-rara"))
        assert razon is not None
        assert "(sin fuente)" in razon.motivo
        assert razon.fuente is None

    def test_comic_vine_si_es_calculable(self):
        assert razon_de_no_calculable(make_series(total_issues=120)) is None


class TestPuedeEnlazarseConComicVine:
    def test_condicion_completa(self):
        series = make_series(metadata_source=None)
        assert puede_enlazarse_con_comic_vine(series, comic_vine_activo=True)

    def test_no_si_ya_tiene_identidad_o_es_manual(self):
        assert not puede_enlazarse_con_comic_vine(
            make_series(metadata_source=None, comic_vine_id=7), comic_vine_activo=True
        )
        assert not puede_enlazarse_con_comic_vine(
            make_series(metadata_source=MetadataSource.MANUAL.value), comic_vine_activo=True
        )

    def test_no_si_la_fuente_esta_apagada_o_la_tradicion_no_es_de_comic_vine(self):
        assert not puede_enlazarse_con_comic_vine(
            make_series(metadata_source=None), comic_vine_activo=False
        )
        assert not puede_enlazarse_con_comic_vine(
            make_series(metadata_source=None, tradition=ComicTradition.MANGA),
            comic_vine_activo=True,
        )
