# ruff: noqa: E501
"""D3-B4 (#233 / BL-R4): ¿qué relación archivo → publicación es «confirmada» y cuál se protege?

Predicado PURO (sin BD) sobre `File` e `Issue`:

- `sin_relacion`: el archivo no está vinculado.
- `confirmada`: hay `metadata.vinculo` VÁLIDO y COHERENTE con la serie del `Issue` (operación y serie
  UUID, `version` conocida y `fecha` ISO parseable). Es la evidencia durable que escribió la
  vinculación 2d; no se inventa ni se marca retroactivamente.
- `manual_sin_comprobante`: `metadata_source='manual'` sin `metadata.vinculo` válido (caminos
  heredados). No se llama «confirmada» (no consta la operación), pero **sí se protege**: es una
  aceptación humana.
- `automatica`: cualquier otra relación (importador/matcher): no se protege y el rescan puede
  re-tríarla como hasta ahora.

Sin usuario, sesión, IP ni auditoría: solo consta operación y fecha. D3 no cambia nada por sí mismo.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

#: Versiones de `metadata.vinculo` que este código SABE interpretar. Lista CERRADA: una versión
#: futura o desconocida no es evidencia de confirmación (no se adivina su esquema).
VERSIONES_CONOCIDAS = frozenset({1})

#: Estados del conjunto cerrado de D3-B4. Los valores son los que viajan en `relacion["estado"]`
#: y en las pruebas; no son texto de pantalla.
SIN_RELACION = "sin_relacion"
CONFIRMADA = "confirmada"
MANUAL_SIN_COMPROBANTE = "manual_sin_comprobante"
AUTOMATICA = "automatica"


class EstadoRelacion(StrEnum):
    SIN_RELACION = SIN_RELACION
    CONFIRMADA = CONFIRMADA
    MANUAL_SIN_COMPROBANTE = MANUAL_SIN_COMPROBANTE
    AUTOMATICA = AUTOMATICA


def _uuid(valor: object) -> str | None:
    """UUID canónico en minúsculas, o `None`. Un UUID mal formado no es evidencia."""
    if not isinstance(valor, str):
        return None
    try:
        return str(UUID(valor))
    except (ValueError, AttributeError):
        return None


def _fecha_valida(valor: object) -> bool:
    """¿Es una fecha ISO que se puede interpretar? La `fecha` de `metadata.vinculo` la escribe la
    operación de vinculación con `datetime.isoformat()`; una cadena inventada no vale como evidencia."""
    if not isinstance(valor, str) or not valor.strip():
        return False
    try:
        datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def vinculo_valido(metadata_: dict | None, series_id: object) -> dict | None:
    """El `metadata.vinculo` si es evidencia completa de una confirmación sobre ESA serie.

    Exige `operacion_id` UUID, `serie_id` UUID e igual a la serie del `Issue`, `version` entera
    **conocida** (`VERSIONES_CONOCIDAS`; hoy solo la 1) y `fecha` ISO. Una versión futura no se
    interpreta: no es evidencia. Sin alguno de esos datos no hay confirmación acreditable (y no se
    rellena a posteriori: D3 prohíbe la retroactividad).
    """
    v = (metadata_ or {}).get("vinculo") if isinstance(metadata_, dict) else None
    if not isinstance(v, dict):
        return None
    if _uuid(v.get("operacion_id")) is None or _uuid(v.get("serie_id")) is None:
        return None
    if series_id is None or _uuid(v["serie_id"]) != _uuid(str(series_id)):
        return None
    version = v.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version not in VERSIONES_CONOCIDAS:
        return None
    if not _fecha_valida(v.get("fecha")):
        return None
    return v


def estado_de_relacion(file, issue) -> EstadoRelacion:
    """El estado D3 de la relación `file -> issue`. `file` e `issue` son filas u objetos con los
    atributos usados (`issue_id`, `metadata_source`, `metadata_`; `issue.series_id`). Sin BD.

    Si `issue_id` apunta a una publicación que no se pudo cargar (`issue is None`), no se puede
    acreditar la coherencia de serie: se clasifica por la procedencia (`manual` o automática),
    nunca como `confirmada` por suposición.
    """
    if getattr(file, "issue_id", None) is None:
        return EstadoRelacion.SIN_RELACION
    if issue is not None and vinculo_valido(getattr(file, "metadata_", None),
                                            getattr(issue, "series_id", None)) is not None:
        return EstadoRelacion.CONFIRMADA
    if str(getattr(file, "metadata_source", None) or "") == "manual":
        return EstadoRelacion.MANUAL_SIN_COMPROBANTE
    return EstadoRelacion.AUTOMATICA


def es_protegida(estado: EstadoRelacion | str) -> bool:
    """¿El cambio automático debe respetar esta relación? `confirmada` y `manual_sin_comprobante` sí;
    `automatica` no; `sin_relacion` no aplica."""
    return estado in (EstadoRelacion.CONFIRMADA, EstadoRelacion.MANUAL_SIN_COMPROBANTE)


def relacion_actual(file, issue) -> dict | None:
    """La huella de contexto que se guarda con una discrepancia (D4): dónde estaba vinculado el
    archivo al detectarla. Sin usuario ni ruta. `operacion_id` es `None` si no consta el comprobante
    (relación manual heredada)."""
    if issue is None or getattr(file, "issue_id", None) is None:
        return None
    v = vinculo_valido(getattr(file, "metadata_", None), getattr(issue, "series_id", None))
    return {
        "issue_id": str(file.issue_id),
        "serie_id": str(getattr(issue, "series_id", "")),
        "operacion_id": str(v["operacion_id"]) if v is not None else None,
    }
