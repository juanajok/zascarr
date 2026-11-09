#!/usr/bin/env python3
"""Prototipo de conversión CBR→CBZ con memoria baja (BL-CNV0, #477).

No extrae el RAR completo: lista con `lsar`, y para cada entrada ejecuta
`unar -q -f -D -o - -i <archivo> <índice>` escribiendo la salida directamente en
un ZIP_STORED en streaming. Solo lee la copia montada en /samples.
"""
from __future__ import annotations

import json
import os
import resource
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

WORK = Path(os.environ.get("WORK", "/trabajo"))
CBZ = WORK / "out.cbz"
TIMEOUT = 900
BLOQUE = 1024 * 1024


def _rss() -> int:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError:
        pass
    return 0


def _maxrss() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def _cgroup_peak() -> int:
    for p in ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"):
        try:
            return int(Path(p).read_text().strip())
        except (OSError, ValueError):
            continue
    return 0


def _lsar(path: Path) -> tuple[dict, str]:
    try:
        r = subprocess.run(["lsar", "-L", "-j", "-nr", str(path)],
                           capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return {}, "timeout"
    if r.returncode != 0:
        return {}, (r.stderr or r.stdout or "error").strip()[:200]
    try:
        return json.loads(r.stdout), ""
    except json.JSONDecodeError:
        return {}, "json"


def _entradas(doc: dict) -> list[tuple[int, str, int, int | None]]:
    out = []
    for e in doc.get("lsarContents", []) or []:
        if not isinstance(e, dict):
            continue
        n = e.get("XADFileName")
        size = e.get("XADFileSize")
        idx = e.get("XADIndex")
        if not isinstance(n, str) or not isinstance(size, int) or not isinstance(idx, int):
            continue
        if n.endswith("/") or size == 0:
            continue
        n = n.replace("\\", "/").lstrip("./")
        crc = e.get("RARCRC32", e.get("RAR5CRC32"))
        out.append((idx, n, size, int(crc) if isinstance(crc, int) else None))
    return sorted(out)


def _limpiar() -> None:
    try:
        CBZ.unlink()
    except OSError:
        pass


def medir(src: Path) -> dict:
    base = {
        "tipo": "streaming", "origen_bytes": src.stat().st_size,
        "t_unar_s": None, "t_zip_s": None, "t_total_s": None,
        "cbz_bytes": None, "delta_bytes": None, "ratio": None,
        "entradas_lsar": None, "entradas_zip": None, "tmp_bytes": 0,
        "rss_kib": None, "cgroup_peak_bytes": None,
        "testzip": None, "nombres": None, "tamanos": None, "crc": None,
        "error": None,
    }
    _limpiar()
    WORK.mkdir(parents=True, exist_ok=True)
    doc, err = _lsar(src)
    if err:
        base["error"] = "lsar:" + err
        return base
    entradas = _entradas(doc)
    base["entradas_lsar"] = len(entradas)
    orig = {n: (s, c) for _i, n, s, c in entradas}
    t0 = time.perf_counter()
    t_unar = 0.0
    try:
        with zipfile.ZipFile(CBZ, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for idx, nombre, size, _crc in entradas:
                tu = time.perf_counter()
                con = subprocess.Popen(
                    ["unar", "-q", "-f", "-D", "-o", "-", "-i", str(src), str(idx)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    with z.open(nombre, "w", force_zip64=True) as dst:
                        assert con.stdout is not None
                        nbytes = 0
                        while True:
                            b = con.stdout.read(BLOQUE)
                            if not b:
                                break
                            dst.write(b)
                            nbytes += len(b)
                    errb = (con.stderr.read() if con.stderr else b"").decode("utf-8", "replace")
                    rc = con.wait(timeout=TIMEOUT)
                except subprocess.TimeoutExpired:
                    con.kill()
                    con.wait()
                    raise
                t_unar += time.perf_counter() - tu
                if rc != 0 or nbytes != size:
                    base["error"] = f"unar idx={idx} rc={rc} bytes={nbytes} esperado={size}: {(errb or '')[:160]}"
                    _limpiar()
                    return base
        base["t_total_s"] = round(time.perf_counter() - t0, 3)
        base["t_unar_s"] = round(t_unar, 3)
        base["t_zip_s"] = round(base["t_total_s"] - t_unar, 3)
        with zipfile.ZipFile(CBZ) as z:
            zi = {i.filename: i for i in z.infolist() if not i.is_dir()}
            base["entradas_zip"] = len(zi)
            base["testzip"] = z.testzip()
            nombres = set(orig) == set(zi)
            tamanos = all(orig[n][0] == zi[n].file_size for n in set(orig) & set(zi))
            crc = all(orig[n][1] is None or orig[n][1] == zi[n].CRC for n in set(orig) & set(zi))
            base["nombres"], base["tamanos"], base["crc"] = nombres, tamanos, crc
        base["cbz_bytes"] = CBZ.stat().st_size
        base["delta_bytes"] = base["cbz_bytes"] - base["origen_bytes"]
        base["ratio"] = round(base["cbz_bytes"] / base["origen_bytes"], 6)
    except MemoryError:
        base["error"] = "memoria"
    except Exception as e:  # noqa: BLE001 — el JSON debe salir siempre
        base["error"] = f"{type(e).__name__}:{e}"[:200]
    finally:
        base["rss_kib"] = _maxrss()
        base["cgroup_peak_bytes"] = _cgroup_peak()
        _limpiar()
    return base


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: convertir_streaming.py <id>", file=sys.stderr)
        return 2
    res = medir(Path("/samples") / sys.argv[1])
    res["id"] = sys.argv[1]
    print(json.dumps(res, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
