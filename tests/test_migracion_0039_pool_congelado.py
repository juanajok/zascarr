"""OCTA-D1: la migración 0039 importa `services.etiquetas_iniciales`.

No se reescribe una migración aplicada. En su lugar, esta prueba congela el
contenido exacto que 0039 sembró: si alguien cambia el módulo sin una migración
nueva, la prueba falla antes de fusionar. Un cambio deliberado exige:
1) actualizar este hash en el mismo PR que añade la migración de datos; y
2) no tocar 0039.
"""
from __future__ import annotations

import hashlib

from zascarr.services.etiquetas_iniciales import ETIQUETAS_INICIALES

#: sha256 de "\n".join(ETIQUETAS_INICIALES) en el vocabulario que sembró 0039.
_HASH_0039 = "20b9733fc48d499ce00a6f9e553b8b179dcf0997984810536fef3e3f987f3657"
_TOTAL_0039 = 60


def test_el_pool_que_siembra_0039_no_cambia_sin_migracion_nueva():
    assert len(ETIQUETAS_INICIALES) == _TOTAL_0039
    datos = "\n".join(ETIQUETAS_INICIALES).encode("utf-8")
    assert hashlib.sha256(datos).hexdigest() == _HASH_0039
