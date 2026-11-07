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


def test_la_app_corre_con_no_new_privileges_y_pids_limit():
    """#418 (ADR 0015, SecOps A-1): el contenedor que abre archivos de terceros con `unar` no puede ganar
    privilegios ni bifurcarse sin tope."""
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    servicio = compose[compose.index("\n  zascarr:\n"):]
    siguiente = re.search(r"\n  [a-z_-]+:\n", servicio[3:])
    if siguiente:
        servicio = servicio[: siguiente.start() + 3]
    assert re.search(r"security_opt:\s*\n\s*- no-new-privileges:true", servicio)
    # `pids_limit` y `deploy.resources.limits` no pueden convivir en este Compose: el tope va en `limits.pids`
    assert re.search(r"limits:\s*\n(?:\s+\w+: .*\n)*?\s+pids:\s*\d+", servicio)


def test_el_dockerfile_borra_los_demonios_de_gnustep_y_solo_instala_unar_en_runtime():
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile[dockerfile.index("AS runtime"):]
    assert "unar" in runtime and "unar" not in dockerfile[: dockerfile.index("AS runtime")].replace("`unar`", "")
    for demonio in ("gdomap", "gdnc", "gpbs"):
        assert demonio in runtime and "-delete" in runtime
