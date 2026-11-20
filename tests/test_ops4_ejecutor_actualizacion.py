"""Pruebas del ejecutor fijo; nunca lanzan update.sh real."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from deploy.ops import ejecutor_actualizar_ops4 as ejecutor

REPO = Path("/opt/zascarr/zascarr")


class Lanzador:
    def __init__(self, returncode=0, *, error=None) -> None:
        self.returncode = returncode
        self.error = error
        self.llamadas: list[tuple] = []

    def __call__(self, orden, **kwargs):
        self.llamadas.append((orden, kwargs))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(orden, self.returncode, b"", b"")


def test_orden_fija() -> None:
    orden = ejecutor.construir_orden()
    assert orden == ("/bin/bash", str(REPO / "scripts/update.sh"), "--rama", "main")
    assert isinstance(orden, tuple)


def test_no_acepta_sh_ni_argumentos_libres() -> None:
    # La API no recibe rama, ruta ni lista de argumentos.
    with pytest.raises(TypeError):
        ejecutor.construir_orden("main")  # type: ignore[call-arg]


def test_lanzamiento_correcto_sin_declarar_salud() -> None:
    lanzador = Lanzador(0)
    resultado = ejecutor.ejecutar(ejecutor.construir_orden(), lanzar=lanzador)
    assert resultado is ejecutor.ResultadoEjecucion.TERMINADO
    orden, kwargs = lanzador.llamadas[0]
    assert orden[0] == "/bin/bash"
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["env"] == {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


@pytest.mark.parametrize("returncode", [1, 2, 75])
def test_codigo_no_cero_es_fallido(returncode: int) -> None:
    assert ejecutor.ejecutar(
        ejecutor.construir_orden(), lanzar=Lanzador(returncode)
    ) is ejecutor.ResultadoEjecucion.FALLIDO


def test_timeout_es_incierto() -> None:
    class Timeout(Lanzador):
        def __call__(self, orden, **kwargs):
            raise subprocess.TimeoutExpired(orden, 1)

    assert ejecutor.ejecutar(
        ejecutor.construir_orden(), lanzar=Timeout()
    ) is ejecutor.ResultadoEjecucion.INCIERTO


@pytest.mark.parametrize("error", [OSError("no existe"), RuntimeError("raro")])
def test_excepcion_es_incierta(error: Exception) -> None:
    assert ejecutor.ejecutar(
        ejecutor.construir_orden(), lanzar=Lanzador(error=error)
    ) is ejecutor.ResultadoEjecucion.INCIERTO


def test_orden_invalida_no_lanza() -> None:
    lanzador = Lanzador(0)
    assert ejecutor.ejecutar([], lanzar=lanzador) is ejecutor.ResultadoEjecucion.INCIERTO
    assert lanzador.llamadas == []
