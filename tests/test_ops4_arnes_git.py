"""Arnés Git local para futuros ensayos OPS4; no prueba ningún ejecutor."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class GitHarness:
    """Repositorios efímeros y entorno Git independiente del usuario."""

    remote: Path
    publisher: Path
    client: Path
    env: dict[str, str]

    def git(self, cwd: Path, *args: str) -> str:
        """Ejecuta Git sin shell ni configuración heredada."""
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, check=True,
            text=True, capture_output=True,
        )
        return result.stdout.strip()

    def advance_remote(self) -> str:
        """Publica otro commit en la rama remota local."""
        (self.publisher / "contenido.txt").write_text("segundo\n", encoding="utf-8")
        self.git(self.publisher, "add", "contenido.txt")
        self.git(self.publisher, "commit", "-m", "segundo")
        sha = self.git(self.publisher, "rev-parse", "HEAD")
        self.git(self.publisher, "push", "origin", "HEAD:refs/heads/main")
        return sha


@pytest.fixture
def git_harness(tmp_path: Path) -> GitHarness:
    """Construye remoto bare, publicador y cliente sin acceso a red."""
    home = tmp_path / "home"
    home.mkdir()
    template = tmp_path / "plantilla-vacia"
    template.mkdir()
    env = {
        "PATH": os.defpath,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TEMPLATE_DIR": str(template),
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "Prueba",
        "GIT_AUTHOR_EMAIL": "prueba@example.invalid",
        "GIT_COMMITTER_NAME": "Prueba",
        "GIT_COMMITTER_EMAIL": "prueba@example.invalid",
        "LC_ALL": "C",
    }
    harness = GitHarness(
        tmp_path / "remoto.git", tmp_path / "publicador", tmp_path / "cliente", env
    )
    harness.git(tmp_path, "init", "--bare", str(harness.remote))
    harness.git(tmp_path, "init", str(harness.publisher))
    (harness.publisher / "contenido.txt").write_text("primero\n", encoding="utf-8")
    harness.git(harness.publisher, "add", "contenido.txt")
    harness.git(harness.publisher, "commit", "-m", "primero")
    harness.git(harness.publisher, "remote", "add", "origin", str(harness.remote))
    harness.git(harness.publisher, "push", "origin", "HEAD:refs/heads/main")
    harness.git(tmp_path, "init", str(harness.client))
    harness.git(harness.client, "remote", "add", "origin", str(harness.remote))
    return harness


def test_barrera_determinista_ref_remota_avanza(git_harness: GitHarness) -> None:
    """El SHA capturado no cambia aunque avance la referencia remota."""
    h = git_harness
    h.git(h.client, "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
    candidate = h.git(h.client, "rev-parse", "refs/remotes/origin/main^{commit}")
    advanced = h.advance_remote()

    remote_sha = h.git(h.client, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert remote_sha == advanced
    assert candidate != remote_sha
    assert h.git(h.client, "rev-parse", "refs/remotes/origin/main^{commit}") == candidate
    h.git(h.client, "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
    assert h.git(h.client, "rev-parse", "refs/remotes/origin/main^{commit}") == advanced
    assert h.git(h.client, "cat-file", "-t", candidate) == "commit"
