"""Ayudas de pruebas para raíces de biblioteca (#156)."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from zascarr.config import get_settings
from zascarr.models import ComicTradition, LibraryRoot, LibraryRootTradition


async def sembrar_raiz(fabrica, path: Path, *, name: str = "Biblioteca", crear: bool = True) -> str:
    """Crea una raíz por defecto y todas las tradiciones; devuelve su id."""
    if crear:
        path.mkdir(parents=True, exist_ok=True)
    rid = uuid4()
    async with fabrica() as s:
        await s.execute(text("DELETE FROM library_root_traditions"))
        await s.execute(text("DELETE FROM library_roots"))
        s.add(LibraryRoot(id=rid, name=name, path=str(path), enabled=True, is_default=True))
        await s.flush()
        for tradicion in ComicTradition:
            s.add(LibraryRootTradition(root_id=rid, tradition=tradicion))
        await s.commit()
    return str(rid)


def allowlist(monkeypatch, path: Path) -> None:
    """Alinea settings con la raíz sembrada y limpia la caché de settings."""
    monkeypatch.setenv("LIBRARY_PATH", str(path))
    monkeypatch.setenv("LIBRARY_ROOTS", str(path))
    get_settings.cache_clear()
