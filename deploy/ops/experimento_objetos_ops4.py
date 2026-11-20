"""Lector experimental puro de objetos Git sintéticos; no autoriza despliegues.

SHA-1 comprueba coherencia con el identificador Git, no autenticidad ni ofrece
resistencia suficiente a colisiones. El proveedor y la procedencia no se
verifican; no conectar este experimento a un autorizador. No realiza E/S.
El perfil de commit es conservador, no verifica firmas ni padres; puede rechazar
commits Git válidos. Los árboles vacíos no aparecen en el inventario de blobs.
El proveedor entrega bytes ya materializados: los límites no acotan la memoria
que el proveedor haya consumido antes de devolver un objeto.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass


class ObjetoInvalidoError(ValueError):
    """El objeto, el árbol o los límites no permiten verificar el inventario."""


@dataclass(frozen=True)
class Entrada:
    """Contenido y modo de un blob, sin materializarlo."""

    tipo: str
    modo: int
    digest: str


@dataclass(frozen=True)
class Limites:
    """Presupuestos conservadores por recorrido, inclusive sus fronteras."""

    objetos: int = 100_000
    bytes_totales: int = 256 * 1024 * 1024
    bytes_objeto: int = 32 * 1024 * 1024
    entradas: int = 100_000
    profundidad: int = 64
    bytes_ruta: int = 4096


_SHA = re.compile(r"[0-9a-f]{40}\Z")
Proveedor = Callable[[str], tuple[str, bytes]]


def inventariar(
    commit: str, proveedor: Proveedor, limites: Limites = Limites()
) -> dict[str, Entrada]:
    """Recorrer íntegramente el árbol de un commit o fallar sin resultado parcial.

    El proveedor recibe SHA-1 hexadecimal minúsculo y devuelve (tipo, bytes).
    Los límites cuentan cada lectura y cada entrada, incluso referencias repetidas.
    El resultado solo describe archivos; los árboles vacíos no tienen entrada.
    """
    if not isinstance(limites, Limites) or any(
        type(v) is not int or v <= 0 for v in vars(limites).values()
    ):
        raise ObjetoInvalidoError("Límites inválidos")
    if not isinstance(commit, str) or not _SHA.fullmatch(commit) or not callable(proveedor):
        raise ObjetoInvalidoError("Identificador o proveedor inválido")
    objetos = 0
    total = 0
    entradas = 0
    resultado: dict[str, Entrada] = {}

    def leer(sha: str, esperado: str) -> bytes:
        nonlocal objetos, total
        objetos += 1
        if objetos > limites.objetos:
            raise ObjetoInvalidoError("Demasiados objetos")
        try:
            respuesta = proveedor(sha)
        except Exception as exc:
            raise ObjetoInvalidoError("Objeto no disponible") from exc
        if (
            not isinstance(respuesta, tuple)
            or len(respuesta) != 2
            or respuesta[0] != esperado
            or type(respuesta[1]) is not bytes
        ):
            raise ObjetoInvalidoError("Tipo o contenido de objeto inválido")
        datos = respuesta[1]
        if len(datos) > limites.bytes_objeto:
            raise ObjetoInvalidoError("Objeto demasiado grande")
        total += len(datos)
        if total > limites.bytes_totales:
            raise ObjetoInvalidoError("Presupuesto de bytes agotado")
        cabecera = esperado.encode("ascii") + b" " + str(len(datos)).encode("ascii") + b"\0"
        if hashlib.sha1(cabecera + datos).hexdigest() != sha:
            raise ObjetoInvalidoError("Hash Git incorrecto")
        return datos

    contenido = leer(commit, "commit")
    cabeceras, separador, _ = contenido.partition(b"\n\n")
    lineas = cabeceras.split(b"\n")
    if not separador or not lineas or not re.fullmatch(rb"tree [0-9a-f]{40}", lineas[0]):
        raise ObjetoInvalidoError("Commit inválido")
    # Perfil deliberadamente conservador: no valida firmas ni ascendencia.
    # Se admiten cabeceras adicionales con continuaciones, no en campos básicos.
    fase = "parent"
    padres: set[bytes] = set()
    extra = False
    for linea in lineas[1:]:
        if linea.startswith(b" "):
            if not extra or any(c < 32 and c != 9 for c in linea):
                raise ObjetoInvalidoError("Continuación de commit inválida")
            continue
        clave, espacio, valor = linea.partition(b" ")
        if not espacio or not re.fullmatch(rb"[a-z][a-z0-9-]*", clave) or not valor:
            raise ObjetoInvalidoError("Cabecera de commit inválida")
        if any(c < 32 or c == 127 for c in valor):
            raise ObjetoInvalidoError("Control en cabecera de commit")
        extra = False
        if clave == b"parent":
            if fase != "parent" or not re.fullmatch(rb"[0-9a-f]{40}", valor) or valor in padres:
                raise ObjetoInvalidoError("Padre inválido o duplicado")
            padres.add(valor)
        elif clave in (b"author", b"committer"):
            esperado = b"author" if fase == "parent" else b"committer" if fase == "author" else b""
            identidad = re.fullmatch(
                rb"[^<>\x00-\x1f\x7f]+ <[^<>\x00-\x20\x7f]+> [0-9]+ ([+-])([0-9]{2})([0-9]{2})",
                valor,
            )
            if (
                clave != esperado
                or not identidad
                or int(identidad[2]) > 23
                or int(identidad[3]) > 59
            ):
                raise ObjetoInvalidoError("Identidad de commit inválida")
            fase = "author" if clave == b"author" else "committer"
        elif clave == b"tree" or fase != "committer":
            raise ObjetoInvalidoError("Cabecera de commit inesperada")
        else:
            extra = True
    if fase != "committer":
        raise ObjetoInvalidoError("Commit sin autor o committer")
    raiz = lineas[0][5:].decode("ascii")
    pendientes = [(raiz, "", 0, frozenset())]
    while pendientes:
        sha, prefijo, profundidad, ancestros = pendientes.pop()
        if profundidad > limites.profundidad or sha in ancestros:
            raise ObjetoInvalidoError("Profundidad o ciclo inválido")
        datos = leer(sha, "tree")
        pos = 0
        nombres: set[str] = set()
        anterior: bytes | None = None
        while pos < len(datos):
            entradas += 1
            if entradas > limites.entradas:
                raise ObjetoInvalidoError("Demasiadas entradas")
            espacio = datos.find(b" ", pos)
            nulo = datos.find(b"\0", espacio + 1) if espacio >= 0 else -1
            if espacio < 0 or nulo < 0 or nulo + 21 > len(datos):
                raise ObjetoInvalidoError("Entrada de árbol truncada")
            modo = datos[pos:espacio]
            nombre_bytes = datos[espacio + 1 : nulo]
            try:
                nombre = nombre_bytes.decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise ObjetoInvalidoError("Nombre no UTF-8") from exc
            if (
                not nombre
                or nombre in (".", "..")
                or nombre.casefold() == ".git"
                or nombre.startswith("-")
                or any(ord(c) < 32 or ord(c) == 127 or c in "/\\" for c in nombre)
                or nombre in nombres
            ):
                raise ObjetoInvalidoError("Nombre inseguro o duplicado")
            nombres.add(nombre)
            clave = nombre_bytes + (b"/" if modo == b"40000" else b"")
            if anterior is not None and clave <= anterior:
                raise ObjetoInvalidoError("Orden de árbol no canónico")
            anterior = clave
            ruta = prefijo + nombre
            if len(ruta.encode("utf-8")) > limites.bytes_ruta:
                raise ObjetoInvalidoError("Ruta demasiado larga")
            hijo = datos[nulo + 1 : nulo + 21].hex()
            pos = nulo + 21
            if modo == b"40000":
                pendientes.append((hijo, ruta + "/", profundidad + 1, ancestros | {sha}))
            elif modo in (b"100644", b"100755"):
                blob = leer(hijo, "blob")
                resultado[ruta] = Entrada("blob", int(modo, 8), hashlib.sha256(blob).hexdigest())
            else:
                raise ObjetoInvalidoError("Modo Git no permitido")
    return resultado
