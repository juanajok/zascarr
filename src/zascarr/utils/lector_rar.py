# ruff: noqa: E501
"""
Lector de RAR por subproceso (`lsar` / `unar`) — #418 (BL-PORT3), compartido con #344.

Es un envoltorio SIN dominio de portadas: lista un archivo y lee UNA entrada ya verificada. Quién
elige la página, la recorta o recuerda un fallo es cosa de quien lo llama. Reglas (spec BL-PORT3
FR-02..FR-09 y evaluación de `unar` de #308):

- Sin shell: argumentos en lista, ruta absoluta del ejecutable, entorno mínimo con un `HOME` dentro
  del directorio temporal propio.
- Grupo de procesos propio, con tiempo máximo (se mata el grupo entero) y vigilancia del tamaño de lo
  escrito; tope de `stdout`/`stderr`. NO se usa `RLIMIT_AS` (mata a `unar`: SIGSEGV con 96 MiB).
- Un código de salida 0 no prueba nada (`lsar` lista un truncado y `unar` sale 0 sin escribir):
  la entrada extraída se verifica por tamaño y CRC32 contra el listado.
- Se extrae por ÍNDICE, nunca por nombre (los nombres llevan corchetes, que `unar` toma por
  comodines) y a un directorio temporal vacío que se borra siempre. El original no se toca.
- Un solo lector vivo en todo el proceso (`RAR_SIMULTANEOS`): 25,8 MiB por proceso en una Pi de
  512 MB compartida.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from zascarr.models import MotivoRar

#: Topes de lectura (spec §5.3). Los máximos observados en #308 fueron 324 entradas y 221 MiB.
RAR_MAX_ENTRADAS = 1000
RAR_MAX_BYTES_DECLARADOS = 500 * 1024 * 1024
RAR_MAX_SALIDA_LISTADO = 4 * 1024 * 1024
RAR_MAX_SALIDA_ERROR = 64 * 1024
RAR_TIMEOUT_LISTAR_S = 15.0
RAR_TIMEOUT_EXTRAER_S = 10.0
RAR_SIMULTANEOS = 1
#: Tope de memoria residente del lector (proceso y descendientes), vigilado en el bucle de 20 ms: sin
#: `RLIMIT_AS` (rompe `unar`), un diccionario hostil de RAR 5 podría dejar al OOM del contenedor elegir
#: víctima entre `unar` y la app. El máximo medido en #308 fue 25,8 MiB (dictamen SecOps M-1).
RAR_MAX_RSS = 128 * 1024 * 1024
#: Cuánto espera un hilo su turno de lector antes de rendirse (`OCUPADO`): sin tope, una rejilla fría
#: de portadas RAR dejaría los hilos del ejecutor esperando el semáforo (dictamen SecOps M-2).
RAR_ESPERA_TURNO_S = 2.5

#: Un listado vacío de un archivo mayor que esto no es «sin entradas» sino un archivo truncado.
_UMBRAL_LISTADO_VACIO = 1024 * 1024
_ENTORNO_PATH = "/usr/bin:/bin"
_SONDEO_S = 0.02

_SEMAFORO = threading.BoundedSemaphore(RAR_SIMULTANEOS)


class ErrorRar(Exception):  # noqa: N818
    """Un RAR no se pudo listar o leer. `motivo` es la causa, de dominio; el mensaje nunca lleva
    rutas ni nombres de archivo."""

    def __init__(self, motivo: MotivoRar) -> None:
        super().__init__(motivo.value)
        self.motivo = motivo


@dataclass(frozen=True)
class EntradaRar:
    indice: int
    nombre: str
    tamano: int
    crc32: int | None
    es_directorio: bool
    cifrada: bool


@dataclass(frozen=True)
class Listado:
    entradas: tuple[EntradaRar, ...]


def _localizar(nombre: str) -> str | None:
    ruta = shutil.which(nombre)
    return str(Path(ruta).resolve()) if ruta else None


def disponible() -> bool:
    """¿Están `lsar` y `unar` en el sistema? No lanza nada."""
    return _localizar("lsar") is not None and _localizar("unar") is not None


def _tamano_directorio(carpeta: Path) -> int:
    total = 0
    for raiz, _dirs, ficheros in os.walk(carpeta):
        for f in ficheros:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(raiz, f)).st_size
    return total


def _matar_grupo(proc: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)


def _rss_del_grupo(pid: int) -> int:
    """Memoria residente (bytes) del proceso `pid` y sus descendientes, leída de `/proc`; lo que no se
    puede leer cuenta 0 (un `/proc` sin `children` degrada a solo el proceso). Acotado a 64 procesos."""
    pagina = os.sysconf("SC_PAGE_SIZE")
    total, visitados, pendientes = 0, set(), [pid]
    while pendientes and len(visitados) < 64:
        actual = pendientes.pop()
        if actual in visitados:
            continue
        visitados.add(actual)
        try:
            with open(f"/proc/{actual}/statm") as fh:
                total += int(fh.read().split()[1]) * pagina
        except (OSError, ValueError, IndexError):
            continue
        with contextlib.suppress(OSError, ValueError):
            for tid in os.listdir(f"/proc/{actual}/task"):
                with open(f"/proc/{actual}/task/{tid}/children") as fh:
                    pendientes.extend(int(x) for x in fh.read().split())
    return total


def _leer_acotado(flujo, tope: int, destino: bytearray, desbordado: threading.Event) -> None:
    """Lee `flujo` hasta el final guardando como mucho `tope` bytes; si lo pasa, avisa y sigue
    vaciando para que el proceso no se bloquee escribiendo."""
    while True:
        trozo = flujo.read(65536)
        if not trozo:
            return
        if len(destino) + len(trozo) > tope:
            desbordado.set()
            destino.extend(trozo[: max(0, tope - len(destino))])
            continue
        destino.extend(trozo)


def _ejecutar(argv: list[str], *, home: Path, timeout: float, tope_salida: int,
              vigilar: Path | None = None, tope_escrito: int | None = None) -> tuple[int, bytes, bytes]:
    """Lanza `argv` sin shell, en grupo propio, y devuelve `(código, stdout, stderr)`. Un solo lector
    vivo en todo el proceso: el turno se espera como mucho `RAR_ESPERA_TURNO_S`, si no `OCUPADO`.

    Falla con `ErrorRar`: `TIEMPO` si vence (se mata el grupo), `DEMASIADO_GRANDE` si la salida, lo
    escrito en `vigilar` o la memoria pasan del tope (se mata el grupo), `HERRAMIENTA_AUSENTE` si no
    arranca, `OCUPADO` si no hubo turno."""
    if not _SEMAFORO.acquire(timeout=RAR_ESPERA_TURNO_S):
        raise ErrorRar(MotivoRar.OCUPADO)
    try:
        return _ejecutar_con_turno(argv, home=home, timeout=timeout, tope_salida=tope_salida,
                                   vigilar=vigilar, tope_escrito=tope_escrito)
    finally:
        _SEMAFORO.release()


def _ejecutar_con_turno(argv: list[str], *, home: Path, timeout: float, tope_salida: int,
                        vigilar: Path | None, tope_escrito: int | None) -> tuple[int, bytes, bytes]:
    """Con el turno ya tomado: lanza, vigila y mata el grupo (ver `_ejecutar`)."""
    entorno = {"PATH": _ENTORNO_PATH, "HOME": str(home), "LANG": "C.UTF-8", "TMPDIR": str(home)}
    try:
        proc = subprocess.Popen(                      # noqa: S603 — sin shell, lista, ruta absoluta
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=entorno, cwd=home, start_new_session=True, close_fds=True)
    except OSError as exc:
        raise ErrorRar(MotivoRar.HERRAMIENTA_AUSENTE) from exc
    salida, error = bytearray(), bytearray()
    desbordado = threading.Event()
    hilos = [
        threading.Thread(target=_leer_acotado, args=(proc.stdout, tope_salida, salida, desbordado), daemon=True),
        threading.Thread(target=_leer_acotado, args=(proc.stderr, RAR_MAX_SALIDA_ERROR, error, threading.Event()), daemon=True),
    ]
    for h in hilos:
        h.start()
    limite = time.monotonic() + timeout
    motivo: MotivoRar | None = None
    try:
        while proc.poll() is None:
            if time.monotonic() >= limite:
                motivo = MotivoRar.TIEMPO
            elif (desbordado.is_set()
                    or (vigilar is not None and tope_escrito is not None
                        and _tamano_directorio(vigilar) > tope_escrito)
                    or _rss_del_grupo(proc.pid) > RAR_MAX_RSS):
                motivo = MotivoRar.DEMASIADO_GRANDE
            if motivo is not None:
                break
            time.sleep(_SONDEO_S)
    finally:
        # el grupo se mata siempre al salir: también si el hijo ya terminó pero dejó nietos
        _matar_grupo(proc)
        for h in hilos:
            h.join(timeout=2)
    if motivo is not None:
        raise ErrorRar(motivo)
    if desbordado.is_set():
        raise ErrorRar(MotivoRar.DEMASIADO_GRANDE)
    return proc.returncode, bytes(salida), bytes(error)


def _motivo_por_mensaje(texto: bytes) -> MotivoRar:
    """Lo que se puede deducir del mensaje de la herramienta; si no, `ilegible`. No se asume que
    haya mensaje: `unar -q` ocultaba errores en la primera prueba de #308."""
    t = texto.lower()
    if b"password" in t or b"encrypt" in t:
        return MotivoRar.CIFRADO
    if b"volume" in t or b"next part" in t or b"multi" in t:
        return MotivoRar.MULTIVOLUMEN
    return MotivoRar.ILEGIBLE


def _exigir_ruta_absoluta(ruta: Path) -> None:
    """Una ruta relativa que empezara por `-` sería una opción de `lsar`/`unar` (SecOps B-2). Las de la
    biblioteca son siempre absolutas."""
    if not ruta.is_absolute():
        raise ErrorRar(MotivoRar.ILEGIBLE)


def _entero(valor: object) -> int | None:
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str):
        with contextlib.suppress(ValueError):
            return int(valor, 0) if valor.lower().startswith("0x") else int(valor)
    return None


def _crc_de(bruto: dict) -> int | None:
    """CRC32 declarado de una entrada. La clave depende del formato (RAR4/RAR5): se acepta
    cualquiera que lleve «CRC» en el nombre, como entero o como 8 cifras hexadecimales."""
    for clave, valor in bruto.items():
        if "crc" not in str(clave).lower():
            continue
        if isinstance(valor, str) and len(valor) == 8:
            with contextlib.suppress(ValueError):
                return int(valor, 16)
        n = _entero(valor)
        if n is not None and 0 <= n <= 0xFFFFFFFF:
            return n
    return None


def _entrada_de(bruto: dict, posicion: int) -> EntradaRar:
    indice = _entero(bruto.get("XADIndex"))
    return EntradaRar(
        indice=posicion if indice is None else indice,
        nombre=str(bruto.get("XADFileName", "")),
        tamano=_entero(bruto.get("XADFileSize")) or 0,
        crc32=_crc_de(bruto),
        es_directorio=bool(_entero(bruto.get("XADIsDirectory"))),
        cifrada=bool(_entero(bruto.get("XADIsEncrypted"))),
    )


def listar(ruta: Path, *, temporal: Path, timeout: float = RAR_TIMEOUT_LISTAR_S) -> Listado:
    """Lista un RAR con `lsar -j` y comprueba los topes (nº de entradas, bytes declarados, salida).

    `temporal` es una carpeta propia y vacía (se usa de `HOME`). Falla con `ErrorRar`."""
    lsar = _localizar("lsar")
    if lsar is None:
        raise ErrorRar(MotivoRar.HERRAMIENTA_AUSENTE)
    _exigir_ruta_absoluta(ruta)
    codigo, salida, error = _ejecutar(
        [lsar, "-j", str(ruta)], home=temporal, timeout=timeout, tope_salida=RAR_MAX_SALIDA_LISTADO)
    if codigo != 0:
        raise ErrorRar(_motivo_por_mensaje(error + salida[:4096]))
    try:
        bruto = json.loads(salida)
        contenido = bruto["lsarContents"]
        entradas = tuple(_entrada_de(e, i) for i, e in enumerate(contenido))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ErrorRar(MotivoRar.ILEGIBLE) from exc
    # lo que llega de `lsar` es una entrada, no una verdad: un índice fuera de rango iría a `argv` y un
    # tamaño negativo eludiría el tope de bytes declarados (dictamen SecOps B-1)
    if any(not 0 <= e.indice < len(entradas) or e.tamano < 0 for e in entradas):
        raise ErrorRar(MotivoRar.ILEGIBLE)
    if len(entradas) > RAR_MAX_ENTRADAS or sum(e.tamano for e in entradas) > RAR_MAX_BYTES_DECLARADOS:
        raise ErrorRar(MotivoRar.DEMASIADO_GRANDE)
    if any(e.cifrada for e in entradas):
        raise ErrorRar(MotivoRar.CIFRADO)
    try:
        tamano_archivo = ruta.stat().st_size
    except OSError as exc:
        raise ErrorRar(MotivoRar.ILEGIBLE) from exc
    # `lsar` lista un truncado con código 0: vacío en un archivo grande es sospechoso, no «sin imágenes»
    if not entradas and tamano_archivo > _UMBRAL_LISTADO_VACIO:
        raise ErrorRar(MotivoRar.ILEGIBLE)
    return Listado(entradas)


def _unico_fichero_regular(carpeta: Path) -> Path:
    """El único fichero de `carpeta`: ni enlaces simbólicos, ni dos ficheros, ni nada que escape."""
    hallados: list[Path] = []
    raiz_real = carpeta.resolve()
    for raiz, dirs, ficheros in os.walk(carpeta, followlinks=False):
        for nombre in (*dirs, *ficheros):
            p = Path(raiz) / nombre
            if p.is_symlink():
                raise ErrorRar(MotivoRar.ILEGIBLE)
        for nombre in ficheros:
            p = Path(raiz) / nombre
            if not str(p.resolve()).startswith(str(raiz_real) + os.sep):
                raise ErrorRar(MotivoRar.ILEGIBLE)
            hallados.append(p)
    if len(hallados) != 1:
        raise ErrorRar(MotivoRar.ILEGIBLE)
    return hallados[0]


def leer_entrada(ruta: Path, entrada: EntradaRar, tope: int, *, temporal: Path,
                 timeout: float = RAR_TIMEOUT_EXTRAER_S) -> bytes:
    """Extrae UNA entrada (por índice) y devuelve sus bytes, ya verificados contra el listado
    (tamaño y, si el listado lo trae, CRC32). `temporal` es una carpeta propia y vacía que el
    llamador borra. Falla con `ErrorRar`; un código 0 sin nada escrito es `ilegible`."""
    unar = _localizar("unar")
    if unar is None:
        raise ErrorRar(MotivoRar.HERRAMIENTA_AUSENTE)
    _exigir_ruta_absoluta(ruta)
    if entrada.indice < 0 or entrada.tamano < 0:
        raise ErrorRar(MotivoRar.ILEGIBLE)
    if entrada.es_directorio or entrada.tamano > tope:
        raise ErrorRar(MotivoRar.DEMASIADO_GRANDE)
    destino = temporal / "salida"
    destino.mkdir(mode=0o700)
    codigo, salida, error = _ejecutar(
        [unar, "-D", "-f", "-i", "-o", str(destino), str(ruta), str(entrada.indice)],
        home=temporal, timeout=timeout, tope_salida=RAR_MAX_SALIDA_ERROR,
        vigilar=destino, tope_escrito=min(tope, entrada.tamano) + 1)
    if codigo != 0:
        raise ErrorRar(_motivo_por_mensaje(error + salida))
    fichero = _unico_fichero_regular(destino)
    try:
        estado = fichero.lstat()
        if estado.st_size != entrada.tamano or estado.st_size > tope:
            raise ErrorRar(MotivoRar.ILEGIBLE)
        datos = fichero.read_bytes()
    except OSError as exc:
        raise ErrorRar(MotivoRar.ILEGIBLE) from exc
    if len(datos) != entrada.tamano:
        raise ErrorRar(MotivoRar.ILEGIBLE)
    if entrada.crc32 is not None and zlib.crc32(datos) != entrada.crc32:
        raise ErrorRar(MotivoRar.ILEGIBLE)
    return datos


@contextlib.contextmanager
def carpeta_temporal(base: Path):
    """Carpeta privada (0700) dentro de `base` —la caché de portadas, nunca junto al original— que
    se borra SIEMPRE al salir, también ante excepción o tiempo agotado."""
    base.mkdir(parents=True, exist_ok=True)
    carpeta = Path(tempfile.mkdtemp(prefix="rar-", dir=base))
    try:
        os.chmod(carpeta, 0o700)
        yield carpeta
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
