"""#488 / BL-CNV6: ¿está este archivo de la biblioteca compartido por un programa de descargas?

Una sola puerta para conversión y etiquetado. **Fallo cerrado**: solo se permite escribir si
todas las fuentes disponibles respondieron y ninguna afirma que el archivo se comparte. Sin
fuentes, cliente caído o ruta que no se sabe traducir ⇒ `no_se_sabe` (se trata como bloqueo).

Sin socket Docker, sin root, sin credenciales en logs y sin acciones sobre Transmission/aMule.
Las fuentes son:

- **carpetas declaradas** por la persona en Ajustes (rutas absolutas conocidas del contenedor);
- **Transmission**, si está encendido: todos los torrents y sus archivos, traduciendo rutas
  host→contenedor con los pares conocidos;
- **aMule**, si está encendido: lo que exponga `amuleweb`. Hoy no hay una API fiable de
  compartidos (BL-CNV0/P6); si el cliente no lo expone, `no_se_sabe` y las carpetas declaradas
  son la vía segura.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import structlog

from zascarr.config import get_settings

logger = structlog.get_logger()


class EstadoComparticion(StrEnum):
    COMPARTIDO = "compartido"
    NO_COMPARTIDO = "no_compartido"
    NO_SE_SABE = "no_se_sabe"


@dataclass(frozen=True)
class Decision:
    """Resultado cerrado del guardián. `bloquea` es lo que consumen los escritores."""

    estado: EstadoComparticion
    causa: str
    fuentes: tuple[str, ...] = ()

    @property
    def bloquea(self) -> bool:
        return self.estado is not EstadoComparticion.NO_COMPARTIDO

    @property
    def mensaje(self) -> str:
        if self.estado is EstadoComparticion.COMPARTIDO:
            return (
                f"Cuidado: este archivo parece compartido ({self.causa}). "
                "Escribir puede romper la siembra."
            )
        if self.estado is EstadoComparticion.NO_SE_SABE:
            return (
                "No podemos saber si este archivo se comparte; escribir puede romper la siembra. "
                "Declara las carpetas en Ajustes («Archivos compartidos»)."
            )
        return "No consta que se comparta."


def _bajo(ruta: str, raiz: str) -> bool:
    """¿`ruta` está bajo `raiz`? Por raíz real, no por prefijo de texto."""
    try:
        return os.path.commonpath([ruta, raiz]) == raiz
    except ValueError:
        return False


def _real(ruta: str | Path) -> str | None:
    try:
        return os.path.realpath(os.fspath(ruta))
    except (OSError, TypeError):
        return None


def _raices_declaradas(settings) -> tuple[list[str], str | None]:
    """Las carpetas declaradas válidas, o un motivo de fallo cerrado."""
    brutas = getattr(settings, "carpetas_compartidas", None) or []
    if not isinstance(brutas, (list, tuple)):
        return [], "La lista de carpetas compartidas no es válida."
    raices: list[str] = []
    for bruta in brutas:
        if not isinstance(bruta, str) or not bruta or not os.path.isabs(bruta):
            return [], "Hay una carpeta compartida que no es una ruta absoluta."
        partes = Path(bruta).parts
        if ".." in partes:
            return [], "Hay una carpeta compartida con «..»."
        real = _real(bruta)
        if real is None:
            return [], "Hay una carpeta compartida que no se puede resolver."
        raices.append(real)
    return raices, None


def _pares_host_a_contenedor(settings) -> list[tuple[str, str]]:
    """Pares conocidos para traducir rutas de cliente a rutas del contenedor."""
    pares: list[tuple[str, str]] = []
    for origen, destino in (
        (getattr(settings, "host_library_dir", ""), getattr(settings, "library_path", None)),
        (getattr(settings, "transmission_download_dir", ""),
         getattr(settings, "downloads_path", None)),
    ):
        if not origen or destino is None:
            continue
        raiz_host = _real(str(origen))
        raiz_destino = _real(str(destino))
        if raiz_host and raiz_destino and raiz_host != raiz_destino:
            pares.append((raiz_host, raiz_destino))
    return pares


def traducir_a_contenedor(ruta: str | Path, settings) -> str | None:
    """Ruta del contenedor a partir de una ruta host/contenedor conocida.

    Devuelve `None` si no se puede traducir: en ese caso el guardián falla cerrado.
    """
    real = _real(ruta)
    if real is None:
        return None
    # Primero los pares host→contenedor; si ya está en una raíz del contenedor,
    # la ruta se acepta tal cual.
    for origen, destino in _pares_host_a_contenedor(settings):
        if _bajo(real, origen):
            rel = os.path.relpath(real, origen)
            return os.path.normpath(os.path.join(destino, rel))
    for campo in ("library_path", "downloads_path", "amule_incoming_dir"):
        raiz = getattr(settings, campo, None)
        if raiz is not None and _bajo(real, _real(str(raiz)) or ""):
            return real
    return None


def _causa_de_transmission(torrent: dict) -> str:
    nombre = str(torrent.get("name") or "").strip()
    return f"lo comparte Transmission{(' («' + nombre + '»)') if nombre else ''}"


def _decision(estado: EstadoComparticion, causa: str, fuentes: list[str]) -> Decision:
    return Decision(estado, causa, tuple(dict.fromkeys(fuentes)))


async def estado_de_comparticion(
    path: Path | str, *, settings=None, transmission=None, amule=None
) -> Decision:
    """La decisión del guardián para ESTA ruta. Consulta todas las fuentes disponibles."""
    settings = settings or get_settings()
    fuentes: list[str] = []
    raices, error_raices = _raices_declaradas(settings)
    if error_raices:
        return _decision(EstadoComparticion.NO_SE_SABE, error_raices, fuentes)
    if raices:
        fuentes.append("carpetas declaradas")
    real = _real(path)
    if real is None:
        return _decision(EstadoComparticion.NO_SE_SABE,
                         "No se puede resolver la ruta del archivo.", fuentes)
    if any(_bajo(real, raiz) for raiz in raices):
        return _decision(EstadoComparticion.COMPARTIDO,
                         "está en una carpeta que has declarado como compartida", fuentes)

    if getattr(settings, "transmission_enabled", False):
        fuentes.append("Transmission")
        try:
            cliente = transmission or _cliente_transmission(settings)
            torrentes = await cliente.list_torrents()
        except Exception:  # noqa: BLE001 — cualquier fallo del cliente es fallo cerrado
            logger.warning("compartidos.transmission_fallida")
            return _decision(EstadoComparticion.NO_SE_SABE,
                             "Transmission no responde; no se puede comprobar.", fuentes)
        for torrent in torrentes:
            direccion = torrent.get("downloadDir")
            if not isinstance(direccion, str):
                return _decision(EstadoComparticion.NO_SE_SABE,
                                 "Transmission devolvió un torrent sin carpeta.", fuentes)
            for fichero in torrent.get("files") or []:
                nombre = fichero.get("name") if isinstance(fichero, dict) else None
                if not isinstance(nombre, str):
                    return _decision(EstadoComparticion.NO_SE_SABE,
                                     "Transmission devolvió un archivo sin nombre.", fuentes)
                traducida = traducir_a_contenedor(os.path.join(direccion, nombre), settings)
                if traducida is None:
                    return _decision(EstadoComparticion.NO_SE_SABE,
                                     "No se sabe traducir una ruta de Transmission.", fuentes)
                if _bajo(real, traducida):
                    return _decision(EstadoComparticion.COMPARTIDO,
                                     _causa_de_transmission(torrent), fuentes)

    if getattr(settings, "amule_enabled", False):
        fuentes.append("aMule")
        cliente = amule or _cliente_amule(settings)
        metodo = getattr(cliente, "list_shared_paths", None)
        if metodo is None:
            # P6/BL-CNV0: amuleweb no expone de forma fiable sus compartidos.
            return _decision(EstadoComparticion.NO_SE_SABE,
                             "aMule no permite saber qué comparte.", fuentes)
        try:
            compartidos = await metodo()
        except Exception:  # noqa: BLE001
            logger.warning("compartidos.amule_fallida")
            return _decision(EstadoComparticion.NO_SE_SABE,
                             "aMule no responde; no se puede comprobar.", fuentes)
        if compartidos is None:
            # P6/BL-CNV0: amuleweb no expone de forma fiable sus compartidos.
            return _decision(EstadoComparticion.NO_SE_SABE,
                             "aMule no permite saber qué comparte.", fuentes)
        for ruta in compartidos:
            traducida = traducir_a_contenedor(ruta, settings)
            if traducida is None:
                return _decision(EstadoComparticion.NO_SE_SABE,
                                 "No se sabe traducir una ruta de aMule.", fuentes)
            if _bajo(real, traducida):
                return _decision(EstadoComparticion.COMPARTIDO, "lo comparte aMule", fuentes)

    if not fuentes:
        return _decision(
            EstadoComparticion.NO_SE_SABE,
            "No hay ninguna fuente: ni carpetas declaradas ni Transmission/aMule encendidos.",
            fuentes,
        )
    return _decision(EstadoComparticion.NO_COMPARTIDO, "ninguna fuente lo comparte", fuentes)


def _cliente_transmission(settings):
    from zascarr.services.transmission import TransmissionClient

    return TransmissionClient()


def _cliente_amule(settings):
    from zascarr.services.amule import AMuleClient

    return AMuleClient()
