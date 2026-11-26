"""Comprueba snapshots con fixtures declarativos o Docker local de adhesión explícita."""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from pipeline.contracts import safe_path

_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_LOCAL_DOCKER = ("/usr/bin/docker", "--host", "unix:///var/run/docker.sock")
_ADMIN_TIMEOUT = 10
_OWNER_LABEL = "agentic.runner"
_IMAGE_FORMAT = (
    '{{.Id}}{{println}}{{if index .Config "Volumes"}}volumes{{else}}ok{{end}}'
    '{{range index .Config "Env"}}{{println}}{{index (split . "=") 0}}{{end}}'
)
_STATE_FORMAT = '{{.State.Status}} {{and (not .State.OOMKilled) (eq .State.Error "")}}'
_CONTAINER_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
}
# Opciones fijas: sin ejecución desde el montaje, sin setuid, tamaño y permisos acotados.
_SCRATCH_MOUNT = "/scratch:rw,noexec,nosuid,nodev,size=32m,uid=65534,gid=65534,mode=0700"


def validate_checks(checks: list[dict]) -> None:
    """Exige configuraciones exactas con identificadores únicos, sin ejecutar nada."""
    if not isinstance(checks, list):
        raise ValueError("Se esperaba una lista de comprobaciones")
    ids: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("Comprobación no válida")
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id.strip() or check_id in ids:
            raise ValueError("Identificador de comprobación inválido o duplicado")
        ids.add(check_id)
        kind = check.get("kind")
        if kind in ("contains", "equals"):
            if (
                set(check) != {"id", "kind", "path", "text"}
                or not safe_path(check["path"])
                or not isinstance(check["text"], str)
            ):
                raise ValueError("Comprobación declarativa no válida")
        elif kind == "docker":
            fields = set(check)
            if not {"id", "kind", "image", "argv", "timeout"} <= fields or not fields <= {
                "id",
                "kind",
                "image",
                "argv",
                "timeout",
                "scratch",
            }:
                raise ValueError("Comprobación Docker no válida")
            if "scratch" in check and check["scratch"] is not True:
                raise ValueError("scratch solo admite true")
            image, argv, timeout = check["image"], check["argv"], check["timeout"]
            if (
                not isinstance(image, str)
                or _IMAGE_ID.fullmatch(image) is None
                or not isinstance(argv, list)
                or not argv
                or not argv[0]
                or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
                or type(timeout) is not int
                or timeout <= 0
            ):
                raise ValueError("Comprobación Docker no válida")
        else:
            raise ValueError("Tipo de comprobación no válido")


def _valid_snapshot(files: dict[str, str]) -> bool:
    if not isinstance(files, dict):
        return False
    for path, text in files.items():
        if not safe_path(path) or not isinstance(text, str):
            return False
        while "/" in path:
            path = path.rsplit("/", 1)[0]
            if path in files:
                return False
    return True


class _DockerError(Exception):
    """Fallo de infraestructura sin salida ni comando del proceso."""


class _DockerTimeoutError(Exception):
    """Se agotó el tiempo asignado al check."""


def _docker(config: Path, *args: str, timeout: float = _ADMIN_TIMEOUT) -> str:
    # Solo metadatos del CLI; nunca se adjunta la salida del contenedor.
    result = subprocess.run(
        [*_LOCAL_DOCKER, "--config", str(config), *args],
        env={"PATH": "/usr/bin:/bin"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise _DockerError
    return result.stdout.decode("ascii").strip()


def _image_environment(
    config: Path, image: str, overrides: dict[str, str] | None = None
) -> list[str]:
    metadata = _docker(config, "image", "inspect", "--format", _IMAGE_FORMAT, image)
    image_info = metadata.splitlines()
    # Los VOLUME de imagen provocarían montajes anónimos escribibles.
    if image_info[:2] != [image, "ok"]:
        raise _DockerError
    keys = image_info[2:]
    if any(_ENV_KEY.fullmatch(key) is None for key in keys):
        raise _DockerError
    # --env sin valor elimina el valor por defecto cuando la variable no existe
    # en el CLI. PATH está en el entorno del CLI y se fija explícitamente abajo.
    environment = _CONTAINER_ENV | (overrides or {})
    return [f"--env={key}" for key in sorted(set(keys) - environment.keys())] + [
        f"--env={key}={value}" for key, value in environment.items()
    ]


def _stage(files: dict[str, str], source: Path) -> None:
    source.mkdir()
    source.chmod(0o755)
    for path, text in files.items():
        target = source / path
        target.parent.mkdir(parents=True, exist_ok=True)
        for directory in target.parents:
            if directory == source:
                break
            directory.chmod(0o755)
        target.write_bytes(text.encode("utf-8"))
        target.chmod(0o644)


def _run_container(config: Path, source: Path, check: dict) -> tuple[str, int | None]:
    image, argv = check["image"], check["argv"]
    scratch = check.get("scratch") is True
    env_flags = _image_environment(
        config,
        image,
        {"HOME": "/scratch", "TMPDIR": "/scratch"} if scratch else None,
    )
    tmpfs = ["--tmpfs", _SCRATCH_MOUNT] if scratch else []
    mount = str(source)
    if any(char in mount for char in ',"\r\n'):
        raise _DockerError
    name = "agentic-check-" + uuid.uuid4().hex
    container = None
    try:
        container = _docker(
            config,
            "create",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--user=65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=256m",
            "--memory-swap=256m",
            "--pids-limit=64",
            "--cpus=1",
            "--ipc=none",
            "--log-driver=none",
            "--no-healthcheck",
            "--workdir=/src",
            f"--name={name}",
            f"--label={_OWNER_LABEL}={name}",
            f"--mount=type=bind,source={mount},target=/src,readonly",
            *tmpfs,
            *env_flags,
            f"--entrypoint={argv[0]}",
            image,
            *argv[1:],
        )
        if _CONTAINER_ID.fullmatch(container) is None:
            raise _DockerError
        # El límite del operador cubre el arranque y la ejecución del comando.
        started = time.monotonic()
        try:
            _docker(config, "start", container, timeout=check["timeout"])
            remaining = check["timeout"] - (time.monotonic() - started)
            if remaining <= 0:
                raise _DockerTimeoutError
            exit_code = _docker(config, "wait", container, timeout=remaining)
        except subprocess.TimeoutExpired:
            raise _DockerTimeoutError from None
        state = _docker(config, "inspect", "--format", _STATE_FORMAT, container)
        if state != "exited true" or re.fullmatch(r"[0-9]{1,3}", exit_code) is None:
            raise _DockerError
        code = int(exit_code)
        # Códigos reservados por Docker y salidas por señal no acreditan RED.
        if code >= 125:
            raise _DockerError
        return "docker", code
    finally:
        if container is None or _CONTAINER_ID.fullmatch(container) is None:
            # La solicitud create puede alcanzar al daemon aun si falla el CLI.
            # No se elimina por nombre: se verifica la marca y se usa el ID.
            owner_format = (
                '{{if eq (index .Config.Labels "'
                + _OWNER_LABEL
                + '") "'
                + name
                + '"}}{{.Id}}{{end}}'
            )
            try:
                container = _docker(
                    config, "inspect", "--type=container", "--format=" + owner_format, name
                )
            except (OSError, UnicodeError, subprocess.TimeoutExpired, _DockerError):
                container = None
        if container is not None and _CONTAINER_ID.fullmatch(container):
            _docker(config, "rm", "--force", container)


class Runner:
    """Ejecuta únicamente configuraciones de confianza sobre archivos de texto.

    Si se autoriza Docker, el daemon local debe compartir la ruta de `scratch`
    (o el temporal por defecto) con este proceso. Docker no es una VM.
    """

    def __init__(self, allow_docker: bool = False, scratch: Path | None = None) -> None:
        self._allow_docker = allow_docker is True
        self._scratch = scratch

    def run(self, files: dict[str, str], check: dict) -> dict:
        """Devuelve evidencia mínima; solo un kind esperado acredita la comprobación."""
        started = time.monotonic_ns()
        passed, exit_code = False, None
        try:
            validate_checks([check])
        except ValueError:
            kind = "check-error"
        else:
            if not _valid_snapshot(files):
                kind = "snapshot-error"
            elif check["kind"] in {"contains", "equals"}:
                kind = check["kind"]
                text = files.get(check["path"])
                passed = text is not None and (
                    text == check["text"] if kind == "equals" else check["text"] in text
                )
            elif not self._allow_docker:
                kind = "docker-disabled"
            else:
                try:
                    with tempfile.TemporaryDirectory(dir=self._scratch, prefix="agentic-") as tmp:
                        root = Path(tmp).resolve()
                        root.chmod(0o700)
                        config, source = root / "docker", root / "src"
                        config.mkdir(mode=0o700)
                        _stage(files, source)
                        kind, exit_code = _run_container(config, source, check)
                except _DockerTimeoutError:
                    kind = "docker-timeout"
                except (
                    OSError,
                    UnicodeError,
                    OverflowError,
                    subprocess.TimeoutExpired,
                    _DockerError,
                ):
                    kind, exit_code = "docker-error", None
                passed = kind == "docker" and exit_code == 0
        return {
            "passed": passed,
            "kind": kind,
            "exit_code": exit_code,
            "duration_ms": (time.monotonic_ns() - started) // 1_000_000,
        }
