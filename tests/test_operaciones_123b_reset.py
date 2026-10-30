"""Reset de 123b: restaurar los originales movidos por la reconciliación.

Sin PostgreSQL: se prueba la función `restaurar_y_resetear` con filas y un
ejecutor SQL inyectables. El caso clave es el de la ventana: la app movió el
original a `_123b/`; el reset antiguo borraba `_123b` antes de mirar las filas
y dejaba el fixture inservible.
"""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "aceptacion" / "preparar_operaciones_123b.py"
CONTENIDO = b"contenido del fixture 123b"


def _cargar():
    spec = importlib.util.spec_from_file_location("preparar_operaciones_123b_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def sidecar():
    return _cargar()


class SQLFalso:
    def __init__(self, issue_id: str | None = "issue-1"):
        self.issue_id = issue_id
        self.consultas: list[str] = []

    def __call__(self, sql: str) -> list[list[str]]:
        self.consultas.append(sql)
        if "from issues" in sql:
            return [[self.issue_id]] if self.issue_id else []
        return []

    @property
    def borrado(self) -> bool:
        return any("DELETE FROM asignacion_operaciones" in sql for sql in self.consultas)

    @property
    def updates(self) -> list[str]:
        return [sql for sql in self.consultas if sql.startswith("UPDATE files")]


def _fila(
    *,
    origen: str = "/media/library/original.cbz",
    destino: str = "/media/library/_123b/confirmada.cbz",
    size: int | str = len(CONTENIDO),
    sha: str | None = None,
    issue_number: str = "2",
    series_id: str = "serie-1",
    file_id: str = "file-1",
):
    return (
        file_id,
        origen,
        destino,
        series_id,
        issue_number,
        str(size),
        sha if sha is not None else hashlib.sha256(CONTENIDO).hexdigest(),
    )


def _biblioteca(tmp_path: Path) -> Path:
    biblioteca = tmp_path / "biblioteca"
    biblioteca.mkdir()
    return biblioteca


def _poner(ruta: Path, contenido: bytes = CONTENIDO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)


def test_origen_intacto_no_copia_y_restaura_la_fila(sidecar, tmp_path, monkeypatch):
    biblioteca = _biblioteca(tmp_path)
    origen = biblioteca / "original.cbz"
    _poner(origen)
    _poner(biblioteca / "_123b" / "resto.cbz")
    sql = SQLFalso()

    def no_copiar(*_a, **_k):
        raise AssertionError("no debía copiar: el origen existe")

    monkeypatch.setattr(sidecar.shutil, "copy2", no_copiar)
    sidecar.restaurar_y_resetear([_fila()], biblioteca, sql)

    assert origen.read_bytes() == CONTENIDO
    assert not (biblioteca / "_123b").exists()
    assert sql.borrado
    assert len(sql.updates) == 1
    assert "file_path = '/media/library/original.cbz'" in sql.updates[0]
    assert "file_name = 'original.cbz'" in sql.updates[0]
    assert "is_missing = false" in sql.updates[0]
    assert "issue_id = 'issue-1'" in sql.updates[0]


def test_origen_sin_issue_deja_issue_id_null(sidecar, tmp_path):
    biblioteca = _biblioteca(tmp_path)
    _poner(biblioteca / "original.cbz")
    sql = SQLFalso(issue_id=None)
    sidecar.restaurar_y_resetear([_fila(issue_number="")], biblioteca, sql)
    assert "issue_id = NULL" in sql.updates[0]


def test_origen_movido_a_destino_copia_de_vuelta_y_restaura(sidecar, tmp_path):
    biblioteca = _biblioteca(tmp_path)
    destino = biblioteca / "_123b" / "confirmada.cbz"
    _poner(destino)
    sql = SQLFalso()

    sidecar.restaurar_y_resetear([_fila()], biblioteca, sql)

    assert (biblioteca / "original.cbz").read_bytes() == CONTENIDO
    assert not (biblioteca / "_123b").exists()
    assert sql.borrado
    assert len(sql.updates) == 1
    assert "file_path = '/media/library/original.cbz'" in sql.updates[0]


def test_origen_fuera_de_biblioteca_aborta_sin_borrar(sidecar, tmp_path):
    biblioteca = _biblioteca(tmp_path)
    _poner(biblioteca / "_123b" / "confirmada.cbz")
    sql = SQLFalso()

    with pytest.raises(sidecar.FixtureError, match="fuera de la biblioteca"):
        sidecar.restaurar_y_resetear(
            [_fila(origen="/etc/passwd")],
            biblioteca,
            sql,
        )

    assert sql.consultas == []
    assert (biblioteca / "_123b" / "confirmada.cbz").exists()


def test_tamano_o_sha_no_coincide_aborta_sin_borrar(sidecar, tmp_path):
    biblioteca = _biblioteca(tmp_path)
    _poner(biblioteca / "_123b" / "confirmada.cbz", b"otra cosa")
    sql = SQLFalso()

    with pytest.raises(sidecar.FixtureError, match="no coincide"):
        sidecar.restaurar_y_resetear([_fila()], biblioteca, sql)

    assert not sql.borrado
    assert (biblioteca / "_123b" / "confirmada.cbz").exists()


def test_dos_reset_seguidos_son_idempotentes(sidecar, tmp_path):
    biblioteca = _biblioteca(tmp_path)
    _poner(biblioteca / "_123b" / "confirmada.cbz")
    filas = [_fila()]

    sidecar.restaurar_y_resetear(filas, biblioteca, SQLFalso())
    sidecar.restaurar_y_resetear(filas, biblioteca, SQLFalso())

    assert (biblioteca / "original.cbz").read_bytes() == CONTENIDO
    assert not (biblioteca / "_123b").exists()


def test_regresion_el_orden_antiguo_perdia_la_unica_copia(sidecar, tmp_path):
    """El reset antiguo borraba `_123b` antes de resolver: la copia desaparecía."""
    biblioteca = _biblioteca(tmp_path)
    copia = biblioteca / "_123b" / "confirmada.cbz"
    _poner(copia)

    # Orden antiguo: rmtree(_123b) y después intentar resolver el original.
    shutil.rmtree(biblioteca / "_123b")
    assert not (biblioteca / "original.cbz").exists()
    assert not copia.exists()

    # El orden nuevo restaura desde destino antes de borrar.
    _poner(copia)
    sidecar.restaurar_y_resetear([_fila()], biblioteca, SQLFalso())
    assert (biblioteca / "original.cbz").read_bytes() == CONTENIDO
