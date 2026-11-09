# ruff: noqa: E501
"""#530 R1: el script de la imagen exige que la limpieza de trixie no deje herramientas y que sigan
las excepciones de runtime. Se prueba la función pura con un `which` inyectado."""
from __future__ import annotations

import importlib.util
from pathlib import Path

RUTA = Path(__file__).resolve().parents[1] / "scripts" / "comprobar_imagen_rar.py"
spec = importlib.util.spec_from_file_location("comprobar_imagen_rar", RUTA)
comprobar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comprobar)


def _which(presentes: set[str]):
    """Simula `shutil.which`: devuelve ruta si está en `presentes`, si no `None`."""
    return lambda nombre: (f"/usr/bin/{nombre}" if nombre in presentes else None)


def _presentes() -> set[str]:
    return set(comprobar.HERRAMIENTAS_QUE_DEBEN_ESTAR)


def test_todo_limpio_y_excepciones_presentes_pasa():
    assert comprobar.problemas_de_herramientas(_which(_presentes())) == []


def test_una_herramienta_de_trixie_que_sigue_es_rojo():
    for nombre in ("make", "patch", "dot", "gnutls-cli", "certtool", "as", "ld", "ar",
                   "corelist", "cpan", "prove", "perlbug", "dpkg-buildpackage", "dpkg-shlibdeps"):
        problemas = comprobar.problemas_de_herramientas(_which(_presentes() | {nombre}))
        assert any(f"sigue en la imagen: {nombre}" in p for p in problemas), nombre


def test_una_excepcion_de_runtime_que_falta_es_rojo():
    for nombre in ("dpkg-architecture", "perl", "dpkg", "lsar", "unar"):
        problemas = comprobar.problemas_de_herramientas(_which(_presentes() - {nombre}))
        assert any(f"falta en la imagen: {nombre}" in p for p in problemas), nombre


def test_las_listas_cubren_lo_que_pide_la_condicion():
    assert set(comprobar.HERRAMIENTAS_QUE_NO_DEBEN_ESTAR) >= {
        "gnutls-cli", "gnutls-serv", "certtool", "make", "patch", "dpkg-buildpackage",
        "dpkg-shlibdeps", "dot", "as", "ld", "ar", "corelist", "cpan", "prove", "perlbug"}
    assert set(comprobar.HERRAMIENTAS_QUE_DEBEN_ESTAR) == {"dpkg-architecture", "perl", "dpkg", "lsar", "unar"}
