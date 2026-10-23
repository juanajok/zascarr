#!/usr/bin/env python3
# ruff: noqa: E501
"""Banco de la SEGUNDA tanda del spike #308 (cierra los NOT RUN de la ficha `evaluacion-lector-rar-2026-10-23.md`).
Corre DENTRO del contenedor desechable: sin red, muestras en solo lectura (/m), kit en /k, tmpfs acotado en /work. Solo `unar`/`lsar` (candidata) y `unrar` (comparación).

Modos (variable MODOS, por defecto todos):
  integridad  la página que sale es de verdad la del archivo: tamaño y CRC32 contra el LISTADO (`lsar -j`) y `Image.load()` (decodifica todos los píxeles; la 1ª tanda solo usó `verify()`).
  corrupto    copias DAÑADAS (truncada, cabecera cortada, un byte cambiado en cabecera/medio/final, 4 KiB a cero): ¿error claro, o cuelgue/caída/memoria/datos erróneos en silencio?
  topes       coste del listado con tamaños (para fijar topes ANTES de extraer) y topes que se pueden poner DESDE FUERA (tamaño de fichero, memoria, tiempo) porque `unar` no tiene opciones.
  cifrado     RAR cifrados (si el censo encontró alguno): no debe colgarse pidiendo contraseña.
  comicinfo   ¿hay `ComicInfo.xml`, y se puede leer y parsear?
Una celda que no se puede medir queda NOT RUN: nunca se estima. Las muestras reales no se modifican: los daños se aplican a una COPIA en /work.
Variables: MODOS · TIMEOUT (60 s) · SOLO (prefijo de muestra). NO se extrae nunca una muestra entera: solo páginas sueltas.
"""
from __future__ import annotations

import io
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import censo_cabeceras_rar as censo  # noqa: E402

M, OUT, WORK = Path("/m"), Path("/out"), Path("/work")
TIMEOUT = int(os.environ.get("TIMEOUT", "60"))
IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
CONTENEDORES = {".cbz", ".zip", ".cbr", ".rar", ".cb7", ".7z", ".cbt", ".tar", ".epub", ".pdf"}


def natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# ── Ejecutar una orden en un proceso nuevo y medirla ────────────────────────────────────────────────
def hijo_ejecutar(cmd: list[str], timeout: float, rlimits: dict[str, int], stdout_a: str | None) -> None:
    """Corre UNA orden con stdin cerrado (nada puede quedarse esperando una contraseña), en su propio grupo de procesos, con los límites pedidos."""
    def previo():
        signal.signal(signal.SIGXFSZ, signal.SIG_DFL)      # Python ignora SIGXFSZ y los hijos lo heredan: sin esto un exceso de tamaño no mataría a la herramienta
        for nombre, v in rlimits.items():
            resource.setrlimit(getattr(resource, nombre), (v, v))

    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=previo, start_new_session=True)
    vencido = False
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        vencido = True
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = p.communicate()
    seg = time.time() - t0
    if stdout_a:
        Path(stdout_a).write_bytes(out)
    sys.stdout.write(json.dumps({"rc": p.returncode, "seg": round(seg, 3), "pico_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, "timeout": vencido,
                                 "bytes_stdout": len(out), "stderr": err[:300].decode(errors="replace"),
                                 "stdout_cabeza": "" if stdout_a else out[:300].decode(errors="replace")}))     # `unar` escribe sus mensajes en la salida estándar


def ejecutar(cmd: list[str], timeout: float = TIMEOUT, rlimits: dict[str, int] | None = None, stdout_a: str | None = None) -> dict:
    p = subprocess.run([sys.executable, __file__, "--ejecutar", json.dumps([cmd, timeout, rlimits or {}, stdout_a])], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"rc": -998, "seg": 0, "pico_kib": 0, "timeout": False, "bytes_stdout": 0, "stderr": "error del banco: " + (p.stderr or p.stdout)[:200]}


def oom_kills() -> int:
    try:
        for linea in Path("/sys/fs/cgroup/memory.events").read_text().splitlines():
            if linea.startswith("oom_kill "):
                return int(linea.split()[1])
    except OSError:
        pass
    return -1


# ── Funciones puras (con pruebas en tests/test_banco_rar2.py) ──────────────────────────────────────
@dataclass(frozen=True)
class Entrada:
    indice: int
    nombre: str
    tam: int | None
    directorio: bool
    cifrada: bool | None
    crc: int | None
    comprimido: int | None = None


def _entero(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def parsear_lsar_json(texto: str) -> tuple[list[Entrada], dict]:
    """Interpreta `lsar -j`. Claves usadas (de The Unarchiver): XADFileName, XADFileSize, XADIsDirectory, XADIsEncrypted, XADIndex y cualquiera que contenga «CRC».
    Devuelve (entradas, meta); `meta["claves"]` lista las claves de la primera entrada para dejar constancia del esquema real."""
    d = json.loads(texto)
    crudas = d.get("lsarContents") or []
    out: list[Entrada] = []
    for i, e in enumerate(crudas):
        crc = next((v for k, v in e.items() if "crc" in k.lower() and _entero(v) is not None), None)
        idx = _entero(e.get("XADIndex"))
        out.append(Entrada(idx if idx is not None else i, str(e.get("XADFileName", "")), _entero(e.get("XADFileSize")),
                           bool(e.get("XADIsDirectory", False)), e.get("XADIsEncrypted") if isinstance(e.get("XADIsEncrypted"), bool) else None, crc, _entero(e.get("XADCompressedSize"))))
    meta = {"formato": d.get("lsarFormatName"), "claves": sorted(crudas[0].keys()) if crudas else []}
    return out, meta


def paginas(entradas: list[Entrada]) -> tuple[Entrada | None, Entrada | None]:
    imgs = sorted((e for e in entradas if not e.directorio and Path(e.nombre).suffix.lower() in IMG), key=lambda e: natural(e.nombre))
    return (imgs[0], imgs[-1]) if imgs else (None, None)


def validar(data: bytes, e: Entrada) -> dict:
    """La página es buena si: tiene el tamaño del listado, su CRC32 coincide (si el listado lo trae) y Pillow la DECODIFICA entera (`load()`)."""
    r: dict = {"bytes": len(data), "tam_ok": e.tam is None or len(data) == e.tam,
               "crc_ok": None if e.crc is None else (zlib.crc32(data) & 0xFFFFFFFF) == e.crc}
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            r["dim"] = list(im.size)
        r["decodifica"] = True
    except Exception as ex:  # noqa: BLE001
        r["decodifica"] = False
        r["error_pillow"] = str(ex)[:80]
    r["ok"] = bool(r["decodifica"] and r["tam_ok"] and r["crc_ok"] is not False)
    return r


def clasificar_salida(r: dict, valida: bool, oom: bool = False, hay_datos: bool = True) -> str:
    """Qué pasó con una orden sobre un fichero posiblemente dañado o cifrado."""
    if r.get("timeout"):
        return "TIMEOUT"
    if oom or r.get("rc") in (-9, 137):
        return "OOM"
    rc = r.get("rc", -998)
    if rc in (-998, -997):
        return "ERROR_DEL_BANCO"
    if rc < 0 or rc >= 128:
        return f"CRASH (señal {abs(rc) if rc < 0 else rc - 128})"
    if rc == 0:
        if not hay_datos:
            return "SIN_SALIDA_CON_RC_0 (dice que fue bien y no escribió nada)"
        return "OK_SIN_DANO_EN_LA_PAGINA" if valida else "SILENCIOSO (rc 0 con página no válida)"
    return "ERROR_CLARO" if mensaje(r) else "ERROR_SIN_MENSAJE"


def mensaje(r: dict) -> str:
    """El texto con que la herramienta explica un fallo: lo que haya en la salida de errores o, si no, el principio de la salida estándar (`unar`)."""
    return ((r.get("stderr") or "").strip() or (r.get("stdout_cabeza") or "").strip())[:110]


ACEPTABLES = ("OK_SIN_DANO_EN_LA_PAGINA", "ERROR_CLARO", "SIN_PAGINA_QUE_PEDIR")
GRAVEDAD = ("CRASH", "TIMEOUT", "OOM", "ERROR_DEL_BANCO", "SILENCIOSO", "SIN_SALIDA", "ERROR_SIN_MENSAJE", "ERROR_CLARO", "SIN_PAGINA", "OK")


def peor(clases: list[str]) -> str:
    """La peor de varias clases de salida (la más arriba en GRAVEDAD)."""
    return min(clases, key=lambda c: next((i for i, g in enumerate(GRAVEDAD) if c.startswith(g)), len(GRAVEDAD)))


def offset_en_pagina(entradas: list[Entrada], k: int, cabecera_estimada: int = 64) -> int:
    """Posición aproximada, en un archivo SIN sólido, de la MITAD de los datos comprimidos de la entrada k (orden del listado = orden en el fichero).
    Estima 64 B de cabecera por entrada más el nombre; el error acumulado es de KB frente a páginas de cientos de KB."""
    pos = 20                                                  # firma + cabecera principal
    for e in entradas[:k]:
        pos += cabecera_estimada + len(e.nombre) + (e.comprimido or 0)
    e = entradas[k]
    return pos + cabecera_estimada + len(e.nombre) + (e.comprimido or 0) // 2


def variantes(n: int) -> list[tuple[str, str, int]]:
    """(nombre, tipo, parámetro) de los daños aplicados a una COPIA de n bytes. Posiciones deterministas."""
    return [("truncado_50", "truncar", n // 2), ("truncado_cabecera", "truncar", 64), ("byte_cabecera", "byte", min(24, n - 1)),
            ("byte_medio", "byte", n // 2), ("ceros_medio", "ceros", n // 2), ("byte_final", "byte", max(0, n - 16))]


def danar(origen: Path, destino: Path, tipo: str, param: int) -> None:
    shutil.copyfile(origen, destino)
    if tipo == "truncar":
        os.truncate(destino, param)
        return
    with open(destino, "r+b") as fh:
        fh.seek(param)
        if tipo == "byte":
            b = fh.read(1)
            fh.seek(param)
            fh.write(bytes([(b[0] ^ 0xFF) if b else 0xFF]))
        elif tipo == "ceros":
            fh.write(b"\0" * 4096)


# ── Herramientas ─────────────────────────────────────────────────────────────────────────────────────
def listar(f: str, extra: dict | None = None) -> tuple[list[Entrada], dict, dict]:
    r = ejecutar(["lsar", "-j", f], stdout_a=str(WORK / "lsar.json"), **(extra or {}))
    entradas, meta = [], {}
    if r["rc"] != 0 and not (r.get("stderr") or "").strip():          # con `-j` la salida (también el mensaje de error) va al fichero redirigido
        try:
            r["stderr"] = (WORK / "lsar.json").read_text(errors="replace")[:300]
        except OSError:
            pass
    if r["rc"] == 0:
        try:
            entradas, meta = parsear_lsar_json((WORK / "lsar.json").read_text(errors="replace"))
        except (json.JSONDecodeError, OSError) as ex:
            r["stderr"] = f"JSON ilegible: {ex}"[:200]
            r["rc"] = -997
    return entradas, meta, r


def extraer(motor: str, f: str, e: Entrada, timeout: float = TIMEOUT, rlimits: dict[str, int] | None = None) -> tuple[dict, bytes | None]:
    shutil.rmtree(WORK / "x", ignore_errors=True)
    (WORK / "p.bin").unlink(missing_ok=True)
    if motor == "unar":
        r = ejecutar(["unar", "-D", "-f", "-i", "-o", str(WORK / "x"), f, str(e.indice)], timeout, rlimits)
        ficheros = [p for p in (WORK / "x").rglob("*") if p.is_file()] if (WORK / "x").exists() else []
        r["bytes_escritos_tmpfs"] = sum(p.stat().st_size for p in ficheros)
        return r, (ficheros[0].read_bytes() if ficheros else None)
    r = ejecutar(["unrar", "p", "-idq", "-p-", f, e.nombre], timeout, rlimits, stdout_a=str(WORK / "p.bin"))
    p = WORK / "p.bin"
    return r, (p.read_bytes() if p.exists() else None)


def fila(modo: str, muestra: str, variante: str, motor: str, op: str, resultado: str, estado: str, r: dict | None = None, detalle: str = "") -> dict:
    r = r or {}
    return {"modo": modo, "muestra": muestra, "variante": variante, "motor": motor, "op": op, "resultado": resultado, "estado": estado, "seg": r.get("seg"),
            "pico_mib": round(r["pico_kib"] / 1024, 1) if r.get("pico_kib") else None, "rc": r.get("rc"), "tmpfs_b": r.get("bytes_escritos_tmpfs"),
            "detalle": (detalle or mensaje(r))[:110].replace("\n", " ").replace("|", "/")}


FILAS: list[dict] = []


def anotar(x: dict) -> None:
    FILAS.append(x)
    print(f"   {x['modo']:<10}{x['muestra']:<5}{x['variante']:<19}{x['motor']:<6}{x['op']:<9}{x['estado']:<8}{x['resultado'][:46]}", flush=True)


def muestras_rar() -> list[tuple[Path, censo.Cabecera]]:
    solo = os.environ.get("SOLO")
    out = []
    for p in sorted(x for x in M.iterdir() if x.is_file() and (not solo or x.name.startswith(solo))):
        with open(p, "rb") as fh:
            c = censo.clasificar(fh.read(censo.LEER))
        if c.firma.startswith("RAR"):
            out.append((p, c))
    return out


# ── Modos ────────────────────────────────────────────────────────────────────────────────────────────
def modo_integridad(ms) -> None:
    print("== integridad (tamaño, CRC y Image.load())", flush=True)
    esquema_dicho = False
    for p, _c in ms:
        entradas, meta, r = listar(str(p))
        if not esquema_dicho and meta:
            print(f"   esquema de lsar -j: formato={meta['formato']} claves={meta['claves']}", flush=True)
            FILAS.append({"modo": "integridad", "muestra": p.name, "variante": "", "motor": "lsar", "op": "esquema", "resultado": json.dumps(meta, ensure_ascii=False), "estado": "INFO"})
            esquema_dicho = True
        if r["rc"] != 0:
            anotar(fila("integridad", p.name, "", "lsar", "listar", "FAIL", "FAIL", r))
            continue
        if any(Path(e.nombre).suffix.lower() in CONTENEDORES for e in entradas):
            anotar(fila("integridad", p.name, "", "lsar", "paginas", "NOT RUN (paquete)", "NOT RUN", detalle="contiene contenedores"))
            continue
        pr, ul = paginas(entradas)
        if not pr:
            anotar(fila("integridad", p.name, "", "lsar", "paginas", "NOT RUN (sin imágenes)", "NOT RUN"))
            continue
        for motor in ("unar", "unrar"):
            for op, e in (("primera", pr), ("ultima", ul)):
                r, data = extraer(motor, str(p), e)
                v = validar(data, e) if data else {"ok": False, "error_pillow": "sin datos"}
                res = f"tam_ok={v.get('tam_ok')} crc={'sin CRC' if v.get('crc_ok') is None else v.get('crc_ok')} decodifica={v.get('decodifica')}"
                anotar(fila("integridad", p.name, "", motor, op, res, "PASS" if (r["rc"] == 0 and v["ok"]) else "FAIL", r))


def _bases_para_danar(ms):
    pequenas = [(p, c) for p, c in ms if p.stat().st_size <= 80 << 20]
    elegidas: dict[str, tuple[Path, censo.Cabecera]] = {}
    for p, c in pequenas:
        clave = "sólido" if c.solido else c.firma
        elegidas.setdefault(clave, (p, c))
    return list(elegidas.values())


def _evaluar(motor: str, f: str, e_danada: Entrada, e_original: Entrada) -> tuple[str, dict]:
    """Pide una página a un fichero posiblemente dañado y la compara con la ORIGINAL (tamaño, CRC, decodificación)."""
    oom0 = oom_kills()
    r, data = extraer(motor, f, e_danada)
    hay = bool(data)
    valida = validar(data, e_original)["ok"] if hay else False
    return clasificar_salida(r, valida, oom=oom_kills() > oom0 >= 0, hay_datos=hay), r


def modo_corrupto(ms) -> None:
    """Como lo haría ZascArr: se LISTA el fichero dañado y se pide LA PÁGINA QUE EL LISTADO DIGA (no el índice del original). Se compara con la página original."""
    print("== corrupto (copias dañadas en /work; las muestras no se tocan)", flush=True)
    for p, c in _bases_para_danar(ms):
        entradas, _meta, r = listar(str(p))
        imgs = sorted((e for e in entradas if not e.directorio and Path(e.nombre).suffix.lower() in IMG), key=lambda e: natural(e.nombre))
        if r["rc"] != 0 or len(imgs) < 3:
            anotar(fila("corrupto", p.name, "", "lsar", "base", "NOT RUN (la muestra base no se lista o tiene menos de 3 páginas)", "NOT RUN", r))
            continue
        orig = {e.nombre: e for e in entradas}
        k = len(imgs) // 2
        pos_k = offset_en_pagina(entradas, entradas.index(imgs[k])) if not c.solido else None
        plan = [(n, t, q, "extremos") for n, t, q in variantes(p.stat().st_size)]
        if pos_k is not None:
            plan += [("byte_en_pagina", "byte", pos_k, "ventana"), ("ceros_en_pagina", "ceros", pos_k, "ventana")]
        tag = f"{p.name}:{'sólido' if c.solido else c.firma}"
        for nombre, tipo, param, objetivo in plan:
            v = WORK / "v.rar"
            danar(p, v, tipo, param)
            oom0 = oom_kills()
            ent2, _m2, r2 = listar(str(v))
            res = clasificar_salida(r2, valida=True, oom=oom_kills() > oom0 >= 0)
            anotar(fila("corrupto", tag, nombre, "lsar", "listar", res.replace("OK_SIN_DANO_EN_LA_PAGINA", "LISTADO_CON_RC_0"), "PASS" if res in ACEPTABLES else "FAIL", r2,
                        f"{len(ent2)} de {len(entradas)} entradas" + (" (¡faltan! y el código de salida no lo avisa)" if r2["rc"] == 0 and len(ent2) < len(entradas) else "")))
            if objetivo == "extremos":
                pr2, ul2 = paginas(ent2)
                pedidas = [("primera", pr2), ("ultima", ul2)]
            else:
                por_nombre = {e.nombre: e for e in ent2}
                pedidas = [(f"pag{i}", por_nombre.get(imgs[i].nombre)) for i in range(max(0, k - 2), min(len(imgs), k + 3))]
            for motor in ("unar", "unrar"):
                clases, medidas, ok = [], [], 0
                for op, e2 in pedidas:
                    if e2 is None:
                        clases.append("SIN_PAGINA_QUE_PEDIR")
                        medidas.append({})
                        continue
                    cl, r_pag = _evaluar(motor, str(v), e2, orig.get(e2.nombre, e2))
                    clases.append(cl)
                    medidas.append(r_pag)
                    ok += cl.startswith("OK")
                ultima_r = next((m for m in reversed(medidas) if m), {})
                if objetivo == "extremos":
                    for (op, _e), cl, m in zip(pedidas, clases, medidas):
                        anotar(fila("corrupto", tag, nombre, motor, op, cl, "PASS" if cl in ACEPTABLES else "FAIL", m))
                else:
                    res = f"peor: {peor(clases)} ({ok} de {len(clases)} páginas bien; {sum(c2.startswith('ERROR_CLARO') for c2 in clases)} con error claro; {sum(e is None for _o, e in pedidas)} ausentes del listado)"
                    anotar(fila("corrupto", tag, nombre, motor, "ventana", res, "PASS" if peor(clases) in ACEPTABLES or peor(clases).startswith("OK") else "FAIL", ultima_r))
            v.unlink(missing_ok=True)


def _procesos_vivos(nombre: str) -> int:
    n = 0
    for d in Path("/proc").iterdir():
        if d.name.isdigit():
            try:
                if nombre in (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").split(" ")[0]:
                    n += 1
            except OSError:
                pass
    return n


def modo_topes(ms) -> None:
    print("== topes (listado con tamaños y límites desde fuera)", flush=True)
    for p, _c in ms:
        entradas, _meta, r = listar(str(p))
        declarado = sum(e.tam or 0 for e in entradas)
        mayor = max((e.tam or 0 for e in entradas), default=0)
        anotar(fila("topes", p.name, "", "lsar", "listado", f"{len(entradas)} entradas; declarado {declarado >> 20} MiB; la mayor {mayor >> 10} KiB",
                    "PASS" if r["rc"] == 0 and (not entradas or any(e.tam is not None for e in entradas)) else "FAIL", r))
    sol = next(((p, c) for p, c in ms if c.solido), None) or (max(ms, key=lambda t: t[0].stat().st_size) if ms else None)
    if not sol:
        anotar(fila("topes", "-", "", "-", "limites", "NOT RUN (sin muestras)", "NOT RUN"))
        return
    p, c = sol
    entradas, _m, r = listar(str(p))
    _pr, ul = paginas(entradas)
    if not ul:
        anotar(fila("topes", p.name, "", "-", "limites", "NOT RUN (sin página)", "NOT RUN"))
        return
    nota = "sólido" if c.solido else "no hay muestra sólida: se usa la mayor"
    tam = ul.tam or 65536
    # 1) tamaño máximo de fichero escrito
    tope = max(4096, tam // 4)
    r1, _ = extraer("unar", str(p), ul, rlimits={"RLIMIT_FSIZE": tope})
    escrito = r1.get("bytes_escritos_tmpfs", 0)
    anotar(fila("topes", p.name, f"FSIZE={tope}B", "unar", "ultima", f"rc={r1['rc']}; escribió {escrito} B (tope {tope}); {nota}", "PASS" if (r1["rc"] != 0 and escrito <= tope and not r1["timeout"]) else "FAIL", r1))
    # 2) memoria virtual máxima
    r2, d2 = extraer("unar", str(p), ul, rlimits={"RLIMIT_AS": 96 << 20})
    cl2 = clasificar_salida(r2, valida=bool(d2), hay_datos=bool(d2))
    util = d2 is not None and r2["rc"] == 0
    anotar(fila("topes", p.name, "AS=96MiB", "unar", "ultima", f"{cl2}; {'página entera' if d2 else 'sin página'}; {nota}" + ("" if util else " → RLIMIT_AS NO sirve como tope: usar el límite de memoria del contenedor"),
                "PASS" if util else "INFO", r2, "informativo: la memoria virtual de unar es muy superior a la residente"))
    # 3) tiempo: orden vencida y sin procesos huérfanos
    r3, _ = extraer("unar", str(p), ul, timeout=0.01)
    time.sleep(0.3)
    vivos = _procesos_vivos("unar")
    anotar(fila("topes", p.name, "timeout=0,01s", "unar", "ultima", f"vencida={r3['timeout']}; procesos «unar» vivos después: {vivos}", "PASS" if (r3["timeout"] and vivos == 0) else "FAIL", r3))
    anotar(fila("topes", "-", "bomba", "-", "descompresion", "NOT RUN (no hay con qué crear un RAR-bomba y no se fabrica uno)", "NOT RUN"))


def modo_cifrado(ms) -> None:
    print("== cifrado", flush=True)
    cif = [(p, c) for p, c in ms if c.cifrado in ("cabeceras", "archivos")]
    if not cif:
        anotar(fila("cifrado", "-", "", "-", "-", "NOT RUN (el censo no encontró ningún RAR cifrado entre las muestras)", "NOT RUN"))
        return
    for p, c in cif:
        entradas, _m, r = listar(str(p))
        res = clasificar_salida(r, valida=True)
        if res.startswith("OK") and not entradas:
            res = "LISTADO_VACIO_CON_RC_0 (no se ve dentro y no lo dice)"
        elif res.startswith("OK"):
            res = "LISTADO_CON_RC_0"
        anotar(fila("cifrado", p.name, c.cifrado, "lsar", "listar", res, "PASS" if (res.startswith(("ERROR_CLARO", "LISTADO")) and not r["timeout"]) else "FAIL", r, f"{len(entradas)} entradas"))
        pr, _ul = paginas(entradas)
        for motor in ("unar", "unrar"):
            if not pr:
                anotar(fila("cifrado", p.name, c.cifrado, motor, "primera", "NOT RUN (no se ve ninguna página sin contraseña)", "NOT RUN"))
                continue
            r2, data = extraer(motor, str(p), pr)
            res = clasificar_salida(r2, valida=bool(data and validar(data, pr)["ok"]))
            anotar(fila("cifrado", p.name, c.cifrado, motor, "primera", res, "PASS" if (res in ACEPTABLES and not r2["timeout"]) else "FAIL", r2))


def modo_comicinfo(ms) -> None:
    print("== comicinfo", flush=True)
    import xml.etree.ElementTree as ET
    hay = 0
    for p, _c in ms:
        entradas, _m, r = listar(str(p))
        ci = next((e for e in entradas if Path(e.nombre).name.lower() == "comicinfo.xml"), None)
        if not ci:
            continue
        hay += 1
        r2, data = extraer("unar", str(p), ci)
        try:
            raiz = ET.fromstring(data or b"")
            campos = sorted({h.tag for h in raiz})[:8]
            anotar(fila("comicinfo", p.name, "", "unar", "leer", f"raíz={raiz.tag}; {len(data)} B; campos: {','.join(campos)}", "PASS" if r2["rc"] == 0 else "FAIL", r2))
        except ET.ParseError as ex:
            anotar(fila("comicinfo", p.name, "", "unar", "leer", f"XML ilegible: {ex}"[:80], "FAIL", r2))
    if not hay:
        anotar(fila("comicinfo", "-", "", "-", "-", f"NOT RUN (ninguna de las {len(ms)} muestras RAR trae ComicInfo.xml)", "NOT RUN"))
    else:
        print(f"   {hay} de {len(ms)} muestras RAR traen ComicInfo.xml", flush=True)


MODOS = {"integridad": modo_integridad, "corrupto": modo_corrupto, "topes": modo_topes, "cifrado": modo_cifrado, "comicinfo": modo_comicinfo}


def main() -> int:
    ms = muestras_rar()
    if not ms:
        print("No hay muestras RAR en /m", file=sys.stderr)
        return 2
    for n in ("lsar", "unar", "unrar"):
        if not shutil.which(n):
            print(f"Falta {n} en la imagen", file=sys.stderr)
            return 2
    print(f"{len(ms)} muestras RAR: " + ", ".join(f"{p.name}({c.firma}{', sólido' if c.solido else ''}{', cifrado' if c.cifrado in ('cabeceras', 'archivos') else ''})" for p, c in ms), flush=True)
    for m in (os.environ.get("MODOS") or ",".join(MODOS)).split(","):
        oom0 = oom_kills()
        MODOS[m.strip()](ms)
        if oom_kills() > oom0 >= 0:
            FILAS.append({"modo": m, "muestra": "-", "variante": "", "motor": "-", "op": "OOM", "resultado": f"el contenedor mató {oom_kills() - oom0} procesos por memoria", "estado": "FAIL"})
    OUT.mkdir(exist_ok=True)
    (OUT / "resultados2.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in FILAS) + "\n")
    md = ["| modo | muestra | variante | motor | operación | resultado | estado | s | pico MiB | detalle |", "|---|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {x['modo']} | {x['muestra']} | {x['variante']} | {x['motor']} | {x['op']} | {x['resultado']} | {x['estado']} | {x.get('seg', '')} | {x.get('pico_mib', '')} | {x.get('detalle', '')} |" for x in FILAS]
    (OUT / "resumen2.md").write_text("\n".join(md) + "\n")
    c = {}
    for x in FILAS:
        c[x["estado"]] = c.get(x["estado"], 0) + 1
    print(f"\nListo: {len(FILAS)} filas {c} → {OUT}/resultados2.jsonl y resumen2.md")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--ejecutar":
        hijo_ejecutar(*json.loads(sys.argv[2]))
    else:
        sys.exit(main())
