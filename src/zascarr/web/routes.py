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
from fastapi.templating import Jinja2Templates

from zascarr.config import get_settings
from zascarr.services.primeros_pasos import fecha_llana
from zascarr.web.componentes import registrar as registrar_componentes
from zascarr.web.descubrir_texto import etiqueta_procedencia, pista_de_tradicion

TEMPLATES_DIR = Path(__file__).parent / "templates"

router = APIRouter(prefix="/ui", tags=["ui"])


def crear_templates() -> Jinja2Templates:
    """Cada router web crea su propia instancia de Jinja2Templates (11 y
    contando) — cada una es un Environment independiente, así que un
    global registrado en una no se ve en las demás. Esta fábrica evita
    tener que repetir el registro a mano en cada fichero.

    `auth_activo` (A6): `base.html` lo usa para mostrar u ocultar
    "Cerrar sesión" en el nav sin que cada router tenga que acordarse de
    meter `auth_mode` en su propio contexto de plantilla."""
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["auth_activo"] = lambda: get_settings().auth_mode != "none"
    # #276: la pista de tradición se atribuye según su procedencia y se usa en Descubrir y en el
    # asistente. Se registran como filtros (no como globales) para no ampliar el contexto de todas
    # las plantillas.
    templates.env.filters["pista_de_tradicion"] = pista_de_tradicion
    templates.env.filters["etiqueta_procedencia"] = etiqueta_procedencia
    # Fechas legibles sin depender del locale del sistema (la Pi puede no tener es_ES).
    templates.env.filters["fecha_llana"] = fecha_llana
    # V2: macros de componentes (chip, aviso, grupo…) disponibles en TODAS las plantillas.
    registrar_componentes(templates.env)
    return templates
