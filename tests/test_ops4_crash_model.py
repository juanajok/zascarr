"""Experimento abstracto de caída; no describe garantías de un disco real.

Se modela una sustitución de «aprobado» por «consumido». El archivo
anterior ya es estable y el temporal solo tiene contenido estable tras
fsync de archivo. Un rename sin fsync del directorio puede sobrevivir o
no al crash. No se modelan escrituras parciales ni otros fallos físicos.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

APPROVED = "aprobado"
CONSUMED = "consumido"
OPERATIONS = ("write", "fsync_file", "rename", "fsync_dir")


@dataclass
class SimulatedDisk:
    """Separar contenido y nombres volátiles de los confirmados en el modelo."""

    memory_temp: str | None = None
    disk_temp: str | None = None
    memory_target: str = APPROVED
    disk_target: str = APPROVED
    rename_pending: bool = False

    def apply(self, operation: str) -> None:
        if operation == "write":
            self.memory_temp = CONSUMED
        elif operation == "fsync_file":
            assert self.memory_temp is not None
            self.disk_temp = self.memory_temp
        elif operation == "rename":
            assert self.memory_temp is not None
            self.memory_target = self.memory_temp
            self.rename_pending = True
        elif operation == "fsync_dir":
            assert self.rename_pending and self.disk_temp is not None
            self.disk_target = self.disk_temp
            self.rename_pending = False
        else:
            raise AssertionError(operation)

    def crash(self) -> frozenset[str]:
        """Enumerar las recuperaciones admisibles, sin ejecutar E/S real."""
        if self.rename_pending:
            assert self.disk_temp is not None
            return frozenset((self.disk_target, self.disk_temp))
        return frozenset((self.disk_target,))


def hypothetical_gate(
    recovered: str, *, reconciled_since_boot: bool, new_approval: bool
) -> bool:
    """Hipótesis: reconciliar no convierte la aprobación anterior en una nueva."""
    return recovered == APPROVED and reconciled_since_boot and new_approval


def test_crash_en_cada_lado_de_cada_operacion_y_puertas_de_arranque() -> None:
    """Explorar todos los cortes y ambas resoluciones de rename pendiente."""
    expected = {
        0: frozenset((APPROVED,)),
        1: frozenset((APPROVED,)),
        2: frozenset((APPROVED,)),
        3: frozenset((APPROVED, CONSUMED)),
        4: frozenset((CONSUMED,)),
    }
    seen_cuts: set[int] = set()
    naive_reopens: set[tuple[str, str, str]] = set()
    for index, side in product(range(len(OPERATIONS)), ("antes", "despues")):
        cut = index + (side == "despues")
        model = SimulatedDisk()
        for operation in OPERATIONS[:cut]:
            model.apply(operation)
        outcomes = model.crash()
        assert outcomes == expected[cut], (OPERATIONS[index], side)
        seen_cuts.add(cut)
        for recovered in outcomes:
            # La operación ya se inició con aprobación y se consumió lógicamente;
            # confiar solo en el valor recuperado reabre una aprobación antigua.
            naive_gate_open = recovered == APPROVED
            if naive_gate_open:
                naive_reopens.add((OPERATIONS[index], side, recovered))
            # Solo expresa la regla hipotética: no prueba reconciliación ni nueva A reales.
            assert not hypothetical_gate(recovered, reconciled_since_boot=False, new_approval=False)
            assert not hypothetical_gate(recovered, reconciled_since_boot=True, new_approval=False)
            assert hypothetical_gate(
                recovered, reconciled_since_boot=True, new_approval=True
            ) == naive_gate_open
    assert seen_cuts == set(expected)
    assert ("rename", "despues", APPROVED) in naive_reopens
    assert ("fsync_dir", "antes", APPROVED) in naive_reopens
