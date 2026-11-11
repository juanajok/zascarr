"""#340/BL-WK2: estado derivado y decisión «no completar» (puro)."""
from __future__ import annotations

from uuid import uuid4

from zascarr.models import ComicTradition, MetadataSource, Series, WishlistPolicy
from zascarr.services.coleccion import (
    COMPLETA,
    FALTAN,
    NO_CALCULABLE,
    NO_COMPLETAR,
    conflicto_con_politica,
    decision_no_completar,
    estado_puro,
    marcar_no_completar,
    revertir_no_completar,
)


def _serie(total=5, fuente=MetadataSource.COMIC_VINE.value, policy=WishlistPolicy.NONE) -> Series:
    return Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                  total_issues=total, metadata_source=fuente, wishlist_policy=policy,
                  metadata_={})


def test_completa_cuando_no_falta_ninguno():
    estado = estado_puro(_serie(total=2), {1, 2})
    assert estado.tipo == COMPLETA and not estado.faltantes and estado.etiqueta == "Completa"


def test_faltan_n_cuando_es_computable():
    estado = estado_puro(_serie(total=5), {1, 2})
    assert estado.tipo == FALTAN and estado.faltantes == (3, 4, 5)
    assert estado.etiqueta == "Te faltan 3"


def test_no_calculable_sin_total_o_sin_unidad_de_grapa():
    assert estado_puro(_serie(total=None), set()).tipo == NO_CALCULABLE
    anilist = estado_puro(_serie(total=20, fuente=MetadataSource.ANILIST.value), set())
    assert anilist.tipo == NO_CALCULABLE and "grapas" in (anilist.motivo or "")


def test_no_completar_prevalece_y_es_reversible():
    serie = _serie(total=5, policy=WishlistPolicy.MISSING)
    marcar_no_completar(serie)
    assert decision_no_completar(serie)
    assert estado_puro(serie, set()).tipo == NO_COMPLETAR
    assert serie.metadata_["coleccion"]["version"] == 1
    assert serie.metadata_["coleccion"]["actualizado_en"]
    assert serie.wishlist_policy == WishlistPolicy.MISSING

    revertir_no_completar(serie)
    assert not decision_no_completar(serie)
    assert estado_puro(serie, set()).tipo == FALTAN
    assert serie.wishlist_policy == WishlistPolicy.MISSING


def test_marcar_conserva_otra_metadata():
    serie = _serie()
    serie.metadata_ = {"otra": {"x": 1}}
    marcar_no_completar(serie)
    assert serie.metadata_["otra"] == {"x": 1}
    assert serie.metadata_["coleccion"]["no_completar"] is True


def test_conflicto_d8_solo_si_la_politica_busca_faltantes_y_no_esta_decidido():
    assert conflicto_con_politica(_serie(policy=WishlistPolicy.MISSING))
    assert conflicto_con_politica(_serie(policy=WishlistPolicy.ALL))
    assert not conflicto_con_politica(_serie(policy=WishlistPolicy.NONE))
    serie = _serie(policy=WishlistPolicy.MISSING)
    marcar_no_completar(serie)
    assert not conflicto_con_politica(serie)
