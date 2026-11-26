"""Pruebas del runner declarativo y del Docker local autorizado."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.runner import Runner, validate_checks

IMAGE = "sha256:" + "a" * 64
CONTAINER = "b" * 64
CONTAINS = {"id": "line", "kind": "contains", "path": "src/demo.txt", "text": "hola"}
DOCKER = {
    "id": "python",
    "kind": "docker",
    "image": IMAGE,
    "argv": ["python", "-c", "print('canario')"],
    "timeout": 3,
}


class ValidationTests(unittest.TestCase):
    def test_only_exact_check_shapes(self) -> None:
        self.assertIsNone(validate_checks([CONTAINS, DOCKER]))
        self.assertIsNone(validate_checks([{**DOCKER, "scratch": True}]))
        for invalid in (False, 1, 0, "true", None, [], {}):
            with self.subTest(scratch=invalid), self.assertRaises(ValueError):
                validate_checks([{**DOCKER, "scratch": invalid}])
        for checks in (
            (),
            [None],
            [CONTAINS, CONTAINS],
            [{**CONTAINS, "extra": 1}],
            [{**CONTAINS, "id": " "}],
            [{**CONTAINS, "kind": []}],
            [{**CONTAINS, "text": 5}],
            [{**DOCKER, "image": "python:3.11"}],
            [{**DOCKER, "image": "python@" + IMAGE}],
            [{**DOCKER, "image": IMAGE + "\n"}],
            [{**DOCKER, "timeout": True}],
            [{**DOCKER, "timeout": 0}],
            [{**DOCKER, "timeout": 1.5}],
            [{**DOCKER, "argv": "python"}],
            [{**DOCKER, "argv": []}],
            [{**DOCKER, "argv": [""]}],
            [{**DOCKER, "argv": ["python", 2]}],
            [{**DOCKER, "argv": ["python", "\0"]}],
        ):
            with self.subTest(checks=checks), self.assertRaises(ValueError):
                validate_checks(checks)

    def test_path_traversal_and_noncanonical_paths_are_rejected(self) -> None:
        for path in ("../demo", "/demo", "a/../../demo", "a//demo", "./demo", "a\\b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_checks([{**CONTAINS, "path": path}])


class RunnerTests(unittest.TestCase):
    def assert_result(
        self,
        result: dict,
        passed: bool,
        kind: str,
        code: int | None,
    ) -> None:
        self.assertEqual(set(result), {"passed", "kind", "exit_code", "duration_ms"})
        self.assertIs(result["passed"], passed)
        self.assertEqual(result["kind"], kind)
        self.assertEqual(result["exit_code"], code)
        self.assertIs(type(result["duration_ms"]), int)
        self.assertGreaterEqual(result["duration_ms"], 0)
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_declarative_fixture_uses_only_the_snapshot(self) -> None:
        with patch("pipeline.runner.subprocess.run") as process:
            self.assert_result(
                Runner().run({"src/demo.txt": "hola\n"}, CONTAINS), True, "contains", None
            )
            self.assert_result(
                Runner().run({"src/demo.txt": "Hola\n"}, CONTAINS), False, "contains", None
            )
            self.assert_result(
                Runner().run({"other.txt": "hola"}, CONTAINS), False, "contains", None
            )
            process.assert_not_called()

    def test_docker_needs_explicit_operator_enablement(self) -> None:
        with patch("pipeline.runner.subprocess.run") as process:
            self.assert_result(Runner().run({}, DOCKER), False, "docker-disabled", None)
            process.assert_not_called()

    def test_bad_snapshot_never_invokes_docker(self) -> None:
        with patch("pipeline.runner.subprocess.run") as process:
            for files in (
                {"../outside": "hola"},
                {"src": "a", "src/demo.txt": "b"},
                {"src/demo.txt": 1},
            ):
                with self.subTest(files=files):
                    self.assert_result(
                        Runner(allow_docker=True).run(files, DOCKER), False, "snapshot-error", None
                    )
            process.assert_not_called()

    def test_exact_text_preserves_lf_and_rejects_extra_bytes(self) -> None:
        check = {"id": "exact", "kind": "equals", "path": "label.txt", "text": "Tu tebeoteca\n"}
        self.assert_result(
            Runner().run({"label.txt": "Tu tebeoteca\n"}, check), True, "equals", None
        )
        for text in ("Tu tebeoteca", "Tu tebeoteca\r\n", "Tu tebeoteca\nExtra"):
            self.assert_result(Runner().run({"label.txt": text}, check), False, "equals", None)

    def test_bad_check_is_not_an_assertion_failure(self) -> None:
        self.assert_result(
            Runner().run({}, {**DOCKER, "image": "private-token"}), False, "check-error", None
        )

    def test_docker_hardening_exact_cleanup_and_snapshot_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            calls = []

            def invoke(command: list[str], **options: object) -> subprocess.CompletedProcess:
                self.assertEqual(
                    command[:4],
                    ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock", "--config"],
                )
                self.assertEqual(list(Path(command[4]).iterdir()), [])
                self.assertEqual(options["stdin"], subprocess.DEVNULL)
                self.assertEqual(options["stderr"], subprocess.DEVNULL)
                self.assertEqual(options["env"], {"PATH": "/usr/bin:/bin"})
                self.assertNotIn("shell", options)
                calls.append(command[5:])
                if command[5:7] == ["image", "inspect"]:
                    metadata = f"{IMAGE}\nok\nPATH\nSECRET_KEY\n".encode()
                    return subprocess.CompletedProcess(command, 0, metadata)
                if command[5] == "create":
                    args = command[5:]
                    for flag in (
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
                        "--env=SECRET_KEY",
                        "--entrypoint=python",
                    ):
                        self.assertIn(flag, args)
                    self.assertEqual(args[-3:], [IMAGE, *DOCKER["argv"][1:]])
                    mount = next(arg for arg in args if arg.startswith("--mount="))
                    source = Path(mount.split("source=", 1)[1].split(",", 1)[0])
                    self.assertTrue(source.is_relative_to(scratch))
                    self.assertEqual(mount.split(",")[2:], ["target=/src", "readonly"])
                    self.assertEqual(source.parent.stat().st_mode & 0o777, 0o700)
                    self.assertEqual((source / "p/q.py").stat().st_mode & 0o777, 0o644)
                    self.assertEqual((source / "p/q.py").read_text(), "hola\n")
                    output = CONTAINER.encode()
                else:
                    output = {"wait": b"7", "inspect": b"exited true"}.get(command[5], b"")
                return subprocess.CompletedProcess(command, 0, output)

            with patch("pipeline.runner.subprocess.run", side_effect=invoke):
                self.assert_result(
                    Runner(True, scratch).run({"p/q.py": "hola\n"}, DOCKER), False, "docker", 7
                )
            self.assertEqual(calls[2:4], [["start", CONTAINER], ["wait", CONTAINER]])
            self.assertEqual(calls[-1], ["rm", "--force", CONTAINER])
            self.assertEqual(list(scratch.iterdir()), [])

    def test_scratch_is_opt_in_and_uses_a_fixed_ephemeral_tmpfs(self) -> None:
        creates = []

        def invoke(command: list[str], **_: object) -> subprocess.CompletedProcess:
            args = command[5:]
            if args[:2] == ["image", "inspect"]:
                return subprocess.CompletedProcess(command, 0, f"{IMAGE}\nok\nPATH\n".encode())
            if args[0] == "create":
                creates.append(args)
                return subprocess.CompletedProcess(command, 0, CONTAINER.encode())
            output = {"wait": b"0", "inspect": b"exited true"}.get(args[0], b"")
            return subprocess.CompletedProcess(command, 0, output)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("pipeline.runner.subprocess.run", side_effect=invoke),
        ):
            runner = Runner(True, Path(directory))
            self.assert_result(runner.run({}, {**DOCKER, "scratch": True}), True, "docker", 0)
            self.assert_result(runner.run({}, DOCKER), True, "docker", 0)

        enabled, disabled = creates
        index = enabled.index("--tmpfs")
        self.assertEqual(
            enabled[index + 1],
            "/scratch:rw,noexec,nosuid,nodev,size=32m,uid=65534,gid=65534,mode=0700",
        )
        self.assertIn("--env=HOME=/scratch", enabled)
        self.assertIn("--env=TMPDIR=/scratch", enabled)
        for flag in (
            "--read-only",
            "--network=none",
            "--user=65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--ipc=none",
            "--pull=never",
            "--log-driver=none",
            "--no-healthcheck",
            "--memory=256m",
            "--memory-swap=256m",
            "--pids-limit=64",
            "--cpus=1",
        ):
            self.assertIn(flag, enabled)
        self.assertNotIn("--tmpfs", disabled)
        self.assertIn("--env=HOME=/nonexistent", disabled)
        self.assertNotIn("--env=TMPDIR", disabled)

    def test_docker_failure_modes_are_not_usable_as_a_red_result(self) -> None:
        for stage, code, kind in (
            ("image", 1, "docker-error"),
            ("create", 125, "docker-error"),
            ("start", 1, "docker-error"),
            ("wait", 1, "docker-error"),
            ("workload", 127, "docker-error"),
            ("workload", 137, "docker-error"),
            ("state", 0, "docker-error"),
            ("cleanup", 1, "docker-error"),
            ("timeout", 0, "docker-timeout"),
        ):
            with self.subTest(stage=stage, code=code):
                calls = []

                def invoke(
                    command: list[str], *, calls=calls, stage=stage, code=code, **_: object
                ) -> subprocess.CompletedProcess:
                    verb = command[5]
                    calls.append(command[5:])
                    if verb == stage or (verb == "rm" and stage == "cleanup"):
                        return subprocess.CompletedProcess(command, code, b"PRIVATE PAYLOAD")
                    if verb == "wait" and stage == "timeout":
                        raise subprocess.TimeoutExpired(command, DOCKER["timeout"])
                    output = {
                        "image": f"{IMAGE}\nok".encode(),
                        "create": CONTAINER.encode(),
                        "wait": str(code if stage == "workload" else 0).encode(),
                        "inspect": (
                            b"false"
                            if "--type=container" in command[6:]
                            else b"exited false"
                            if stage == "state"
                            else b"exited true"
                        ),
                    }.get(verb, b"")
                    return subprocess.CompletedProcess(command, 0, output)

                with (
                    tempfile.TemporaryDirectory() as directory,
                    patch(
                        "pipeline.runner.subprocess.run",
                        side_effect=invoke,
                    ),
                ):
                    self.assert_result(
                        Runner(True, Path(directory)).run({}, DOCKER), False, kind, None
                    )
                    self.assertEqual(list(Path(directory).iterdir()), [])
                if stage not in {"image", "create"}:
                    self.assertEqual(calls[-1], ["rm", "--force", CONTAINER])
                elif stage == "create":
                    self.assertEqual(calls[-1][0], "inspect")
                    self.assertFalse(any(call[0] == "rm" for call in calls))

    def test_failed_create_recovers_only_by_verified_owner_label(self) -> None:
        calls = []

        def invoke(command: list[str], **_: object) -> subprocess.CompletedProcess:
            args = command[5:]
            calls.append(args)
            if args[0] == "create":
                raise subprocess.TimeoutExpired(command, 3)
            output = {"image": f"{IMAGE}\nok".encode(), "inspect": CONTAINER.encode()}
            return subprocess.CompletedProcess(command, 0, output.get(args[0], b""))

        with patch("pipeline.runner.subprocess.run", side_effect=invoke):
            self.assert_result(Runner(True).run({}, DOCKER), False, "docker-error", None)
        name = next(arg for arg in calls[1] if arg.startswith("--name=")).split("=", 1)[1]
        self.assertIn(f"--label=agentic.runner={name}", calls[1])
        self.assertIn(f'(index .Config.Labels "agentic.runner") "{name}"', calls[2][2])
        self.assertEqual(calls[2][-1], name)
        self.assertEqual(calls[-1], ["rm", "--force", CONTAINER])

    def test_image_declaring_volume_never_starts(self) -> None:
        with patch(
            "pipeline.runner.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                f"{IMAGE}\nvolumes".encode(),
            ),
        ) as process:
            self.assert_result(Runner(True).run({}, DOCKER), False, "docker-error", None)
            process.assert_called_once()


@unittest.skipUnless(os.getenv("AGENTIC_DOCKER_TEST_IMAGE"), "Docker canario no autorizado")
class DockerCanaryTests(unittest.TestCase):
    def test_local_python_image_uses_isolated_snapshot_and_no_host_environment(self) -> None:
        image = os.environ["AGENTIC_DOCKER_TEST_IMAGE"]
        code = """from pathlib import Path
import errno
import os
assert os.getuid() != 0
assert Path.cwd() == Path('/src')
assert Path('fixtures/hello.txt').read_text() == 'hola'
assert not Path('/var/run/docker.sock').exists()
assert not Path('/sys/class/net/eth0').exists()
assert 'AGENTIC_DOCKER_CANARY_SECRET' not in os.environ
assert 'PYTHON_VERSION' not in os.environ
for target in ('/tmp/agentic-canary', '/src/agentic-canary'):
    try:
        Path(target).write_text('canario')
    except OSError as exc:
        assert exc.errno == errno.EROFS
    else:
        raise AssertionError('montaje escribible')
print('canario inocuo')
"""
        check = {**DOCKER, "image": image, "argv": ["python", "-c", code], "timeout": 8}
        # Algunos ejecutores aíslan /tmp del host donde vive el daemon.
        with (
            tempfile.TemporaryDirectory(dir=Path.cwd()) as scratch,
            patch.dict(
                os.environ,
                {"AGENTIC_DOCKER_CANARY_SECRET": "canario"},
            ),
        ):
            result = Runner(True, Path(scratch)).run({"fixtures/hello.txt": "hola"}, check)
        self.assertEqual(
            (result["passed"], result["kind"], result["exit_code"]), (True, "docker", 0)
        )

    def test_scratch_allows_atomic_file_io_and_is_ephemeral(self) -> None:
        image = os.environ["AGENTIC_DOCKER_TEST_IMAGE"]
        write = """from pathlib import Path
import errno
import os
import subprocess
import sys

scratch = Path('/scratch')
info = scratch.stat()
assert (info.st_uid, info.st_gid) == (65534, 65534), (info.st_uid, info.st_gid)
assert info.st_mode & 0o777 == 0o700, oct(info.st_mode & 0o777)
assert os.environ['TMPDIR'] == '/scratch'
assert os.environ['HOME'] == '/scratch'
assert list(scratch.iterdir()) == []
source = scratch / 'temporal'
source.write_text('datos')
target = scratch / 'final'
os.replace(source, target)
assert target.read_text() == 'datos'
assert not source.exists()
subprocess.run(
    [sys.executable, '-c', 'from pathlib import Path; Path("/scratch/hijo").write_text("ok")'],
    check=True,
)
assert (scratch / 'hijo').read_text() == 'ok'
script = scratch / 'ejecutable'
script.write_text('#!/bin/sh\\nexit 0\\n')
script.chmod(0o755)
try:
    subprocess.run([str(script)], check=True)
except OSError as exc:
    assert exc.errno in (errno.EACCES, errno.ENOEXEC)
else:
    raise AssertionError('tmpfs ejecutable')
try:
    Path('/src/intruso').write_text('no')
except OSError as exc:
    assert exc.errno == errno.EROFS
else:
    raise AssertionError('src escribible')
print('scratch ok')
"""
        empty = """from pathlib import Path
assert list(Path('/scratch').iterdir()) == []
print('scratch limpio')
"""
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as scratch:
            runner = Runner(True, Path(scratch))
            first = runner.run(
                {},
                {
                    **DOCKER,
                    "image": image,
                    "argv": ["python", "-c", write],
                    "timeout": 20,
                    "scratch": True,
                },
            )
            second = runner.run(
                {},
                {
                    **DOCKER,
                    "image": image,
                    "argv": ["python", "-c", empty],
                    "timeout": 20,
                    "scratch": True,
                },
            )
        self.assertEqual((first["passed"], first["kind"], first["exit_code"]), (True, "docker", 0))
        self.assertEqual(
            (second["passed"], second["kind"], second["exit_code"]), (True, "docker", 0)
        )

    def test_local_failure_and_timeout_are_distinguished_and_cleaned(self) -> None:
        image = os.environ["AGENTIC_DOCKER_TEST_IMAGE"]
        real_run = subprocess.run
        used = []

        def invoke(command: list[str], **options: object) -> subprocess.CompletedProcess:
            proc = real_run(command, **options)
            if command[5] == "create" and proc.returncode == 0:
                used.append(proc.stdout.decode().strip())
            return proc

        for code, timeout, expected in (
            ("raise AssertionError('canario')", 8, (False, "docker", 1)),
            ("import time; time.sleep(30)", 2, (False, "docker-timeout", None)),
        ):
            with (
                self.subTest(expected=expected),
                tempfile.TemporaryDirectory(
                    dir=Path.cwd(),
                ) as scratch,
                patch("pipeline.runner.subprocess.run", side_effect=invoke),
            ):
                result = Runner(True, Path(scratch)).run(
                    {},
                    {
                        **DOCKER,
                        "image": image,
                        "argv": ["python", "-c", code],
                        "timeout": timeout,
                    },
                )
                self.assertEqual((result["passed"], result["kind"], result["exit_code"]), expected)
        self.assertEqual(len(used), 2)
        listing = real_run(
            [
                "/usr/bin/docker",
                "--host",
                "unix:///var/run/docker.sock",
                "ps",
                "--all",
                "--no-trunc",
                "--format={{.ID}}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertTrue(set(used).isdisjoint(listing.stdout.splitlines()))
