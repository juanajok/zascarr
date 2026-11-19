"""Pruebas sin Git, root ni Docker: solo utilidad pura y gate existente."""
from __future__ import annotations

import json

import pytest

from deploy.ops import validar_inventario_ops4 as politica

F = politica.Entrada("blob", 0o100644, "a" * 64)
N = politica.Entrada("blob", 0o100644, "b" * 64)
OTRO = politica.Entrada("blob", 0o100644, "c" * 64)
BASE = {
    "docker-compose.yml": F,
    "Dockerfile": F,
    "scripts/update.sh": F,
    "deploy/systemd/zascarr-ops@.service": F,
    "pyproject.toml": F,
    "alembic/versions/0001.py": F,
    "alembic/env.py": F,
    "src/zascarr/servicio.py": N,
}
ALLOWLIST = frozenset({"src/zascarr/servicio.py"})


def validar(candidato: dict[str, politica.Entrada]) -> str:
    return politica.validar_superficie(BASE, candidato, ALLOWLIST)


def test_identico_y_cambio_de_bytes_de_ruta_preaprobada() -> None:
    assert validar(BASE) == "conforme"
    assert validar({**BASE, "src/zascarr/servicio.py": OTRO}) == "conforme"


@pytest.mark.parametrize("ruta", [
    "docker-compose.yml", "Dockerfile", "scripts/update.sh",
    "deploy/systemd/zascarr-ops@.service", "pyproject.toml",
    "alembic/versions/0001.py", "alembic/env.py",
])
@pytest.mark.parametrize("cambio", ["modificar", "borrar", "modo"])
def test_protegidos_no_cambian(ruta: str, cambio: str) -> None:
    arbol = dict(BASE)
    if cambio == "borrar":
        del arbol[ruta]
    elif cambio == "modo":
        arbol[ruta] = politica.Entrada("blob", 0o100755, F.digest)
    else:
        arbol[ruta] = OTRO
    assert validar(arbol) == (
        "migracion_nueva" if ruta.startswith("alembic/") else "superficie_no_permitida"
    )


@pytest.mark.parametrize("ruta", [
    "scripts/otro.sh", "deploy/ops/otro.py", "alembic/versions/0002.py",
    "src/zascarr/otro.py", ".github/workflows/otro.yml",
])
def test_alta_ajena_o_nueva_se_rechaza(ruta: str) -> None:
    assert validar({**BASE, ruta: N}) != "conforme"


def test_ruta_permitida_no_puede_borrarse_cambiar_modo_ni_ser_enlace() -> None:
    arbol = dict(BASE)
    del arbol["src/zascarr/servicio.py"]
    assert validar(arbol) == "superficie_no_permitida"
    for entrada in (
        politica.Entrada("blob", 0o100755, N.digest),
        politica.Entrada("symlink", 0o120000, N.digest),
    ):
        assert validar({**BASE, "src/zascarr/servicio.py": entrada}) != "conforme"


@pytest.mark.parametrize("ruta", [
    "../scripts/a", "/scripts/a", "src//a", "src/./a", "src/../a",
    "src\\a", "src/a\nb", "-ruta", "src/\ud800/a",
])
def test_rutas_ambiguas_no_entran(ruta: str) -> None:
    assert validar({**BASE, ruta: N}) == "arbol_inseguro"


def test_allowlist_falta_o_es_autoautorizada_no_pasa() -> None:
    candidato = {**BASE, "src/zascarr/servicio.py": OTRO}
    assert politica.validar_superficie(BASE, candidato, frozenset()) == "superficie_no_permitida"
    assert politica.validar_superficie(
        BASE, candidato, frozenset({"src/zascarr/otro.py"})
    ) == "politica_invalida"
    assert politica.validar_superficie(
        BASE, candidato, frozenset({"Dockerfile"})
    ) == "politica_invalida"


def test_mapa_incompleto_no_se_detecta_sin_ancla_externa() -> None:
    """Límite explícito: dos mapas truncados iguales NO prueban P."""
    assert politica.validar_superficie({}, {}, frozenset()) == "conforme"


def test_gate_v3_sigue_cerrado() -> None:
    from deploy.ops import zascarr_ops
    assert "actualizar" not in zascarr_ops.UNIDADES
    assert zascarr_ops.parsear(
        json.dumps({"v": 3, "id": "e" * 32, "accion": "actualizar",
                    "sha": "a" * 40, "prueba": "secreto", "creada": 123,
                    "firma": "f" * 64}).encode() + b"\n"
    ) is None
