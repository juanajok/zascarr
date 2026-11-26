"""Checkpoints de un escritor y objetos inmutables por contenido."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pipeline.contracts import canonical


def atomic(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".checkpoint-")
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(name).unlink(missing_ok=True)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @contextmanager
    def lock(self) -> Iterator[None]:
        with (self.root / ".lock").open("ab") as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            yield

    def put(self, value: object) -> str:
        raw = canonical(value)
        key = hashlib.sha256(raw).hexdigest()
        atomic(self.root / "objects" / key, raw)
        return key

    def get(self, key: str) -> dict:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Referencia de evidencia no válida")
        raw = (self.root / "objects" / key).read_bytes()
        if hashlib.sha256(raw).hexdigest() != key:
            raise ValueError("Evidencia alterada")
        return json.loads(raw)

    def load(self) -> dict:
        return json.loads((self.root / "state.json").read_bytes())

    def save(self, state: dict) -> None:
        atomic(self.root / "state.json", canonical(state))
