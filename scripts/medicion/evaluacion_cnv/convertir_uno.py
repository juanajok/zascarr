#!/usr/bin/env python3
"""Convierte y verifica UNA copia CBR dentro de un contenedor desechable (BL-CNV0).

Se ejecuta con `/samples/<id>` montado en solo lectura; escribe resultados JSON por stdout.
No abre la biblioteca: solo la copia que recibe. Usa `unar` + `zipfile(ZIP_STORED)` y
comprueba nombres, tamaños y CRC contra `lsar`; después `testzip`.
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
OUT = WORK / "out"
CBZ = WORK / "out.cbz"
TIMEOUT = 600


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
                           capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {}, "timeout"
    if r.returncode != 0:
        return {}, (r.stderr or r.stdout or "error").strip()[:200]
    try:
        return json.loads(r.stdout), ""
    except json.JSONDecodeError:
        return {}, "json"


def _entradas_lsar(doc: dict) -> dict[str, tuple[int, int | None]]:
    out: dict[str, tuple[int, int | None]] = {}
    for e in doc.get("lsarContents", []) or []:
        if not isinstance(e, dict):
            continue
        n = e.get("XADFileName")
        if not isinstance(n, str):
            continue
        n = n.replace("\\", "/").lstrip("./")
        if n.endswith("/"):
            continue
        size = e.get("XADFileSize")
        crc = e.get("RARCRC32")
        if not isinstance(size, int):
            continue  # directorio RAR (sin tamaño): no es un fichero del manifiesto
        if size == 0 and crc in (0, None):
            continue
        out[n] = (size, int(crc) if isinstance(crc, int) else None)
    return out


def _bytes_en(p: Path) -> tuple[int, int]:
    total = n = 0
    for raiz, _dirs, ficheros in os.walk(p):
        for f in ficheros:
            q = Path(raiz) / f
            try:
                total += q.stat().st_size
                n += 1
            except OSError:
                pass
    return total, n


def _limpiar() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    try:
        CBZ.unlink()
    except OSError:
        pass


def medir(src: Path, *, tipo_zip: bool) -> dict:
    base = {
        "tipo": "zip_renombrado" if tipo_zip else "rar_a_cbz",
        "origen_bytes": src.stat().st_size,
        "t_unar_s": None, "t_zip_s": None, "t_total_s": None,
        "cbz_bytes": None, "delta_bytes": None, "ratio": None,
        "entradas_lsar": None, "entradas_zip": None, "tmp_bytes": None,
        "rss_kib": None, "cgroup_peak_bytes": None,
        "testzip": None, "nombres": None, "tamanos": None, "crc": None,
        "error": None,
    }
    _limpiar()
    WORK.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    try:
        if tipo_zip:
            shutil.copyfile(src, CBZ)
            base["t_total_s"] = round(time.perf_counter() - t0, 3)
        else:
            doc, err = _lsar(src)
            if err:
                base["error"] = "lsar:" + err
                return base
            orig = _entradas_lsar(doc)
            base["entradas_lsar"] = len(orig)
            OUT.mkdir()
            tu = time.perf_counter()
            r = subprocess.run(["unar", "-q", "-f", "-D", "-o", str(OUT), str(src)],
                               capture_output=True, text=True, timeout=TIMEOUT)
            base["t_unar_s"] = round(time.perf_counter() - tu, 3)
            if r.returncode != 0:
                base["error"] = "unar:" + (r.stderr or r.stdout or str(r.returncode)).strip()[:200]
                return base
            tmp_bytes, _tmp_n = _bytes_en(OUT)
            base["tmp_bytes"] = tmp_bytes
            tz = time.perf_counter()
            with zipfile.ZipFile(CBZ, "w", compression=zipfile.ZIP_STORED) as z:
                for raiz, _dirs, ficheros in os.walk(OUT):
                    for f in sorted(ficheros):
                        q = Path(raiz) / f
                        arc = q.relative_to(OUT).as_posix()
                        z.write(q, arc)
            base["t_zip_s"] = round(time.perf_counter() - tz, 3)
            base["t_total_s"] = round(time.perf_counter() - t0, 3)
            with zipfile.ZipFile(CBZ) as z:
                zi = {i.filename: i for i in z.infolist() if not i.is_dir()}
                base["entradas_zip"] = len(zi)
                base["testzip"] = z.testzip()
                nombres = set(orig) == set(zi)
                tamanos = all(orig[n][0] == zi[n].file_size for n in set(orig) & set(zi))
                crc = all(orig[n][1] is None or orig[n][1] == zi[n].CRC for n in set(orig) & set(zi))
                base["nombres"], base["tamanos"], base["crc"] = nombres, tamanos, crc
        base["cbz_bytes"] = CBZ.stat().st_size if CBZ.exists() else None
        if base["cbz_bytes"] is not None:
            base["delta_bytes"] = base["cbz_bytes"] - base["origen_bytes"]
            base["ratio"] = round(base["cbz_bytes"] / base["origen_bytes"], 6)
        if base["tipo"] == "zip_renombrado":
            with zipfile.ZipFile(CBZ) as z:
                base["entradas_zip"] = len([i for i in z.infolist() if not i.is_dir()])
                base["testzip"] = z.testzip()
                base["nombres"] = base["tamanos"] = base["crc"] = True
    except subprocess.TimeoutExpired:
        base["error"] = "timeout"
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
    if len(sys.argv) != 3:
        print("uso: convertir_uno.py <id> <tipo rar|zip>", file=sys.stderr)
        return 2
    sid, tipo = sys.argv[1], sys.argv[2]
    src = Path("/samples") / sid
    res = medir(src, tipo_zip=(tipo == "zip"))
    res["id"] = sid
    print(json.dumps(res, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
