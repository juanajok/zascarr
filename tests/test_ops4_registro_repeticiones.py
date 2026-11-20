"""Registro antirrepetición sobre directorios temporales; sin auxiliar ni Docker."""
from __future__ import annotations

import concurrent.futures
import errno
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from deploy.ops import protocolo_actualizar_ops4 as protocolo
from deploy.ops import registro_repeticiones_ops4 as registro
from deploy.ops.admision_actualizar_ops4 import CodigoAdmision, admitir

ID = "a" * 32


@pytest.fixture
def directory_fd(tmp_path: Path):
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield fd
    finally:
        os.close(fd)


def test_reclamacion_real_persiste_y_no_contiene_secretos(tmp_path: Path, directory_fd) -> None:
    assert registro.reclamar_id(ID, directorio_fd=directory_fd) is True
    marker = tmp_path / f"solicitud-{ID}"
    assert marker.read_bytes() == b""
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    assert registro.reclamar_id(ID, directorio_fd=directory_fd) is False
    os.fstat(directory_fd)  # El descriptor del llamador sigue abierto.


def test_orden_de_sincronizacion_fichero_luego_directorio(directory_fd) -> None:
    calls = []

    def sync(fd):
        calls.append(stat.S_IFMT(os.fstat(fd).st_mode))
        os.fsync(fd)

    assert registro.reclamar_id(ID, directorio_fd=directory_fd, sincronizar=sync)
    assert calls == [stat.S_IFREG, stat.S_IFDIR]


@pytest.mark.parametrize("failed_call", [1, 2])
def test_fallo_fsync_no_autoriza_ni_borra_marca(directory_fd, failed_call: int) -> None:
    calls = 0

    def sync(fd):
        nonlocal calls
        calls += 1
        if calls == failed_call:
            raise OSError(errno.EIO, "dato sensible no debe propagarse")
        os.fsync(fd)

    with pytest.raises(registro.RegistroNoDisponibleError) as error:
        registro.reclamar_id(ID, directorio_fd=directory_fd, sincronizar=sync)
    assert "sensible" not in str(error.value)
    assert registro.reclamar_id(ID, directorio_fd=directory_fd) is False


def test_callback_que_no_acredita_sync_deniega(directory_fd) -> None:
    with pytest.raises(registro.RegistroNoDisponibleError):
        registro.reclamar_id(ID, directorio_fd=directory_fd, sincronizar=lambda _: False)
    assert registro.reclamar_id(ID, directorio_fd=directory_fd) is False


@pytest.mark.parametrize("bad", [None, True, "../escape", "A" * 32, "a" * 31, "a" * 33])
def test_id_invalido_no_crea_nada(tmp_path: Path, directory_fd, bad) -> None:
    with pytest.raises(registro.RegistroNoDisponibleError):
        registro.reclamar_id(bad, directorio_fd=directory_fd)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_nombre_existente_siempre_consumido_sin_seguirlo(
    tmp_path: Path, directory_fd, kind: str,
) -> None:
    marker = tmp_path / f"solicitud-{ID}"
    if kind == "symlink":
        marker.symlink_to(tmp_path / "no-crear")
    elif kind == "fifo":
        os.mkfifo(marker)
    else:
        marker.mkdir()
    assert registro.reclamar_id(ID, directorio_fd=directory_fd) is False
    assert not (tmp_path / "no-crear").exists()


def test_directorio_escribible_por_grupo_deniega(tmp_path: Path, directory_fd) -> None:
    tmp_path.chmod(0o770)
    with pytest.raises(registro.RegistroNoDisponibleError):
        registro.reclamar_id(ID, directorio_fd=directory_fd)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", [True, -1, 999999])
def test_descriptor_invalido_deniega(bad) -> None:
    with pytest.raises(registro.RegistroNoDisponibleError):
        registro.reclamar_id(ID, directorio_fd=bad)


def test_descriptor_de_fichero_no_sirve(tmp_path: Path) -> None:
    path = tmp_path / "not-a-directory"
    path.touch()
    with path.open("rb") as stream, pytest.raises(registro.RegistroNoDisponibleError):
        registro.reclamar_id(ID, directorio_fd=stream.fileno())


def test_disco_lleno_deniega_sin_inventar_consumo(
    tmp_path: Path, directory_fd, monkeypatch,
) -> None:
    def full(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "sin espacio")

    monkeypatch.setattr(registro.os, "open", full)
    with pytest.raises(registro.RegistroNoDisponibleError):
        registro.reclamar_id(ID, directorio_fd=directory_fd)
    assert list(tmp_path.iterdir()) == []


def test_cambio_de_nombre_del_directorio_no_redirige_operaciones(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.mkdir(mode=0o700)
    moved = tmp_path / "moved"
    fd = os.open(original, os.O_RDONLY | os.O_DIRECTORY)
    try:
        original.rename(moved)
        original.mkdir(mode=0o700)
        assert registro.reclamar_id(ID, directorio_fd=fd)
        assert list(original.iterdir()) == []
        assert (moved / f"solicitud-{ID}").exists()
    finally:
        os.close(fd)


def test_hilos_solo_una_reclamacion(directory_fd) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: registro.reclamar_id(ID, directorio_fd=directory_fd), range(24),
        ))
    assert results.count(True) == 1
    assert results.count(False) == 23


def test_procesos_independientes_y_reapertura_no_reutilizan_id(tmp_path: Path) -> None:
    code = (
        "import os,sys\n"
        "from deploy.ops.registro_repeticiones_ops4 import reclamar_id\n"
        "fd=os.open(sys.argv[1], os.O_RDONLY|os.O_DIRECTORY)\n"
        "try: print(reclamar_id(sys.argv[2], directorio_fd=fd))\n"
        "finally: os.close(fd)\n"
    )
    argv = [sys.executable, "-c", code, str(tmp_path), ID]
    repo = Path(__file__).resolve().parents[1]
    processes = []
    try:
        for _ in range(8):
            processes.append(subprocess.Popen(
                argv, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ))
        results = [p.communicate(timeout=15) for p in processes]
        assert all(p.returncode == 0 for p in processes)
        assert [out.strip() for out, _err in results].count(b"True") == 1
        assert [out.strip() for out, _err in results].count(b"False") == 7
        reopened = subprocess.run(argv, cwd=repo, capture_output=True, check=True, timeout=15)
        assert reopened.stdout.strip() == b"False"
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait()


@pytest.mark.parametrize("stage", ["dup", "fstat", "close_marker", "close_directory"])
def test_errores_de_descriptor_no_autorizan(directory_fd, monkeypatch, stage: str) -> None:
    # Restaurar antes de que pytest inspeccione sus propios FD de captura.
    with monkeypatch.context() as patch:
        if stage in ("dup", "fstat"):
            def fail(*_args):
                raise OSError(errno.EBADF, "descriptor no disponible")

            patch.setattr(registro.os, stage, fail)
        else:
            real_close = os.close
            calls = 0
            failure = 1 if stage == "close_marker" else 2

            def close_then_fail(fd):
                nonlocal calls
                calls += 1
                real_close(fd)
                if calls == failure:
                    raise OSError(errno.EINTR, "no reintentar close")

            patch.setattr(registro.os, "close", close_then_fail)
        with pytest.raises(registro.RegistroNoDisponibleError):
            registro.reclamar_id(ID, directorio_fd=directory_fd)


def test_sin_fugas_en_exitos_repeticiones_y_fallos(directory_fd) -> None:
    before = len(os.listdir("/proc/self/fd"))

    def fail(_fd):
        raise OSError(errno.EIO, "fallo simulado")

    for i in range(16):
        id_ = f"{i:032x}"
        assert registro.reclamar_id(id_, directorio_fd=directory_fd)
        assert not registro.reclamar_id(id_, directorio_fd=directory_fd)
        with pytest.raises(registro.RegistroNoDisponibleError):
            registro.reclamar_id(f"{i + 100:032x}", directorio_fd=directory_fd, sincronizar=fail)
    assert len(os.listdir("/proc/self/fd")) == before


def solicitud() -> tuple[bytes, bytes]:
    key = bytes(range(32))
    data = {"v": 3, "id": ID, "accion": "actualizar", "creada": 1_800_000_000,
            "prueba": "sintetica", "firma": "0" * 64}
    data["firma"] = protocolo.firmar(key, data)
    return json.dumps(data, separators=(",", ":")).encode() + b"\n", key


def test_admision_autentica_antes_de_consumir_marca(tmp_path: Path, directory_fd) -> None:
    line, key = solicitud()

    def claim(id_):
        return registro.reclamar_id(id_, directorio_fd=directory_fd)

    assert admitir(
        line, clave=key, ahora=1_800_000_000,
        verificar_prueba=lambda _: False, reclamar_id=claim,
    ) is CodigoAdmision.PRUEBA_INVALIDA
    assert list(tmp_path.iterdir()) == []
    assert admitir(
        line, clave=key, ahora=1_800_000_000,
        verificar_prueba=lambda _: True, reclamar_id=claim,
    ) is CodigoAdmision.ACEPTADA
    assert admitir(
        line, clave=key, ahora=1_800_000_000,
        verificar_prueba=lambda _: True, reclamar_id=claim,
    ) is CodigoAdmision.REPETIDA


def test_admision_no_disponible_si_persistencia_no_acreditada(directory_fd) -> None:
    line, key = solicitud()

    def fail(_fd):
        raise OSError(errno.EIO, "sync no acreditado")

    def claim(id_):
        return registro.reclamar_id(id_, directorio_fd=directory_fd, sincronizar=fail)

    assert admitir(
        line, clave=key, ahora=1_800_000_000,
        verificar_prueba=lambda _: True, reclamar_id=claim,
    ) is CodigoAdmision.NO_DISPONIBLE
    assert registro.reclamar_id(ID, directorio_fd=directory_fd) is False


# ── Consumo durable de autorizaciones: namespace propio (SPEC §7.2-§7.3) ──────


def test_prefijo_propio_de_autorizacion(tmp_path: Path, directory_fd) -> None:
    assert registro.reclamar_autorizacion(ID, directorio_fd=directory_fd) is True
    marca = tmp_path / f"{registro.PREFIJO_AUTORIZACION}{ID}"
    assert marca.read_bytes() == b""
    assert stat.S_IMODE(marca.stat().st_mode) == 0o600
    assert not (tmp_path / f"{registro.PREFIJO_SOLICITUD_V3}{ID}").exists()
    assert registro.reclamar_autorizacion(ID, directorio_fd=directory_fd) is False


def test_prefijos_distintos_no_se_satisfacen_entre_si(tmp_path: Path, directory_fd) -> None:
    # Una marca del registro experimental v3 en el mismo directorio no consume
    # ni satisface la autorización, y al revés: comparten ID a propósito.
    assert registro.reclamar_id(ID, directorio_fd=directory_fd) is True
    assert registro.reclamar_autorizacion(ID, directorio_fd=directory_fd) is True
    assert (tmp_path / f"{registro.PREFIJO_SOLICITUD_V3}{ID}").exists()
    assert (tmp_path / f"{registro.PREFIJO_AUTORIZACION}{ID}").exists()
    assert registro.reclamar_autorizacion(ID, directorio_fd=directory_fd) is False
    otro = "c" * 32
    assert registro.reclamar_autorizacion(otro, directorio_fd=directory_fd) is True
    assert registro.reclamar_id(otro, directorio_fd=directory_fd) is True


def test_vistos_v3_no_satisface_ni_se_satisface_por_la_autorizacion(tmp_path: Path) -> None:
    vistos = tmp_path / "vistos"
    autorizaciones = tmp_path / "autorizaciones"
    vistos.mkdir()
    autorizaciones.mkdir(mode=0o700)
    (vistos / ID).write_text("1800000000", encoding="ascii")  # `marcar_visto`
    auth_fd = os.open(autorizaciones, os.O_RDONLY | os.O_DIRECTORY)
    vistos_fd = os.open(vistos, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert registro.reclamar_autorizacion(ID, directorio_fd=auth_fd) is True
        # Consumir la autorización no crea ni modifica la marca v3.
        assert (vistos / ID).read_text(encoding="ascii") == "1800000000"
        assert sorted(os.listdir(vistos)) == [ID]
    finally:
        os.close(vistos_fd)
        os.close(auth_fd)
    # Una purga de `vistos` (borrar sus entradas) no reabre la autorización.
    (vistos / ID).unlink()
    auth_fd = os.open(autorizaciones, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert registro.reclamar_autorizacion(ID, directorio_fd=auth_fd) is False
    finally:
        os.close(auth_fd)
    assert (autorizaciones / f"{registro.PREFIJO_AUTORIZACION}{ID}").exists()


def test_el_registro_de_autorizacion_no_vive_en_run_ni_en_vistos() -> None:
    modulo = Path(registro.__file__).read_text(encoding="utf-8")
    assert "/run" not in modulo
    assert "vistos" not in modulo
    assert registro.PREFIJO_AUTORIZACION != registro.PREFIJO_SOLICITUD_V3
    assert registro.PREFIJO_AUTORIZACION.startswith("autorizacion-")


def test_reclamador_durable_para_el_verificador(directory_fd) -> None:
    reclamar = registro.crear_reclamador_durable(directory_fd)
    assert reclamar(ID) is True
    assert reclamar(ID) is False
    with pytest.raises(registro.RegistroNoDisponibleError):
        reclamar("../escape")


def test_fallo_de_sincronizacion_en_autorizacion_no_autoriza_ni_borra(directory_fd) -> None:
    with pytest.raises(registro.RegistroNoDisponibleError):
        registro.reclamar_autorizacion(
            ID, directorio_fd=directory_fd, sincronizar=lambda _fd: False,
        )
    # La marca creada no se borra aunque la sincronización no se acredite.
    assert registro.reclamar_autorizacion(ID, directorio_fd=directory_fd) is False


def test_procesos_nuevos_no_reutilizan_la_autorizacion(tmp_path: Path) -> None:
    code = (
        "import os,sys\n"
        "from deploy.ops.registro_repeticiones_ops4 import reclamar_autorizacion\n"
        "fd=os.open(sys.argv[1], os.O_RDONLY|os.O_DIRECTORY)\n"
        "try: print(reclamar_autorizacion(sys.argv[2], directorio_fd=fd))\n"
        "finally: os.close(fd)\n"
    )
    argv = [sys.executable, "-c", code, str(tmp_path), ID]
    repo = Path(__file__).resolve().parents[1]
    processes = []
    try:
        for _ in range(8):
            processes.append(subprocess.Popen(
                argv, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ))
        results = [p.communicate(timeout=15) for p in processes]
        assert all(p.returncode == 0 for p in processes)
        assert [out.strip() for out, _err in results].count(b"True") == 1
        assert [out.strip() for out, _err in results].count(b"False") == 7
        reopened = subprocess.run(argv, cwd=repo, capture_output=True, check=True, timeout=15)
        assert reopened.stdout.strip() == b"False"
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait()
    assert (tmp_path / f"{registro.PREFIJO_AUTORIZACION}{ID}").exists()
