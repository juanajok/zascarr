#!/usr/bin/env python3
# ruff: noqa: E501
"""Capturas de U16 (#203) a 390×844 (emulación táctil) contra el ensayo aislado: para REVISAR el aspecto tras los cambios (alto de los
controles, barra inferior, selector de la ficha). Reutiliza `Navegador` de `../ui-baseline/capturar.py`. No hace POST.

    python3 docs/design/ui-u16/capturar_u16.py http://127.0.0.1:18000 docs/design/ui-u16
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("capturar", Path(__file__).resolve().parents[1] / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capturar)


async def main(base: str, salida: Path) -> None:
    nav = capturar.Navegador()
    try:
        await nav.abrir()
        await nav.vista({"nombre": "m", "w": 390, "h": 844, "movil": True}, "light")
        await nav.ir(base + "/ui/biblioteca", espera=0.5)
        ficha = await nav.js("(() => { const a=[...document.querySelectorAll('a[href^=\"/ui/series/\"]')].find(x=>x.textContent.includes('Guardianes')); return a? a.getAttribute('href'):null })()")
        for nombre, ruta, tema in [("1-ficha-de-serie", ficha, "light"), ("2-por-revisar", "/ui/pendientes", "light"), ("3-ajustes", "/ui/ajustes", "light"),
                                   ("4-asistente-de-carpeta", "/ui/pendientes/carpetas/asistente?clave=_Unsorted", "dark"), ("5-aviso-legal-texto", "/legal", "light")]:
            await nav.vista({"nombre": "m", "w": 360 if nombre.startswith("5") else 390, "h": 844, "movil": True}, tema)
            await nav.ir(base + ruta, espera=0.8)
            await nav.foto(salida / f"{nombre}--movil.png", completa=False)
    finally:
        await nav.cerrar()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2])))
