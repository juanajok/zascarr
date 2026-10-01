"""
tests/test_compose_env.py

Deriva entre `.env.example`, `docker-compose.yml` y `Settings`.

El contenedor de ZascArr **no monta el `.env`**: solo ve las variables que el
compose declara en su `environment`. Con A6/E6 se documentó `BASE_URL` y
`ALLOWED_HOSTS` en `.env.example`, en `SECURITY.md` y en el changelog de 1.15.0
(«añádelo a `ALLOWED_HOSTS` en el `.env`»), pero el compose no las pasaba: poner
el valor en el `.env` no tenía ningún efecto. `ALLOWED_HOSTS` además no está en
Ajustes, así que quien entra por un nombre de equipo con `auth_mode=none` recibía
`403` en todo sin forma de arreglarlo desde la interfaz.

Regla que fija esta prueba: toda clave de `.env.example` que sea un campo de
`Settings` tiene que llegar al contenedor.
"""
from __future__ import annotations

import re
from pathlib import Path

from zascarr.config import Settings

RAIZ = Path(__file__).resolve().parents[1]


def _claves_de_env_example() -> list[str]:
    claves = []
    for linea in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#?\s*([A-Z][A-Z0-9_]+)=", linea)
        if m:
            claves.append(m.group(1))
    return list(dict.fromkeys(claves))


def _variables_del_servicio_zascarr() -> set[str]:
    """Nombres que el servicio `zascarr` recibe en su `environment` (forma
    `- NOMBRE=...`), sin depender de PyYAML (CLAUDE.md §2: sin dependencias
    nuevas por «testing»)."""
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    inicio = compose.index("\n  zascarr:\n")
    bloque = compose[inicio:]
    return set(re.findall(r"^\s+- ([A-Z][A-Z0-9_]+)=", bloque, re.M))


def test_la_prueba_ve_algo():
    """Guarda contra que una regex rota deje pasar todo en silencio."""
    assert "DB_PASSWORD" in _claves_de_env_example()
    assert "DATABASE_URL" in _variables_del_servicio_zascarr()


def test_toda_clave_de_settings_documentada_en_env_example_llega_al_contenedor():
    campos = {nombre.upper() for nombre in Settings.model_fields}
    llegan = _variables_del_servicio_zascarr()
    perdidas = [k for k in _claves_de_env_example() if k in campos and k not in llegan]
    assert not perdidas, (
        f"{perdidas} están en .env.example y son ajustes de la app, pero el compose "
        "no se las pasa al contenedor: poner el valor en el .env no tendría efecto"
    )


def test_base_url_y_allowed_hosts_llegan_al_contenedor():
    """El caso concreto que se rompió, con nombre propio."""
    llegan = _variables_del_servicio_zascarr()
    assert {"BASE_URL", "ALLOWED_HOSTS"} <= llegan
