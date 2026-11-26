"""Comprueba el pin aislado de OpenSpec y su exclusión del contexto Docker."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / "tooling" / "sdd"
PACKAGE = "@fission-ai/openspec"
VERSION = "2.2.0"


class SddToolingTest(unittest.TestCase):
    def test_manifest_pins_exact_private_dependency(self) -> None:
        manifest = json.loads((TOOLING / "package.json").read_text())
        self.assertIs(manifest["private"], True)
        self.assertEqual(manifest["devDependencies"], {PACKAGE: VERSION})
        self.assertFalse(manifest.get("dependencies"))

    def test_lock_matches_manifest_and_has_integrity(self) -> None:
        manifest = json.loads((TOOLING / "package.json").read_text())
        lock = json.loads((TOOLING / "package-lock.json").read_text())
        self.assertEqual(lock["lockfileVersion"], 3)
        packages = lock["packages"]
        self.assertEqual(packages[""]["devDependencies"], manifest["devDependencies"])
        self.assertEqual(packages["node_modules/" + PACKAGE]["version"], VERSION)
        for path, package in packages.items():
            if path:
                with self.subTest(path=path):
                    self.assertTrue(package.get("integrity"))
                    self.assertTrue(package.get("resolved"))

    def test_docker_allowlist_does_not_include_tooling(self) -> None:
        lines = (ROOT / ".dockerignore").read_text().splitlines()
        # Docker recorta espacios en los patrones: una línea con espacio
        # periférico podría abrir un patrón fuera de la lista de permitidos.
        # Sin subTest: dentro de él la aserción no propagaría a quien llama.
        for line in lines:
            self.assertEqual(line, line.strip(), f"espacio periférico en {line!r}")
        self.assertIn("**", lines)
        # Solo se permite una lista conocida: un comodín nuevo podría reabrir tooling.
        allowed = {"Dockerfile", "pyproject.toml", "uv.lock", "src/", "src/**",
                   "alembic.ini", "alembic/", "alembic/**", "LICENSE",
                   ".env.example", "docker-entrypoint.sh", "scripts/",
                   "scripts/comprobar_imagen_rar.py"}
        self.assertTrue({line[1:] for line in lines if line.startswith("!")} <= allowed)

    def _assert_docker_context_valid(self, content: str) -> None:
        with patch.object(Path, "read_text", return_value=content):
            self.test_docker_allowlist_does_not_include_tooling()

    def test_docker_allowlist_rejects_whitespace_and_unknown_exceptions(self) -> None:
        # Docker recorta espacios en los patrones: una excepción con espacio
        # inicial no debe escapar del análisis de la lista de permitidos.
        for line in (" !tooling/**", "!tooling/**", "!unexpected"):
            with self.subTest(line=line), self.assertRaises(AssertionError):
                self._assert_docker_context_valid(f"**\n{line}\n")

    def test_docker_allowlist_accepts_comments_blank_lines_and_crlf(self) -> None:
        self._assert_docker_context_valid("# comentario\r\n\r\n**\r\n!Dockerfile\r\n")


if __name__ == "__main__":
    unittest.main()
