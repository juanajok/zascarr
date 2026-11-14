"""Raíces de biblioteca (#156, ADR 0020).

Contrato del corte A: normalización y validación de raíces, mapeo tradición→raíz y
helpers de pertenencia/ruta visible. NO conecta todavía importer ni asignación: el
comportamiento actual de una sola raíz no cambia.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import ComicTradition, LibraryRoot, LibraryRootTradition


class RaizInvalidaError(ValueError):
    """Ruta/nombre de raíz que no cumple el contrato de §3/§5."""


@dataclass(frozen=True)
class Montaje:
    """Un montaje autorizado por la configuración (frontera de seguridad)."""
    path: str
    host_path: str = ""


def _sin_barra_final(valor: str) -> str:
    return valor.rstrip("/") or "/"


def normalizar_ruta(valor: str | Path) -> str:
    """Ruta absoluta POSIX normalizada, sin `.`/`..` y sin barra final.

    No resuelve symlinks (eso lo hace `validar_raiz` cuando la ruta existe): una ruta
    inexistente también debe normalizarse para poder crearla/validarla.
    """
    texto = str(valor).strip()
    if not texto:
        raise RaizInvalidaError("La ruta de la raíz no puede estar vacía.")
    if "\x00" in texto:
        raise RaizInvalidaError("La ruta contiene un carácter no válido.")
    ruta = Path(texto)
    if not ruta.is_absolute():
        raise RaizInvalidaError("La ruta de la raíz debe ser absoluta.")
    # `resolve(strict=False)` elimina `.` y `..` sin tocar el disco.
    normalizada = os.path.normpath(str(ruta))
    if normalizada == "." or normalizada == "..":
        raise RaizInvalidaError("La ruta de la raíz no es válida.")
    normalizada = _sin_barra_final(normalizada)
    if normalizada == "/":
        raise RaizInvalidaError("La raíz no puede ser «/».")
    if normalizada.startswith("//"):
        normalizada = "/" + normalizada.lstrip("/")
    return normalizada


def nombre_normalizado(valor: str) -> str:
    nombre = " ".join(str(valor).split())
    if not nombre:
        raise RaizInvalidaError("El nombre de la raíz no puede estar vacío.")
    return nombre


def es_componente_de(ruta: str | Path, base: str | Path) -> bool:
    """True si `ruta` es igual a `base` o está DENTRO de ella por componentes.

    `/media/library2` NO es componente de `/media/library`; `/media/library/x` sí.
    """
    hijo = Path(normalizar_ruta(ruta))
    padre = Path(normalizar_ruta(base))
    return hijo == padre or padre in hijo.parents


def rutas_autorizadas() -> list[Montaje]:
    """Allowlist de montajes derivada de settings, no de texto libre de Ajustes."""
    settings = get_settings()
    crudas = [p.strip() for p in (settings.library_roots or "").split(",") if p.strip()]
    if not crudas:
        crudas = [str(settings.library_path)]
    hosts = [p.strip() for p in (settings.host_library_roots or "").split(",")]
    montajes: list[Montaje] = []
    for i, cruda in enumerate(crudas):
        montajes.append(Montaje(path=normalizar_ruta(cruda),
                                host_path=hosts[i] if i < len(hosts) else ""))
    return montajes


def _rutas_especiales() -> list[str]:
    settings = get_settings()
    candidatas = [
        settings.downloads_path,
        settings.amule_incoming_dir,
        settings.export_path,
        *settings.carpetas_compartidas,
    ]
    return [normalizar_ruta(p) for p in candidatas if str(p).strip()]


def _mismo_inodo(a: Path, b: Path) -> bool:
    try:
        sa, sb = a.stat(), b.stat()
    except OSError:
        return False
    return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


def validar_raiz(
    path: str | Path,
    *,
    name: str = "",
    host_path: str = "",
    enabled: bool = True,
    is_default: bool = False,
    raices: Iterable[LibraryRoot | dict] = (),
    root_id: str | None = None,
) -> dict:
    """Normaliza y valida una raíz nueva/actualizada.

    `raices` son las raíces ya guardadas (modelos o dicts); se excluye `root_id` al
    comprobar unicidad. Lanza `RaizInvalidaError` con un motivo en español.
    """
    ruta = normalizar_ruta(path)
    nombre = nombre_normalizado(name or Path(ruta).name)
    if ruta == "/":
        raise RaizInvalidaError("La raíz no puede ser «/».")
    if "/.zascarr" in ruta or ruta.endswith("/.zascarr"):
        raise RaizInvalidaError("La raíz no puede estar dentro de .zascarr.")
    if not enabled and is_default:
        raise RaizInvalidaError("Una raíz por defecto no puede estar deshabilitada.")
    if is_default and any(
            bool(r.get("is_default") if isinstance(r, dict) else r.is_default)
            for r in raices
            if not root_id or str(r.get("id") if isinstance(r, dict) else r.id) != str(root_id)):
        raise RaizInvalidaError("Ya hay una raíz por defecto.")
    host = str(host_path or "").strip()
    if host:
        host = str(Path(host))
        if not Path(host).is_absolute():
            raise RaizInvalidaError("La ruta del host debe ser absoluta.")

    montajes = rutas_autorizadas()
    if not any(es_componente_de(ruta, m.path) for m in montajes):
        raise RaizInvalidaError("La ruta no está dentro de un montaje autorizado.")
    for especial in _rutas_especiales():
        if es_componente_de(ruta, especial) or es_componente_de(especial, ruta):
            raise RaizInvalidaError(
                "La raíz no puede solaparse con descargas, exportación ni .zascarr.")
    for raiz in raices:
        otro = raiz if isinstance(raiz, dict) else {
            "id": str(raiz.id), "path": raiz.path, "name": raiz.name,
            "host_path": raiz.host_path,
        }
        if root_id and str(otro["id"]) == str(root_id):
            continue
        if nombre.casefold() == str(otro["name"]).casefold():
            raise RaizInvalidaError("Ya existe una raíz con ese nombre.")
        if str(otro["path"]) == ruta or es_componente_de(ruta, str(otro["path"])) \
                or es_componente_de(str(otro["path"]), ruta):
            raise RaizInvalidaError("La raíz se solapa con otra raíz existente.")
        if host and otro.get("host_path") and str(otro["host_path"]) == host:
            raise RaizInvalidaError("Ya existe una raíz con esa ruta de host.")
        # Dos rutas (o un symlink) que son el mismo inodo son la misma raíz física.
        if (Path(ruta).exists() and Path(str(otro["path"])).exists()
                and _mismo_inodo(Path(ruta), Path(str(otro["path"])))):
            raise RaizInvalidaError("La raíz es el mismo inodo que otra raíz existente.")

    ruta_obj = Path(ruta)
    if ruta_obj.is_symlink() and not ruta_obj.exists():
        raise RaizInvalidaError("La ruta es un symlink roto.")
    if ruta_obj.exists():
        if not ruta_obj.is_dir():
            raise RaizInvalidaError("La ruta de la raíz no es una carpeta.")
        if ruta_obj.is_symlink() and not ruta_obj.resolve().is_dir():
            raise RaizInvalidaError("La ruta es un symlink roto.")
        # Symlink a una ruta autorizada: la ruta normalizada ya se validó por componentes.
        if ruta_obj.is_symlink():
            destino = normalizar_ruta(ruta_obj.resolve())
            if not any(es_componente_de(destino, m.path) for m in montajes):
                raise RaizInvalidaError(
                    "El symlink de la raíz apunta fuera de un montaje autorizado.")
    return {
        "name": nombre, "path": ruta, "host_path": host or None,
        "enabled": bool(enabled), "is_default": bool(is_default),
    }


async def raiz_por_tradicion(db: AsyncSession, tradicion: ComicTradition) -> LibraryRoot | None:
    """La raíz asignada a una tradición, o None (fallo cerrado; no hay raíz por defecto)."""
    fila = (await db.execute(
        select(LibraryRoot)
        .join(LibraryRootTradition, LibraryRootTradition.root_id == LibraryRoot.id)
        .where(LibraryRootTradition.tradition == tradicion, LibraryRoot.enabled.is_(True))
    )).scalar_one_or_none()
    return fila


def raiz_de(ruta: str | Path, raices: Iterable[LibraryRoot]) -> LibraryRoot | None:
    """La raíz MÁS ESPECÍFICA que contiene `ruta` por componentes, o None."""
    candidatas = [r for r in raices if es_componente_de(ruta, r.path)]
    if not candidatas:
        return None
    return max(candidatas, key=lambda r: len(Path(r.path).parts))


def relative_to_root(ruta: str | Path, root: LibraryRoot) -> Path:
    """Ruta relativa a `root`; falla si la ruta no pertenece a esa raíz."""
    ruta_n = normalizar_ruta(ruta)
    base = normalizar_ruta(root.path)
    if not es_componente_de(ruta_n, base):
        raise RaizInvalidaError("La ruta no pertenece a esa raíz.")
    return Path(ruta_n).relative_to(Path(base))


def ruta_visible(ruta: str | Path, root: LibraryRoot | None) -> str:
    """Ruta para mostrar: host de ESA raíz si existe; si no, la del contenedor.

    Una ruta fuera de la raíz se devuelve tal cual (nunca se le aplica el host de otra).
    """
    ruta_n = normalizar_ruta(ruta)
    if root is None or not root.host_path:
        return ruta_n
    try:
        relativa = relative_to_root(ruta_n, root)
    except RaizInvalidaError:
        return ruta_n
    return str(Path(root.host_path) / relativa)


class RaicesService:
    """Fachada única del contrato de raíces (#156); el corte A solo expone lectura/validación."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def raiz_por_tradicion(self, tradicion: ComicTradition) -> LibraryRoot | None:
        if self.db is None:
            raise RuntimeError("RaicesService sin sesión no puede consultar una tradición.")
        return await raiz_por_tradicion(self.db, tradicion)

    @staticmethod
    def validar(path, **kw) -> dict:
        return validar_raiz(path, **kw)

    @staticmethod
    def raiz_de(ruta, raices) -> LibraryRoot | None:
        return raiz_de(ruta, raices)
