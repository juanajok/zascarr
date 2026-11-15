"""Raíces de biblioteca (#156, ADR 0020).

Contrato del corte A: normalización y validación de raíces, mapeo tradición→raíz y
helpers de pertenencia/ruta visible. NO conecta todavía importer ni asignación: el
comportamiento actual de una sola raíz no cambia.

TOCTOU residual: entre validar y una escritura futura (cortes B/C) el montaje o la
ruta pueden cambiar. En el corte A no se escribe; B/C deben revalidar (canonical +
allowlist + permisos) antes de cada importación/escritura.
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


def _rechazar_control(texto: str) -> None:
    if any(ord(c) < 32 or ord(c) == 127 for c in texto):
        raise RaizInvalidaError("La ruta contiene caracteres de control.")


def _hay_symlink_roto(ruta: str | Path) -> bool:
    """Recorre los componentes: un symlink roto intermedio o final no se resuelve."""
    actual = Path("/")
    for parte in Path(ruta).parts[1:]:
        actual = actual / parte
        try:
            if actual.is_symlink() and not actual.exists():
                return True
        except OSError:
            return True
    return False


def _resolver(ruta: str | Path) -> str:
    """Ruta canónica real (symlinks resueltos), sin exigir que exista."""
    try:
        resuelta = Path(ruta).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise RaizInvalidaError("La ruta tiene un symlink roto o un bucle.") from exc
    return _sin_barra_final(os.path.normpath(str(resuelta)))


def normalizar_ruta(valor: str | Path) -> str:
    """Ruta absoluta POSIX normalizada, sin `.`/`..` y sin barra final.

    No recorta espacios: un path con espacios al principio no es absoluto y se
    rechaza. Tampoco resuelve symlinks: eso lo hace `validar_raiz` sobre la ruta
    completa para comprobar que el destino real sigue dentro de la allowlist.
    """
    texto = str(valor)
    if not texto:
        raise RaizInvalidaError("La ruta de la raíz no puede estar vacía.")
    _rechazar_control(texto)
    ruta = Path(texto)
    if not ruta.is_absolute():
        raise RaizInvalidaError("La ruta de la raíz debe ser absoluta.")
    normalizada = os.path.normpath(str(ruta))
    if normalizada in (".", ".."):
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
        montajes.append(Montaje(path=_resolver(normalizar_ruta(cruda)),
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
    return [_resolver(normalizar_ruta(p)) for p in candidatas if str(p).strip()]


def _mismo_inodo(a: Path, b: Path) -> bool:
    try:
        sa, sb = a.stat(), b.stat()
    except OSError:
        return False
    return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


def _comprobar_escritura(ruta: Path) -> None:
    """Prueba real de lectura/escritura con un temporal creado y borrado."""
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(prefix=".zascarr-prueba-", dir=ruta, delete=True):
            pass
    except OSError as exc:
        raise RaizInvalidaError(
            f"La raíz no es legible/escribible para el usuario del servicio: {ruta}") from exc


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
    """Normaliza, resuelve y valida una raíz nueva/actualizada.

    `raices` son las raíces ya guardadas (modelos o dicts); se materializa antes de
    recorrerlo y se excluye `root_id` al comprobar unicidad. La ruta nueva debe
    existir (la raíz 1 de la migración es la excepción: no la valida el servicio),
    ser directorio y permitir crear/borrar un temporal. Lanza `RaizInvalidaError`.
    """
    existentes = list(raices)
    ruta_original = normalizar_ruta(path)
    if _hay_symlink_roto(ruta_original):
        raise RaizInvalidaError("La ruta es un symlink roto.")
    ruta = _resolver(ruta_original)
    nombre = nombre_normalizado(name or Path(ruta).name)
    if "/.zascarr" in ruta or ruta.endswith("/.zascarr"):
        raise RaizInvalidaError("La raíz no puede estar dentro de .zascarr.")
    if not enabled and is_default:
        raise RaizInvalidaError("Una raíz por defecto no puede estar deshabilitada.")
    if is_default and any(
            bool(r.get("is_default") if isinstance(r, dict) else r.is_default)
            for r in existentes
            if not root_id or str(r.get("id") if isinstance(r, dict) else r.id) != str(root_id)):
        raise RaizInvalidaError("Ya hay una raíz por defecto.")

    host = str(host_path or "")
    if host:
        _rechazar_control(host)
        if not Path(host).is_absolute():
            raise RaizInvalidaError("La ruta del host debe ser absoluta.")

    montajes = rutas_autorizadas()
    if not any(es_componente_de(ruta, m.path) for m in montajes):
        raise RaizInvalidaError("La ruta resuelta no está dentro de un montaje autorizado.")
    for especial in _rutas_especiales():
        if es_componente_de(ruta, especial) or es_componente_de(especial, ruta):
            raise RaizInvalidaError(
                "La raíz no puede solaparse con descargas, exportación ni .zascarr.")
    ruta_obj = Path(ruta)
    if ruta_obj.is_symlink() and not ruta_obj.exists():
        raise RaizInvalidaError("La ruta es un symlink roto.")
    if not ruta_obj.exists():
        raise RaizInvalidaError("La raíz no existe o el disco no está montado.")
    if not ruta_obj.is_dir():
        raise RaizInvalidaError("La ruta de la raíz no es una carpeta.")
    _comprobar_escritura(ruta_obj)

    for raiz in existentes:
        otro = raiz if isinstance(raiz, dict) else {
            "id": str(raiz.id), "path": raiz.path, "name": raiz.name,
            "host_path": raiz.host_path,
        }
        if root_id and str(otro["id"]) == str(root_id):
            continue
        if nombre.casefold() == str(otro["name"]).casefold():
            raise RaizInvalidaError("Ya existe una raíz con ese nombre.")
        otra_ruta = _resolver(normalizar_ruta(str(otro["path"])))
        if ruta == otra_ruta or es_componente_de(ruta, otra_ruta) \
                or es_componente_de(otra_ruta, ruta):
            raise RaizInvalidaError("La raíz se solapa con otra raíz existente.")
        if host and otro.get("host_path") and str(otro["host_path"]) == host:
            raise RaizInvalidaError("Ya existe una raíz con esa ruta de host.")
        if (ruta_obj.exists() and Path(otra_ruta).exists()
                and _mismo_inodo(ruta_obj, Path(otra_ruta))):
            raise RaizInvalidaError("La raíz es el mismo inodo que otra raíz existente.")
    return {
        "name": nombre, "path": ruta, "host_path": host or None,
        "enabled": bool(enabled), "is_default": bool(is_default),
    }


def validar_conjunto(raices: Iterable[LibraryRoot | dict]) -> None:
    """Invariante I4: exactamente una raíz por defecto, habilitada.

    El índice parcial impide dos, pero no cero; el servicio lo exige al guardar.
    """
    filas = list(raices)
    defectos = [
        r for r in filas
        if bool(r.get("is_default") if isinstance(r, dict) else r.is_default)
    ]
    if len(defectos) != 1:
        raise RaizInvalidaError("Debe haber exactamente una raíz por defecto.")
    unica = defectos[0]
    if not bool(unica.get("enabled") if isinstance(unica, dict) else unica.enabled):
        raise RaizInvalidaError("La raíz por defecto debe estar habilitada.")


async def raiz_por_tradicion(db: AsyncSession, tradicion: ComicTradition) -> LibraryRoot | None:
    """La raíz asignada a una tradición, o None (fallo cerrado; no hay raíz por defecto)."""
    fila = (await db.execute(
        select(LibraryRoot)
        .join(LibraryRootTradition, LibraryRootTradition.root_id == LibraryRoot.id)
        .where(LibraryRootTradition.tradition == tradicion, LibraryRoot.enabled.is_(True))
    )).scalar_one_or_none()
    if fila is None:
        return None
    # Si el operador retiró el montaje de la allowlist actual, no se usa para importar.
    autorizadas = [m.path for m in rutas_autorizadas()]
    if not any(es_componente_de(_resolver(fila.path), autorizada)
               for autorizada in autorizadas):
        return None
    return fila


def raiz_de(ruta: str | Path, raices: Iterable[LibraryRoot] = ()) -> LibraryRoot | None:
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
    def raiz_de(ruta, raices=()) -> LibraryRoot | None:
        return raiz_de(ruta, raices)

    @staticmethod
    def validar_conjunto(raices) -> None:
        validar_conjunto(raices)
