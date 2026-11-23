"""#827: la caché de CBR se ajusta también si Docker crea el bind al arrancar.

El arreglo original quedó en un commit posterior a la fusión de #1056 y no
llegó a `main`. Esta prueba fija el contrato: `update.sh` ajusta el bind antes
de `up -d` y lo vuelve a ajustar después, por si Docker lo creó como root.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
UPDATE = RAIZ / "scripts" / "update.sh"

CHOWN = '"${PUID:-1000}:${PGID:-1000}" "${DATA_DIR}/lector"'
CHMOD = 'chmod 750 "${DATA_DIR}/lector"'
ARRANQUE = '"${COMPOSE[@]}" up -d --remove-orphans zascarr'


def test_ajusta_permisos_del_lector_antes_y_despues_de_arrancar():
    texto = UPDATE.read_text(encoding="utf-8")

    assert texto.count(CHOWN) == 2
    assert texto.count(CHMOD) == 2
    assert texto.index(CHOWN) < texto.index(ARRANQUE) < texto.rindex(CHOWN)
    assert texto.index(CHMOD) < texto.index(ARRANQUE) < texto.rindex(CHMOD)
