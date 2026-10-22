#!/usr/bin/env python3
# ruff: noqa: E501
"""Banco de evaluación de lectores RAR/CBR (spike #308). Corre DENTRO del contenedor desechable: sin red, muestras montadas en solo lectura (/m).

Por cada muestra y motor (unar, bsdtar, unrar y `rarfile` con cada uno de ellos como backend) mide, en un PROCESO NUEVO por operación:
  listar · primera página · última página · ComicInfo.xml (si existe)
con REPS repeticiones (la primera se anota aparte). Tiempo = segundos de reloj; memoria = pico residente de la herramienta y sus hijos (KiB).
La página sale por la salida estándar y se comprueba que Pillow la decodifica; si una herramienta exige extraer a disco lo hace en /work (tmpfs acotado)
y se anotan los bytes escritos. NO se extrae nunca la muestra entera. Una celda que no se puede medir queda NOT RUN, no se estima.
Variables: REPS (3) · TIMEOUT (60 s) · MOTORES (por defecto todos los disponibles) · SOLO (prefijo de muestra, p. ej. m03).
"""
from __future__ import annotations

import io
import json
import os
import re
import resource
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

M, OUT, WORK = Path("/m"), Path("/out"), Path("/work")
REPS = int(os.environ.get("REPS", "3"))
TIMEOUT = int(os.environ.get("TIMEOUT", "60"))
IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
CONTENEDORES = {".cbz", ".zip", ".cbr", ".rar", ".cb7", ".7z", ".cbt", ".tar", ".epub", ".pdf"}


def natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# ── Modo hijo: mide UNA orden en un proceso nuevo y devuelve JSON por la salida estándar ─────────────
def hijo_medir(cmd: list[str]) -> None:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT)
        rc, stdout, stderr, timeout = p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as e:
        rc, stdout, stderr, timeout = -999, e.stdout or b"", e.stderr or b"", True
    seg = time.time() - t0
    kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    res = {"rc": rc, "seg": round(seg, 3), "pico_kib": kb, "timeout": timeout, "bytes_stdout": len(stdout),
           "stderr": stderr[:160].decode(errors="replace"), "texto": stdout[:600_000].decode(errors="replace") if cmd[0] in LISTAR else ""}
    if stdout and cmd[0] in EXTRAER_STDOUT:
        try:
            from PIL import Image
            with Image.open(io.BytesIO(stdout)) as im:
                im.verify()
            res["pillow"] = True
        except Exception as e:  # noqa: BLE001
            res["pillow"] = False
            res["pillow_error"] = str(e)[:80]
    sys.stdout.write(json.dumps(res))


LISTAR = {"lsar", "bsdtar", "unrar"}
EXTRAER_STDOUT = {"bsdtar", "unrar"}


def medir(cmd: list[str]) -> dict:
    p = subprocess.run([sys.executable, __file__, "--medir", json.dumps(cmd)], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"rc": -998, "error_banco": (p.stderr or p.stdout)[:200]}


def oom_kills() -> int:
    try:
        for linea in Path("/sys/fs/cgroup/memory.events").read_text().splitlines():
            if linea.startswith("oom_kill "):
                return int(linea.split()[1])
    except OSError:
        pass
    return -1


# ── Motores ──────────────────────────────────────────────────────────────────────────────────────────
def entradas(motor: str, texto: str) -> list[str]:
    lineas = [l.rstrip("\r") for l in texto.split("\n") if l.strip()]
    if motor == "unar":
        return lineas[1:]                      # la primera línea de `lsar` es el nombre del archivo
    return lineas


def cmd_listar(motor: str, f: str):
    return {"unar": ["lsar", f], "bsdtar": ["bsdtar", "-tf", f], "unrar": ["unrar", "lb", f]}.get(motor)


def cmd_extraer(motor: str, f: str, entrada: str, indice: int = -1):
    """Los nombres de página llevan a veces corchetes (`[JokerFansub] Página - 00.jpg`): `bsdtar` y `unar` los tratan como COMODINES y no
    encuentran la entrada (error del banco en la primera tanda, no del lector). Por eso: `bsdtar` con los comodines escapados y `unar -i` con el ÍNDICE de la entrada."""
    if motor == "bsdtar":
        return ["bsdtar", "-xOf", f, re.sub(r"([\\\[\]*?])", r"\\\1", entrada)]      # bsdtar 3.6.2 no tiene --no-wildcards: se escapan los comodines (\[ \] \* \? \\)
    if motor == "unrar":
        return ["unrar", "p", "-inul", f, entrada]
    if motor == "unar":                         # `unar` no escribe a la salida estándar: va al tmpfs acotado; la entrada se da por ÍNDICE
        return ["unar", "-q", "-D", "-f", "-i", "-o", str(WORK / "x"), f, str(indice)]
    return None


def hijo_rarfile(motor: str, op: str, f: str, entrada: str) -> None:
    """`rarfile` con UN backend forzado; imprime JSON con el backend realmente usado (versión de rarfile y herramienta)."""
    import rarfile
    t = {"unrar": dict(unrar=True, unar=False, bsdtar=False), "unar": dict(unrar=False, unar=True, bsdtar=False),
         "bsdtar": dict(unrar=False, unar=False, bsdtar=True)}[motor]
    rarfile.tool_setup(force=True, **t)
    res: dict = {"rarfile": rarfile.__version__, "backend_pedido": motor}
    try:
        rf = rarfile.RarFile(f)
        if op == "listar":
            res["texto"] = "\n".join(rf.namelist())
        else:
            data = rf.read(entrada)
            res["bytes_stdout"] = len(data)
            try:
                from PIL import Image
                with Image.open(io.BytesIO(data)) as im:
                    im.verify()
                res["pillow"] = True
            except Exception as e:  # noqa: BLE001
                res["pillow"] = False
                res["pillow_error"] = str(e)[:80]
        res["rc"] = 0
    except Exception as e:  # noqa: BLE001
        res["rc"] = 1
        res["error"] = f"{type(e).__name__}: {str(e)[:100]}"
    sys.stdout.write(json.dumps(res))


def medir_rarfile(motor: str, op: str, f: str, entrada: str) -> dict:
    cmd = [sys.executable, __file__, "--rarfile", motor, op, f, entrada]
    t0 = time.time()
    p = subprocess.run([sys.executable, "-c",
                        "import resource,subprocess,sys,json,time;t=time.time();"
                        "p=subprocess.run(json.loads(sys.argv[1]),capture_output=True,timeout=%d);"
                        "print(json.dumps({'seg':round(time.time()-t,3),'pico_kib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,'rc_proceso':p.returncode,'salida':p.stdout.decode(errors='replace')[:600000],'stderr':p.stderr[:160].decode(errors='replace')}))" % TIMEOUT,
                        json.dumps(cmd)], capture_output=True, text=True)
    try:
        medido = json.loads(p.stdout)
        interno = json.loads(medido["salida"]) if medido["salida"].strip().startswith("{") else {}
    except (json.JSONDecodeError, KeyError):
        return {"rc": -998, "error_banco": (p.stderr or p.stdout)[:200], "seg": round(time.time() - t0, 3)}
    return {**interno, "seg": medido["seg"], "pico_kib": medido["pico_kib"], "rc": interno.get("rc", medido["rc_proceso"]), "stderr": medido["stderr"]}


# ── Muestras ─────────────────────────────────────────────────────────────────────────────────────────
def firma(f: Path) -> str:
    with open(f, "rb") as fh:
        b = fh.read(8)
    if b.startswith(b"Rar!\x1a\x07\x01\x00"):
        return "RAR5"
    if b.startswith(b"Rar!\x1a\x07\x00"):
        return "RAR4 (o anterior)"
    if b[:2] == b"PK":
        return "ZIP"
    if b[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    return "otro/desconocido"


def solido(f: str) -> str:
    if not shutil.which("unrar"):
        return "desconocido (sin unrar)"
    p = subprocess.run(["unrar", "lt", f], capture_output=True, text=True, timeout=TIMEOUT)
    return "sí" if re.search(r"solid", p.stdout, re.I) else ("no" if p.returncode == 0 else "desconocido")


def causa(reps: list[dict], oom_nuevos: bool) -> str:
    """Por qué falló una celda, separando lo que NO es culpa del lector: el límite de memoria, el tiempo o el espacio del directorio temporal."""
    texto = " ".join(str(r.get("stderr") or "") + " " + str(r.get("error") or "") for r in reps).lower()
    if any(r.get("timeout") for r in reps):
        return "TIEMPO (más de %d s)" % TIMEOUT
    if oom_nuevos or any(r.get("rc") in (-9, 137) for r in reps):
        return "MEMORIA (proceso muerto por el límite del contenedor)"
    if "no space left" in texto or "disk full" in texto or "espacio" in texto and "disp" in texto:
        return "LIMITE_TMPFS (sin espacio en /work, no es un fallo del lector)"
    return "LECTOR (la herramienta no pudo leerlo)"


def mediana(xs):
    return statistics.median(xs) if xs else None


def main() -> int:
    muestras = sorted(p for p in M.iterdir() if p.is_file() and (not os.environ.get("SOLO") or p.name.startswith(os.environ["SOLO"])))
    if not muestras:
        print("No hay muestras en /m", file=sys.stderr)
        return 2
    motores = [m for m in ("unar", "bsdtar", "unrar") if shutil.which({"unar": "unar", "bsdtar": "bsdtar", "unrar": "unrar"}[m])]
    pedidos = os.environ.get("MOTORES")
    if pedidos:
        motores = [m for m in motores if m in pedidos.split(",")]
    try:
        import rarfile
        rarfile_v = rarfile.__version__
    except ImportError:
        rarfile_v = None
    filas, ficha = [], []
    for s in muestras:
        f = str(s)
        meta = {"muestra": s.name, "bytes": s.stat().st_size, "firma": firma(s), "solido": solido(f)}
        ficha.append(meta)
        print(f"== {s.name}: {meta['firma']}, {meta['bytes'] / 1e6:.0f} MB, sólido: {meta['solido']}", flush=True)
        for motor in motores + ([f"rarfile+{m}" for m in motores] if rarfile_v else []):
            base = motor.split("+")[-1]
            usa_rarfile = motor.startswith("rarfile+")
            oom0 = oom_kills()
            lista: list[str] = []
            for op in ("listar", "primera", "ultima", "comicinfo"):
                if op == "listar":
                    entrada = ""
                else:
                    imgs = sorted((e for e in lista if Path(e).suffix.lower() in IMG), key=natural)
                    entrada = (imgs[0] if op == "primera" else imgs[-1]) if imgs and op in ("primera", "ultima") else \
                              next((e for e in lista if e.lower().endswith("comicinfo.xml")), "")
                    if not entrada:
                        filas.append({**meta, "motor": motor, "op": op, "estado": "NOT RUN (no hay entrada aplicable)"})
                        continue
                reps = []
                for i in range(REPS):
                    shutil.rmtree(WORK / "x", ignore_errors=True)
                    if usa_rarfile:
                        r = medir_rarfile(base, "listar" if op == "listar" else "leer", f, entrada)
                    elif op == "listar":
                        r = medir(cmd_listar(base, f))
                    else:
                        r = medir(cmd_extraer(base, f, entrada, lista.index(entrada) if entrada in lista else -1))
                        if base == "unar":                      # leer lo que `unar` dejó en el tmpfs
                            escritos = sum(p.stat().st_size for p in (WORK / "x").rglob("*") if p.is_file()) if (WORK / "x").exists() else 0
                            r["bytes_escritos_tmpfs"] = escritos
                            if escritos:
                                from PIL import Image
                                try:
                                    with Image.open(next(p for p in (WORK / "x").rglob("*") if p.is_file())) as im:
                                        im.verify()
                                    r["pillow"] = True
                                except Exception:  # noqa: BLE001
                                    r["pillow"] = False
                    reps.append(r)
                    if op == "listar" and i == 0 and r.get("rc") == 0:
                        lista = entradas("unar" if (base == "unar" and not usa_rarfile) else base, r.get("texto", "")) if not usa_rarfile else \
                                [l for l in r.get("texto", "").split("\n") if l.strip()]
                ok = all(r.get("rc") == 0 for r in reps) and (op in ("listar", "comicinfo") or all(r.get("pillow") for r in reps))
                if op == "listar" and not lista:
                    ok = False                       # rc 0 con 0 entradas no es leer el archivo (p. ej. `unrar lb` sobre un ZIP)
                    reps[0].setdefault("error", "sin entradas (la herramienta no reconoce el contenido)")
                walls = [r.get("seg") for r in reps if r.get("seg") is not None]
                picos = [r.get("pico_kib", 0) / 1024 for r in reps]
                paquete = op == "listar" and any(Path(e).suffix.lower() in CONTENEDORES for e in lista)
                filas.append({**meta, "motor": motor, "op": op, "estado": "PASS" if ok else "FAIL", "causa": "" if ok else causa(reps, oom_kills() > oom0 >= 0), "entrada": entrada[:60] if op != "listar" else f"{len(lista)} entradas",
                              "paquete": paquete, "rc": [r.get("rc") for r in reps], "seg_primera": walls[0] if walls else None,
                              "seg_mediana": mediana(walls), "seg_max": max(walls) if walls else None, "pico_mib_mediana": round(mediana(picos), 1) if picos else None,
                              "pico_mib_max": round(max(picos), 1) if picos else None, "pico_mib_primera": round(picos[0], 1) if picos else None,
                              "error": next((r.get("stderr") or r.get("error") or "" for r in reps if r.get("rc") != 0 or r.get("error")), "")[:100],
                              "timeout": any(r.get("timeout") for r in reps), "escrito_tmpfs": max((r.get("bytes_escritos_tmpfs", 0) for r in reps), default=0)})
                print(f"   {motor:<15}{op:<10}{filas[-1]['estado']:<6}{(filas[-1].get('seg_mediana') or 0):>7.2f} s {(filas[-1].get('pico_mib_max') or 0):>8.1f} MiB", flush=True)
            if oom_kills() > oom0 >= 0:
                filas.append({**meta, "motor": motor, "op": "OOM", "estado": "FAIL", "error": f"el contenedor mató un proceso por memoria ({oom_kills() - oom0} veces)"})
    OUT.mkdir(exist_ok=True)
    (OUT / "resultados.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in filas) + "\n")
    resumen = ["| muestra | firma | sólido | motor | operación | estado | primera (s) | mediana (s) | pico máx. (MiB) | tmpfs (B) | causa del FAIL / nota |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in filas:
        resumen.append(f"| {x['muestra']} | {x['firma']} | {x['solido']} | {x['motor']} | {x['op']} | {x['estado']} | {x.get('seg_primera', '')} | {x.get('seg_mediana', '')} | {x.get('pico_mib_max', '')} | {x.get('escrito_tmpfs', '')} | {(x.get('causa') or x.get('error') or ('paquete' if x.get('paquete') else ''))[:70]} |")
    (OUT / "resumen.md").write_text("\n".join(resumen) + "\n")
    print(f"\nListo: {len(filas)} filas → {OUT}/resultados.jsonl y resumen.md (rarfile {rarfile_v})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--medir":
        hijo_medir(json.loads(sys.argv[2]))
    elif len(sys.argv) > 5 and sys.argv[1] == "--rarfile":
        hijo_rarfile(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "")
    else:
        sys.exit(main())
