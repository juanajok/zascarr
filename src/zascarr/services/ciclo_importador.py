# ruff: noqa: E501
"""Ciclo del importador compartido por el bucle automático y la acción manual (#232).

Es el mismo camino de siempre: sesión propia → `scan_and_import` → commit → aviso opcional.
`disparador` viaja al `ImportReport` para que el `ImportRun` distinga manual de automático
sin migración. El aviso sigue yendo DESPUÉS del commit y solo con archivos nuevos.
"""
from __future__ import annotations

from zascarr.services.importer import ImportReport


async def ejecutar_ciclo_y_avisar(notifier, session_factory, importer_cls, *,
                                  disparador: str = "automatico") -> ImportReport:
    """Ejecuta el ciclo y devuelve su informe ya confirmado.

    El `ImportRun` se persiste dentro de `scan_and_import` y se confirma con el mismo commit.
    Si el commit falla, la excepción se propaga y no se avisa.
    """
    async with session_factory() as session:
        kwargs = {} if disparador == "automatico" else {"disparador": disparador}
        report = await importer_cls(session).scan_and_import(**kwargs)
        await session.commit()
    if report.imported:
        await notifier.notify_imported(report.imported)
    return report
