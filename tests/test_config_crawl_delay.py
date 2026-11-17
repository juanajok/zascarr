"""M-4 — el tope de `Crawl-delay` vive en config con rango validado (O2 de QA)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from zascarr.config import Settings


def test_crawl_delay_max_s_acepta_los_extremos_del_rango():
    assert Settings(crawl_delay_max_s=5).crawl_delay_max_s == 5
    assert Settings(crawl_delay_max_s=300).crawl_delay_max_s == 300


@pytest.mark.parametrize("valor", [4, 301, 0, -1])
def test_crawl_delay_max_s_fuera_de_rango_no_valida(valor):
    with pytest.raises(ValidationError):
        Settings(crawl_delay_max_s=valor)
