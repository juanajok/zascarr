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
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.config import get_settings
from zascarr.models import ComicTradition, File, LibraryRoot, LibraryRootTradition


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


class RaizNoDisponibleError(RaizInvalidaError):
    """La tradición/raíz no se puede usar para escribir; `causa` es accionable."""

    def __init__(self, causa: str, *, raiz: str | None = None):
        self.causa = causa
        self.raiz = raiz
        super().__init__(f"{causa}" + (f" (raíz «{raiz}»)" if raiz else ""))


@dataclass(frozen=True)
class RaizResuelta:
    """Una raíz ya validada para una operación; `id` puede ser None solo en dobles de prueba."""
    id: UUID | None
    name: str
    path: Path
    host_path: str | None = None


class FotoDeRaices:
    """Foto inmutable del mapeo de raíces al empezar un ciclo/operación.

    Una consulta, y no se cambia el destino a mitad: el ciclo del importer y una
    asignación usan la misma foto hasta terminar.
    """

    def __init__(self, raices: list[LibraryRoot], *, validar: bool = True,
                 por_tradicion: dict[str, LibraryRoot] | None = None):
        self._raices = raices
        self._validar = validar
        self._resueltas: dict[str, RaizResuelta] = {}
        self._defecto: LibraryRoot | None = None
        for raiz in raices:
            if raiz.is_default and self._defecto is None:
                self._defecto = raiz
        if por_tradicion is not None:
            self._por_tradicion = dict(por_tradicion)
        else:
            self._por_tradicion = {}
            for raiz in raices:
                for asignacion in getattr(raiz, "traditions", []) or []:
                    self._por_tradicion[ComicTradition(asignacion.tradition).value] = raiz

    @classmethod
    async def cargar(cls, db: AsyncSession) -> FotoDeRaices:
        """Una sola consulta: raíces + mapeo de tradiciones."""
        filas = (await db.execute(
            select(LibraryRoot, LibraryRootTradition)
            .outerjoin(LibraryRootTradition, LibraryRootTradition.root_id == LibraryRoot.id)
            .order_by(LibraryRoot.created_at, LibraryRoot.id, LibraryRootTradition.tradition)
        )).all()
        raices: list[LibraryRoot] = []
        por_tradicion: dict[str, LibraryRoot] = {}
        vistos: set[str] = set()
        for raiz, asignacion in filas:
            clave = str(raiz.id)
            if clave not in vistos:
                vistos.add(clave)
                raices.append(raiz)
            if asignacion is not None:
                por_tradicion[ComicTradition(asignacion.tradition).value] = raiz
        from zascarr.utils.saneado_logs import refrescar_raices
        refrescar_raices([r.path for r in raices])
        return cls(raices, por_tradicion=por_tradicion)

    @classmethod
    def compatibilidad(cls, path: Path | None = None) -> FotoDeRaices:
        """Solo para dobles de prueba sin tabla de raíces: reproduce una instalación de una raíz."""
        s = get_settings()
        raiz = type("_RaizCompat", (), {})()
        raiz.id = None
        raiz.name = "Biblioteca"
        raiz.path = str(path or s.library_path)
        raiz.host_path = s.host_library_dir or None
        raiz.enabled = True
        raiz.is_default = True
        raiz.traditions = [
            type("_Trad", (), {"tradition": t.value})() for t in ComicTradition
        ]
        return cls([raiz], validar=False)

    @property
    def raices(self) -> tuple[LibraryRoot, ...]:
        return tuple(self._raices)

    def _resolver_raiz(self, raiz: LibraryRoot) -> RaizResuelta:
        clave = str(raiz.id)
        if clave in self._resueltas:
            return self._resueltas[clave]
        if not getattr(raiz, "enabled", True):
            raise RaizNoDisponibleError("La raíz está deshabilitada.", raiz=raiz.name)
        if self._validar:
            try:
                datos = validar_raiz(
                    raiz.path, name=raiz.name, host_path=raiz.host_path or "",
                    enabled=bool(raiz.enabled), is_default=bool(raiz.is_default),
                    raices=self._raices, root_id=raiz.id,
                )
            except RaizInvalidaError as exc:
                raise RaizNoDisponibleError(str(exc), raiz=raiz.name) from exc
            camino = Path(datos["path"])
        else:
            camino = Path(raiz.path)
        resuelta = RaizResuelta(
            id=raiz.id if raiz.id is not None else None,
            name=raiz.name, path=camino, host_path=raiz.host_path)
        self._resueltas[clave] = resuelta
        return resuelta

    def por_tradicion(self, tradicion: ComicTradition | str | None) -> RaizResuelta:
        clave = (tradicion.value if isinstance(tradicion, ComicTradition)
                 else str(tradicion or "other"))
        raiz = self._por_tradicion.get(clave)
        if raiz is None:
            # `other` puede no tener raíz explícita: no se cae a la raíz por defecto.
            raise RaizNoDisponibleError(
                "La tradición no tiene una raíz asignada; el archivo se queda en la cola.")
        return self._resolver_raiz(raiz)

    def por_defecto(self) -> RaizResuelta:
        if self._defecto is None:
            raise RaizNoDisponibleError(
                "No hay raíz por defecto; el archivo se queda en la cola.")
        return self._resolver_raiz(self._defecto)

    def raiz_para_escritura(self, root_id: UUID | None) -> RaizResuelta:
        """Revalida estado/allowlist/existencia/escritura antes de cada movimiento.

        La foto conserva el mapeo, pero no la disponibilidad: un disco que se
        desmonta o una raíz que se deshabilita entre archivos debe bloquear el
        siguiente (H3).
        """
        if root_id is None:
            raise RaizNoDisponibleError("La operación no tiene raíz persistida.")
        for raiz in self._raices:
            if str(raiz.id) == str(root_id):
                self._resueltas.pop(str(raiz.id), None)
                return self._resolver_raiz(raiz)
        raise RaizNoDisponibleError("La raíz de la operación ya no existe.")

    def para_id(self, root_id: str | None) -> RaizResuelta:
        if root_id is None:
            raise RaizNoDisponibleError("La operación no tiene raíz persistida.")
        for raiz in self._raices:
            if str(raiz.id) == str(root_id):
                return self._resolver_raiz(raiz)
        raise RaizNoDisponibleError("La raíz de la operación ya no existe.")


# ── Administración de raíces (corte D) ───────────────────────────────────────

async def listar_con_tradiciones(db: AsyncSession) -> list[LibraryRoot]:
    """Raíces con su mapeo cargado, en orden estable."""
    return list((await db.execute(
        select(LibraryRoot)
        .options(selectinload(LibraryRoot.traditions))
        .order_by(LibraryRoot.created_at, LibraryRoot.id)
    )).scalars().all())


def estado_de_raiz(raiz: LibraryRoot) -> str:
    """Estado visible, derivado de la configuración y del disco (no persistido)."""
    if not raiz.enabled:
        return "desactivada"
    try:
        ruta = Path(raiz.path)
        if not ruta.is_dir():
            return "ausente"
        if not os.access(ruta, os.R_OK | os.W_OK | os.X_OK):
            return "sin_permiso"
    except OSError:
        return "ausente"
    return "disponible"


def montajes_libres(raices: Iterable[LibraryRoot]) -> list[Montaje]:
    """Montajes autorizados que aún no son una raíz (comparación canónica)."""
    usadas = {_resolver(r.path) for r in raices}
    return [m for m in rutas_autorizadas() if _resolver(m.path) not in usadas]


async def crear_raiz(
    db: AsyncSession, *, path: str, name: str = "", host_path: str = "",
) -> LibraryRoot:
    """Crea una raíz SOLO si la ruta es un montaje autorizado y válido."""
    existentes = await listar_con_tradiciones(db)
    datos = validar_raiz(path, name=name, host_path=host_path, raices=existentes)
    raiz = LibraryRoot(
        name=datos["name"], path=datos["path"], host_path=datos["host_path"],
        enabled=True, is_default=not existentes,
    )
    db.add(raiz)
    await db.flush()
    if raiz.is_default:
        # La raíz por defecto nace con todas las tradiciones, como la migración.
        for tradicion in ComicTradition:
            db.add(LibraryRootTradition(root_id=raiz.id, tradition=tradicion))
        await db.flush()
    return raiz


async def guardar_mapa(db: AsyncSession, asignaciones: dict[str, str | None]) -> None:
    """Reemplaza el mapa tradición→raíz. No mueve archivos ni cambia `File.root_id`."""
    raices = await listar_con_tradiciones(db)
    por_id = {str(r.id): r for r in raices}
    elegidas: list[tuple[str, UUID]] = []
    for tradicion, root_id in asignaciones.items():
        try:
            valor = ComicTradition(tradicion)
        except ValueError as exc:
            raise RaizInvalidaError("Tradición desconocida.") from exc
        if not root_id:
            continue
        raiz = por_id.get(str(root_id))
        if raiz is None:
            raise RaizInvalidaError("La raíz elegida no existe.")
        if not raiz.enabled:
            raise RaizInvalidaError("No se puede asignar una tradición a una raíz desactivada.")
        elegidas.append((valor.value, raiz.id))
    await db.execute(delete(LibraryRootTradition))
    for tradicion, root_id in elegidas:
        db.add(LibraryRootTradition(root_id=root_id, tradition=ComicTradition(tradicion)))
    await db.flush()


async def cambiar_habilitada(db: AsyncSession, root_id: UUID, enabled: bool) -> LibraryRoot:
    raiz = await db.get(LibraryRoot, root_id)
    if raiz is None:
        raise RaizInvalidaError("La raíz no existe.")
    if raiz.is_default and not enabled:
        raise RaizInvalidaError(
            "La raíz por defecto no puede desactivarse; elige otra por defecto antes.")
    raiz.enabled = enabled
    await db.flush()
    return raiz


async def borrar_raiz(db: AsyncSession, root_id: UUID) -> None:
    """Borra solo una raíz sin archivos; con archivos manda la FK y se explica."""
    raiz = await db.get(LibraryRoot, root_id)
    if raiz is None:
        raise RaizInvalidaError("La raíz no existe.")
    n = (await db.execute(
        select(func.count(File.id)).where(File.root_id == root_id))).scalar() or 0
    if n:
        raise RaizInvalidaError(
            f"Esta raíz tiene {n} archivos registrados; desactívala o reasígnalos primero.")
    if raiz.is_default:
        raise RaizInvalidaError("No se puede borrar la raíz por defecto.")
    await db.delete(raiz)
    await db.flush()


async def cambiar_por_defecto(db: AsyncSession, root_id: UUID) -> LibraryRoot:
    """Elige la raíz de `_Unsorted`; la anterior deja de serlo."""
    raiz = await db.get(LibraryRoot, root_id)
    if raiz is None:
        raise RaizInvalidaError("La raíz no existe.")
    if not raiz.enabled:
        raise RaizInvalidaError("La raíz por defecto debe estar activa.")
    actual = (await db.execute(
        select(LibraryRoot).where(LibraryRoot.is_default.is_(True)))).scalar_one_or_none()
    if actual is not None and actual.id != raiz.id:
        actual.is_default = False
        await db.flush()
    raiz.is_default = True
    await db.flush()
    return raiz
