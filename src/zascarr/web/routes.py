"""
Punto de encuentro de la UI web (/ui/*) — ver docs/adr/0001-ui-stack.md.

Ya no sirve la portada de /ui/ (antes un placeholder): esa la sirve
`web/dashboard.py`. Aquí quedan solo las piezas compartidas:

  - `TEMPLATES_DIR`: ruta absoluta a las plantillas, importada por todos los
    routers web (library, pendientes, wishlist, series, dashboard...).
  - `router`: el router raíz `/ui`, hoy sin endpoints propios.
"""
from pathlib import Path

from fastapi import APIRouter

TEMPLATES_DIR = Path(__file__).parent / "templates"

router = APIRouter(prefix="/ui", tags=["ui"])
