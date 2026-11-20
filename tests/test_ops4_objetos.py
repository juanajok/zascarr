"""Pruebas sintéticas del lector aislado, sin Git ni red."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from deploy.ops.experimento_objetos_ops4 import Limites, ObjetoInvalidoError, inventariar

IDENTIDADES = b"\nauthor A <a@b> 1 +0000\ncommitter C <c@d> 2 +0000"


def objeto(tipo: str, datos: bytes, almacen: dict) -> str:
    sha = hashlib.sha1(tipo.encode() + b" " + str(len(datos)).encode() + b"\0" + datos).hexdigest()
    almacen[sha] = (tipo, datos)
    return sha


def entrada(modo: bytes, nombre: bytes, sha: str) -> bytes:
    return modo + b" " + nombre + b"\0" + bytes.fromhex(sha)


def preparar() -> tuple[dict, str, str, str]:
    almacen = {}
    blob = objeto("blob", b"contenido", almacen)
    sub = objeto("tree", entrada(b"100755", b"fichero", blob), almacen)
    tree = objeto("tree", entrada(b"40000", b"dir", sub), almacen)
    commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\nmensaje", almacen)
    return almacen, commit, tree, blob


def test_inventario_completo_y_sha256() -> None:
    almacen, commit, _, _ = preparar()
    inventario = inventariar(commit, almacen.__getitem__)
    assert set(inventario) == {"dir/fichero"}
    assert inventario["dir/fichero"].modo == 0o100755
    assert inventario["dir/fichero"].digest == hashlib.sha256(b"contenido").hexdigest()


def test_objeto_alterado_o_ausente_falla() -> None:
    almacen, commit, _, blob = preparar()
    almacen[blob] = ("blob", b"otro")
    with pytest.raises(ObjetoInvalidoError):
        inventariar(commit, almacen.__getitem__)
    del almacen[blob]
    with pytest.raises(ObjetoInvalidoError):
        inventariar(commit, almacen.__getitem__)


@pytest.mark.parametrize(
    "modo,nombre",
    [
        (b"120000", b"link"),
        (b"160000", b"sub"),
        (b"100644", b".."),
        (b"100644", b"a/b"),
        (b"100644", b"a\\b"),
        (b"100644", b"\xff"),
        (b"0100644", b"a"),
    ],
)
def test_entrada_insegura(modo: bytes, nombre: bytes) -> None:
    almacen, _, _, blob = preparar()
    tree = objeto("tree", entrada(modo, nombre, blob), almacen)
    commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
    with pytest.raises(ObjetoInvalidoError):
        inventariar(commit, almacen.__getitem__)


def test_duplicados_y_truncado_no_entregan_parcial() -> None:
    almacen, _, _, blob = preparar()
    e = entrada(b"100644", b"a", blob)
    for datos in (e + e, e + b"100644 b\0\x01"):
        tree = objeto("tree", datos, almacen)
        commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
        with pytest.raises(ObjetoInvalidoError):
            inventariar(commit, almacen.__getitem__)


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("objetos", 2),
        ("bytes_totales", 1),
        ("bytes_objeto", 1),
        ("entradas", 1),
        ("profundidad", 0),
        ("bytes_ruta", 3),
    ],
)
def test_limites(campo: str, valor: int) -> None:
    almacen, commit, _, _ = preparar()
    with pytest.raises(ObjetoInvalidoError):
        inventariar(commit, almacen.__getitem__, replace(Limites(), **{campo: valor}))


@pytest.mark.parametrize("nombre", [b".git", b".GiT", b".GIT"])
def test_git_reservado(nombre: bytes) -> None:
    almacen, _, _, blob = preparar()
    tree = objeto("tree", entrada(b"100644", nombre, blob), almacen)
    commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
    with pytest.raises(ObjetoInvalidoError):
        inventariar(commit, almacen.__getitem__)


def test_orden_git_y_colision_entre_directorio_y_fichero() -> None:
    almacen, _, _, blob = preparar()
    vacio = objeto("tree", b"", almacen)
    for datos in (
        entrada(b"100644", b"z", blob) + entrada(b"100644", b"a", blob),
        entrada(b"40000", b"a", vacio) + entrada(b"100644", b"a.c", blob),
        entrada(b"100644", b"a", blob) + entrada(b"40000", b"a", vacio),
    ):
        tree = objeto("tree", datos, almacen)
        commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
        with pytest.raises(ObjetoInvalidoError):
            inventariar(commit, almacen.__getitem__)
    valido = entrada(b"100644", b"a.c", blob) + entrada(b"40000", b"a", vacio)
    tree = objeto("tree", valido, almacen)
    commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
    assert set(inventariar(commit, almacen.__getitem__)) == {"a.c"}


@pytest.mark.parametrize(
    "cabeceras",
    [
        b"",
        b"\nauthor A <a@b> 1 +0000",
        b"\ncommitter C <c@d> 2 +0000",
        IDENTIDADES + b"\nauthor A <a@b> 1 +0000",
        IDENTIDADES + b"\ncommitter C <c@d> 2 +0000",
        b"\nparent ABC" + IDENTIDADES,
        b"\nparent " + b"a" * 40 + b"\nparent " + b"a" * 40 + IDENTIDADES,
        b"\nauthor A <a@b> 1 +2460\ncommitter C <c@d> 2 +0000",
        IDENTIDADES + b"\n malformado",
        IDENTIDADES + b"\ntree " + b"a" * 40,
    ],
)
def test_commit_malformado(cabeceras: bytes) -> None:
    almacen, _, tree, _ = preparar()
    commit = objeto("commit", b"tree " + tree.encode() + cabeceras + b"\n\n", almacen)
    with pytest.raises(ObjetoInvalidoError):
        inventariar(commit, almacen.__getitem__)


def test_commit_con_padres_y_firma_multilinea() -> None:
    almacen, _, tree, _ = preparar()
    commit = objeto(
        "commit",
        b"tree "
        + tree.encode()
        + b"\nparent "
        + b"a" * 40
        + IDENTIDADES
        + b"\ngpgsig -----BEGIN SIGNATURE-----\n contenido\n -----END SIGNATURE-----\n\n",
        almacen,
    )
    assert set(inventariar(commit, almacen.__getitem__)) == {"dir/fichero"}


def test_tipo_no_coincide_con_modo() -> None:
    almacen, _, _, blob = preparar()
    tree = objeto("tree", entrada(b"40000", b"dir", blob), almacen)
    commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
    with pytest.raises(ObjetoInvalidoError):
        inventariar(commit, almacen.__getitem__)


def test_presupuesto_rutas_utf8_repetidas_y_frontera() -> None:
    almacen = {}
    blob = objeto("blob", b"x", almacen)
    sub = objeto("tree", entrada(b"100644", "é".encode(), blob), almacen)
    vacio = objeto("tree", b"", almacen)
    tree = objeto(
        "tree",
        entrada(b"40000", b"a", sub)
        + entrada(b"40000", b"b", sub)
        + entrada(b"40000", b"vacio", vacio),
        almacen,
    )
    commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
    # a, b y vacio suman 7 bytes; a/é y b/é suman otros 8.
    limites = replace(Limites(), bytes_rutas_totales=15)
    primero = inventariar(commit, almacen.__getitem__, limites)
    assert set(primero) == {"a/é", "b/é"}
    assert inventariar(commit, almacen.__getitem__, limites) == primero
    with pytest.raises(ObjetoInvalidoError, match="bytes de rutas"):
        inventariar(commit, almacen.__getitem__, replace(limites, bytes_rutas_totales=14))


def test_directorios_vacios_anchos_agotan_presupuesto_antes_de_encolarlos() -> None:
    almacen = {}
    vacio = objeto("tree", b"", almacen)
    nombres = [f"dir{i:04d}".encode() for i in range(1000)]
    tree = objeto("tree", b"".join(entrada(b"40000", n, vacio) for n in nombres), almacen)
    commit = objeto("commit", b"tree " + tree.encode() + IDENTIDADES + b"\n\n", almacen)
    limites = replace(Limites(), bytes_rutas_totales=7000)
    assert inventariar(commit, almacen.__getitem__, limites) == {}
    llamadas = []

    def proveedor(sha: str) -> tuple[str, bytes]:
        llamadas.append(sha)
        return almacen[sha]

    with pytest.raises(ObjetoInvalidoError, match="bytes de rutas"):
        inventariar(commit, proveedor, replace(limites, bytes_rutas_totales=6999))
    assert llamadas == [commit, tree]


def test_hash_git_actualiza_sin_concatenar_contenido(monkeypatch: pytest.MonkeyPatch) -> None:
    almacen, commit, _, _ = preparar()
    original = hashlib.sha1
    recibidos = []

    class HashVigilado:
        def __init__(self, cabecera: bytes) -> None:
            assert cabecera.endswith(b"\0")
            self.hash = original(cabecera)

        def update(self, datos: bytes) -> None:
            recibidos.append(datos)
            self.hash.update(datos)

        def hexdigest(self) -> str:
            return self.hash.hexdigest()

    monkeypatch.setattr(hashlib, "sha1", HashVigilado)
    inventariar(commit, almacen.__getitem__)
    assert len(recibidos) == 4
    assert all(any(datos is contenido for _, contenido in almacen.values()) for datos in recibidos)
