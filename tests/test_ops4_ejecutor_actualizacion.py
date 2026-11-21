"""Pruebas del ejecutor fijo; nunca lanzan update.sh real."""
from __future__ import annotations

import contextlib
import os
import select
import signal
import subprocess
import sys
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


def lanzar_python(code: str, timeout: float = 3) -> subprocess.CompletedProcess[bytes]:
    """Solo ejecuta procesos sintéticos, nunca el actualizador."""
    return ejecutor._lanzar_grupo(
        [sys.executable, "-c", code], timeout=timeout, check=False, shell=False,
        env={"PATH": ejecutor.PATH_FIJO}, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
    )


@pytest.mark.parametrize("code", [0, 9])
def test_grupo_real_conserva_codigo(code: int) -> None:
    result = lanzar_python(f"raise SystemExit({code})")
    assert result.returncode == code


def test_grupo_real_aisla_sesion(tmp_path: Path) -> None:
    path = tmp_path / "grupo"
    lanzar_python(
        f"import os; from pathlib import Path; "
        f"Path({str(path)!r}).write_text(f'{{os.getpid()}} {{os.getpgrp()}}')"
    )
    pid, group = map(int, path.read_text().split())
    assert pid == group
    assert group != os.getpgrp()


def test_timeout_real_mata_padre_e_hijo_que_ignora_sigterm(tmp_path: Path) -> None:
    path = tmp_path / "pids"
    code = (
        "import os,signal,time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "child = os.fork()\n"
        f"if child: Path({str(path)!r}).write_text(f'{{os.getpid()}} {{child}}')\n"
        "time.sleep(30)\n"
    )
    completed = False
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            lanzar_python(code, timeout=1)
        assert path.exists(), "el proceso sintético no llegó a crear el hijo"
        parent, child = map(int, path.read_text().split())
        # El padre ya fue recogido; el hijo puede ser zombi hasta que PID 1
        # lo recoja. Zombi no ejecuta código ni mantiene descriptores abiertos.
        assert not Path(f"/proc/{parent}").exists()
        try:
            child_fd = os.pidfd_open(child)
        except ProcessLookupError:
            pass  # PID 1 ya lo ha recogido.
        else:
            try:
                poller = select.poll()
                poller.register(child_fd, select.POLLIN)
                assert poller.poll(1000), "el descendiente sigue ejecutándose"
            finally:
                os.close(child_fd)
        completed = True
    finally:
        if not completed and path.exists():
            for pid in map(int, path.read_text().split()):
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)


def test_timeout_sintetico_integrado_se_clasifica_incierto() -> None:
    def lanzar(_orden, **kwargs):
        kwargs["timeout"] = 0.3
        return ejecutor._lanzar_grupo(
            [sys.executable, "-c", "import time; time.sleep(30)"], **kwargs,
        )

    assert ejecutor.ejecutar(
        ejecutor.construir_orden(), lanzar=lanzar,
    ) is ejecutor.ResultadoEjecucion.INCIERTO
