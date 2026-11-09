"""Bloqueo compartido por `File.id` para quien escribe `metadata_` o la relación del archivo.

Tagger ya serializa la escritura del CBZ por `File.id`; el rescan, «Mantener lo mío» y la
asignación manual también releen y escriben `metadata_`/`issue_id`, así que tienen que usar
**la misma** clave de advisory lock. Si cada uno usara la suya, dos escritores podrían leer la
misma fila y el último commit pisaría `mantenida`, `discrepancias` o el vínculo.

La clave es la misma que usaba `services/tagger.py` (blake2b de 64 bits del UUID, con signo)
para no cambiar el bloqueo ya probado del etiquetador. Es `pg_advisory_xact_lock`: se suelta
con el COMMIT/ROLLBACK de la transacción que lo pide, sin `unlock` explícito.
"""
from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Espacio lógico del advisory lock (la clave numérica ya identifica el archivo).
ESPACIO = "file_id:"


def clave_de_fichero(file_id) -> int:
    """Clave de 64 bits estable a partir del UUID del `File` (misma que usa el tagger)."""
    return int.from_bytes(
        hashlib.blake2b(uuid.UUID(str(file_id)).bytes, digest_size=8).digest(),
        "big", signed=True,
    )


async def bloquear_archivo(db: AsyncSession, file_id) -> None:
    """Toma el advisory lock de ESTE archivo en la transacción de `db`.

    Debe llamarse **antes** de leer la fila que se va a modificar y mantenerse hasta el
    COMMIT: así la relectura ve lo último y nadie escribe entre la lectura y la escritura.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(:clave)"),
                     {"clave": clave_de_fichero(file_id)})
