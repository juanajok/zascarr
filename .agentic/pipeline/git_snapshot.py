"""Materializa candidatos de texto en Git privado, sin filtros ni hooks."""

from __future__ import annotations

import subprocess
from pathlib import Path

_ENV = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "LC_ALL": "C",
    "GIT_AUTHOR_NAME": "Agentic pipeline",
    "GIT_AUTHOR_EMAIL": "pipeline@local.invalid",
    "GIT_COMMITTER_NAME": "Agentic pipeline",
    "GIT_COMMITTER_EMAIL": "pipeline@local.invalid",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_ALLOW_PROTOCOL": "",
}


def git(root: Path, *args: str, data: bytes = b"") -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_ENV,
            timeout=20,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("No se pudo leer o construir el snapshot de Git") from exc


def base_files(root: Path, paths: list[str]) -> tuple[str, dict[str, str]]:
    sha = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    files = {}
    total = 0
    for path in paths:
        entry = git(root, "ls-tree", "-z", sha, "--", path)
        if not entry.startswith(b"100644 blob ") or not entry.endswith(
            b"\t" + path.encode() + b"\0"
        ):
            raise ValueError("Solo se admiten archivos rastreados de texto no ejecutables")
        obj = f"{sha}:{path}"
        size = int(git(root, "cat-file", "-s", obj))
        total += size
        if total > 512_000:
            raise ValueError("Snapshot demasiado grande")
        files[path] = git(root, "cat-file", "blob", obj).decode("utf-8")
        if "\0" in files[path]:
            raise ValueError("Solo se admite texto UTF-8")
    return sha, files


def snapshot(repo: Path, files: dict[str, str], parent: str | None = None) -> str:
    if not repo.exists():
        repo.mkdir(mode=0o700)
        git(repo, "init", "--bare", "--template=", "--object-format=sha1")
    records = []
    for name, text in sorted(files.items()):
        blob = git(repo, "hash-object", "-w", "--stdin", data=text.encode()).strip()
        records.append(b"100644 " + blob + b"\t" + name.encode() + b"\0")
    git(repo, "read-tree", "--empty")
    git(repo, "update-index", "-z", "--index-info", data=b"".join(records))
    tree = git(repo, "write-tree").decode().strip()
    parents = ["-p", parent] if parent else []
    sha = git(repo, "commit-tree", tree, *parents, "-m", "Snapshot acotado").decode().strip()
    git(repo, "update-ref", f"refs/snapshots/{sha}", sha)
    return sha


def verify_snapshot(repo: Path, sha: str, parent: str, files: dict[str, str]) -> None:
    """Verifica que el commit entregado conserva padre y bytes del candidato."""
    ancestry = git(repo, "rev-list", "--parents", "-n", "1", sha).decode().strip().split()
    tree = git(repo, "ls-tree", "-rz", sha).rstrip(b"\0").split(b"\0")
    names = {entry.split(b"\t", 1)[-1] for entry in tree}
    if ancestry != [sha, parent] or names != {name.encode() for name in files}:
        raise ValueError("Árbol o ascendencia de entrega inválidos")
    for name, expected in files.items():
        obj = f"{sha}:{name}"
        if git(repo, "cat-file", "blob", obj) != expected.encode():
            raise ValueError("El commit de entrega no corresponde al artefacto")
