# ruff: noqa: E501
"""D4-B4 (#233 / BL-R4): discrepancias entre una relación protegida y lo que propone una actualización.

Una discrepancia es una **afirmación automática** sobre a qué publicación corresponde un archivo que
difiere de la relación protegida. No se aplica nunca: se registra para que la persona decida.

- Se guarda en `File.metadata_["discrepancias"]` (JSONB, sin migración): lista versionada y acotada.
- `clave` estable = SHA-256 del JSON canónico de la PROPUESTA (origen + destino + discriminantes),
  **sin** fecha, score, nombre de archivo ni ruta. La misma afirmación repetida se reutiliza; una
  afirmación distinta genera otra entrada (no se silencia a la fuente).
- Ciclo cerrado: `pendiente → mantenida | resuelta | obsoleta`. «Mantener lo mío» afecta solo a ESA
  clave y deja un comprobante inmutable `mantener_lo_mio` en `vinculacion_operaciones` (24 h).
- Sin usuario, sesión, IP ni token. Solo lectura de BD y escritura de `metadata_` + comprobante; ni
  bytes, ni rutas, ni archivos.

Las funciones de la primera mitad son PURAS (sin BD) y se prueban sin PostgreSQL. `mantener_lo_mio`
es la acción explícita que confirma una propuesta como «mantener la relación actual».
"""
from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, Issue, VinculacionOperacion
from zascarr.services.relacion_confirmada import relacion_actual
from zascarr.services.tokens_revision import (
    MantenerFirmada,
    verificar_token_mantener,
)
from zascarr.services.vinculacion import (
    ConflictoDeBloqueoError,
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
    _es_interbloqueo,
)

VERSION = 1
CLAVE_METADATA = "discrepancias"
CLAVE_ARCHIVADAS = "discrepancias_archivadas"
#: Tope de entradas activas y de archivadas (la entrada JSONB no puede crecer sin límite: R3 de §6.2).
TOPE = 20
TOPE_ARCHIVADAS = 50

#: Orígenes admitidos por D4 (conjunto cerrado). En el futuro, `fuente:<...>` para una fuente externa.
ORIGEN_RESCAN = "rescan"
ORIGEN_COMICINFO = "comicinfo"
ORIGEN_IMPORTADOR = "importador"
ORIGENES = frozenset({ORIGEN_RESCAN, ORIGEN_COMICINFO, ORIGEN_IMPORTADOR})

PENDIENTE = "pendiente"
MANTENIDA = "mantenida"
RESUELTA = "resuelta"
OBSOLETA = "obsoleta"


class EstadoDiscrepancia(StrEnum):
    PENDIENTE = PENDIENTE
    MANTENIDA = MANTENIDA
    RESUELTA = RESUELTA
    OBSOLETA = OBSOLETA


_ESTADOS_TERMINALES = frozenset({RESUELTA, OBSOLETA})


def origen_valido(origen: object) -> bool:
    """El conjunto de orígenes es cerrado; una fuente futura se expresa `fuente:<valor>`."""
    if not isinstance(origen, str) or not origen:
        return False
    if origen in ORIGENES:
        return True
    return origen.startswith("fuente:") and len(origen) > len("fuente:")


@dataclass(frozen=True)
class Propuesta:
    """Lo que afirma el origen automático sobre el archivo. Solo los campos de aquí entran en la
    `clave`: son la afirmación de identidad y los discriminantes que cambian la decisión.

    `serie_destino_id`/`issue_destino_uuid` son UUID canónicos o `None`; `numero`/`formato` son los
    del destino propuesto (o los del nombre cuando no hay publicación). Nada de fecha, score, ruta
    ni nombre de archivo.
    """
    origen: str
    fuente: str | None = None
    id_externo: str | None = None
    serie_destino_id: str | None = None
    issue_destino_uuid: str | None = None
    numero: str | None = None
    formato: str | None = None
    titulo_norm: str | None = None
    anio: int | None = None

    def __post_init__(self) -> None:
        if not origen_valido(self.origen):
            raise ValueError(f"origen de discrepancia no admitido: {self.origen!r}")

    def como_dict(self) -> dict[str, object]:
        return {
            "origen": self.origen,
            "fuente": self.fuente,
            "id_externo": self.id_externo,
            "serie_destino_id": self.serie_destino_id,
            "issue_destino_uuid": self.issue_destino_uuid,
            "numero": self.numero,
            "formato": self.formato,
            "titulo_norm": self.titulo_norm,
            "anio": self.anio,
        }


def _canonico(propuesta: Propuesta) -> str:
    # `sort_keys` + separadores sin espacios: la MISMA afirmación siempre da el mismo texto.
    return json.dumps(propuesta.como_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def clave_de(propuesta: Propuesta) -> str:
    """Clave estable (SHA-256 hex) de la afirmación. Sin fecha, score, nombre de archivo ni ruta."""
    return hashlib.sha256(_canonico(propuesta).encode("utf-8")).hexdigest()


def _fecha(ahora: datetime | str | float | None = None) -> str:
    if isinstance(ahora, str):
        return ahora
    if isinstance(ahora, (int, float)):
        return datetime.fromtimestamp(ahora, UTC).isoformat()
    return (ahora or datetime.now(UTC)).isoformat()


def crear_discrepancia(propuesta: Propuesta, relacion: dict, *, ahora: datetime | str | float | None = None) -> dict:
    """La entrada nueva, en estado `pendiente`. `relacion` es la huella de D3 en el momento de detectar."""
    return {
        "version": VERSION,
        "clave": clave_de(propuesta),
        "origen": propuesta.origen,
        "propuesta": propuesta.como_dict(),
        "relacion": dict(relacion),
        "estado": PENDIENTE,
        "observada_en": _fecha(ahora),
    }


def _lista(metadata_: dict | None, clave: str) -> list[dict]:
    """Lee una lista de entradas descartando lo mal formado (JSONB editado a mano o de una versión
    futura): no puede tumbar un rescan ni una ficha."""
    bruto = (metadata_ or {}).get(clave) if isinstance(metadata_, dict) else None
    if not isinstance(bruto, list):
        return []
    return [dict(e) for e in bruto if isinstance(e, dict) and isinstance(e.get("clave"), str)]


def _copiar(metadata_: dict | None) -> dict:
    return dict(metadata_ or {})


def _limitar(activas: list[dict], archivadas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Tope/archivado: primero se archivan las terminales (`resuelta`/`obsoleta`) más antiguas; si
    siguen sobrando (p. ej. todas pendientes), las más antiguas, para no hacer crecer el JSONB."""
    def _observada(e: dict) -> str:
        v = e.get("observada_en")
        return v if isinstance(v, str) else ""

    while len(activas) > TOPE:
        terminales = [i for i, e in enumerate(activas) if e.get("estado") in _ESTADOS_TERMINALES]
        indice = min(terminales, key=lambda i: _observada(activas[i])) if terminales else 0
        archivadas.append(activas.pop(indice))
    archivadas.sort(key=_observada)
    del archivadas[: max(0, len(archivadas) - TOPE_ARCHIVADAS)]
    return activas, archivadas


def _guardar(metadata_: dict, activas: list[dict], archivadas: list[dict]) -> dict:
    salida = _copiar(metadata_)
    if activas:
        salida[CLAVE_METADATA] = activas
    else:
        salida.pop(CLAVE_METADATA, None)
    if archivadas:
        salida[CLAVE_ARCHIVADAS] = archivadas
    else:
        salida.pop(CLAVE_ARCHIVADAS, None)
    return salida


def leer(metadata_: dict | None) -> list[dict]:
    """Las entradas activas (copia), sin la lista de archivadas."""
    return _lista(metadata_, CLAVE_METADATA)


def entrada(metadata_: dict | None, clave: str) -> dict | None:
    return next((e for e in _lista(metadata_, CLAVE_METADATA) if e.get("clave") == clave), None)


def registrar(metadata_: dict | None, nueva: dict, *, ahora: datetime | str | float | None = None) -> tuple[dict, bool]:
    """Registra (o reutiliza) una discrepancia. Devuelve `(metadata nuevo, cambió)`.

    - Misma clave y misma relación: se reutiliza la entrada. Si estaba `obsoleta`, vuelve a
      `pendiente`; si estaba `mantenida`, sigue mantenida (la decisión de la persona no se pisa).
    - Misma clave con OTRA relación: la anterior pasa al archivo como `obsoleta` y la afirmación
      vuelve como `pendiente` para la relación actual.
    - Clave nueva: se añade como `pendiente`.
    """
    activas = _lista(metadata_, CLAVE_METADATA)
    archivadas = _lista(metadata_, CLAVE_ARCHIVADAS)
    ahora_iso = (nueva.get("observada_en") if isinstance(nueva.get("observada_en"), str)
                 else _fecha(ahora))
    for i, e in enumerate(activas):
        if e.get("clave") != nueva.get("clave"):
            continue
        if e.get("relacion") == nueva.get("relacion"):
            estado = e.get("estado")
            if estado == OBSOLETA:
                activas[i] = {**nueva, "observada_en": ahora_iso}
            else:
                # No duplica ni cambia la decisión; solo refresca cuándo se volvió a observar.
                activas[i] = {**e, "observada_en": ahora_iso}
            return _guardar(metadata_, *(_limitar(activas, archivadas))), True
        archivadas.append({**e, "estado": OBSOLETA})
        activas[i] = {**nueva, "observada_en": ahora_iso}
        return _guardar(metadata_, *(_limitar(activas, archivadas))), True
    activas.append({**nueva, "observada_en": ahora_iso})
    return _guardar(metadata_, *(_limitar(activas, archivadas))), True


def marcar_estado_por_relacion(metadata_: dict | None, relacion: dict | None) -> dict:
    """Cierra las entradas que ya no describen la relación actual: `resuelta` si la corrección
    coincide con la publicación propuesta y `obsoleta` en cualquier otro caso. No toca las que ya
    son terminales."""
    activas = _lista(metadata_, CLAVE_METADATA)
    if not activas:
        return _copiar(metadata_)
    actual = relacion or {}
    for e in activas:
        if e.get("estado") not in (PENDIENTE, MANTENIDA):
            continue
        if e.get("relacion") == actual:
            continue
        propuesta = e.get("propuesta") if isinstance(e.get("propuesta"), dict) else {}
        if actual.get("issue_id") is not None and propuesta.get("issue_destino_uuid") == actual.get("issue_id"):
            e["estado"] = RESUELTA
        else:
            e["estado"] = OBSOLETA
    return _guardar(metadata_, activas, _lista(metadata_, CLAVE_ARCHIVADAS))


def pendientes(metadata_: dict | None, relacion: dict | None) -> list[dict]:
    """Las discrepancias que la ficha puede avisar AHORA: `pendiente` y de la relación actual."""
    return [e for e in _lista(metadata_, CLAVE_METADATA)
            if e.get("estado") == PENDIENTE and e.get("relacion") == relacion]


def mantener(metadata_: dict | None, clave: str, *, operacion_id: str, fecha: str) -> tuple[dict | None, bool]:
    """Marca la entrada `mantenida` (solo si estaba `pendiente`). Devuelve `(metadata, actualizada)`.

    - `(None, False)` si la clave no existe o no es mantenible.
    - `(metadata, False)` si ya estaba `mantenida`: idempotente, sin escribir de nuevo.
    - `(metadata, True)` si pasa de `pendiente` a `mantenida`.
    """
    activas = _lista(metadata_, CLAVE_METADATA)
    for i, e in enumerate(activas):
        if e.get("clave") != clave:
            continue
        if e.get("estado") == MANTENIDA:
            return _copiar(metadata_), False
        if e.get("estado") != PENDIENTE:
            return None, False
        activas[i] = {**e, "estado": MANTENIDA, "mantenida_en": fecha, "operacion_id": operacion_id}
        return _guardar(metadata_, activas, _lista(metadata_, CLAVE_ARCHIVADAS)), True
    return None, False


# ── «Mantener lo mío»: acción explícita con token y comprobante inmutable ───────────────────────

RETENCION_HORAS = 24
LOTE_DE_PURGA = 200
_ESPACIO_OPERACION = "mantener_op:"

MENSAJES = {
    "archivo_inexistente": "Ese archivo ya no está registrado en ZascArr. No se ha cambiado nada.",
    "sin_relacion": "Ese archivo ya no está vinculado a ninguna publicación. No se ha cambiado nada.",
    "no_existe": "Esa propuesta ya no está en la ficha de la serie. No se ha cambiado nada.",
    "no_pendiente": "Esa propuesta ya no se puede mantener (la relación o la propuesta cambiaron). No se ha cambiado nada.",
    "cambio_desde_la_vista_previa": "La relación o la propuesta han cambiado desde que abriste la ficha. No se ha cambiado nada: vuelve a mirarla.",
}


@dataclass(frozen=True)
class ResultadoMantener:
    version: int
    operacion_id: str
    file_id: str
    clave: str
    resultado: str          # mantenida | ya_mantenida | omitido
    motivo: str | None
    mensaje: str
    fecha: str | None


async def mantener_lo_mio(db: AsyncSession, token: str, *, secret: str,
                          ahora: float | None = None) -> ResultadoMantener:
    """Confirma «Mantener lo mío» para LA propuesta firmada. No cambia la relación ni los archivos."""
    firmado = verificar_token_mantener(token, secret, ahora=ahora, ignorar_caducidad=True)
    if firmado is None:
        raise TokenInvalidoError("Esa confirmación no es válida: vuelve a abrirla desde la serie.")
    vigente = verificar_token_mantener(token, secret, ahora=ahora) is not None
    commit_pedido = False
    try:
        resultado = await _en_transaccion(db, firmado, vigente)
        commit_pedido = True
        return resultado
    except BaseException as exc:
        with contextlib.suppress(Exception):
            await db.rollback()
        if commit_pedido and isinstance(exc, Exception):
            raise ResultadoInciertoError("No se pudo confirmar si se guardó «Mantener lo mío».") from None
        if isinstance(exc, DBAPIError) and _es_interbloqueo(exc):
            raise ConflictoDeBloqueoError("Otra operación coincidió; vuelve a intentarlo.") from None
        raise


async def _en_transaccion(db: AsyncSession, firmado: MantenerFirmada, vigente: bool) -> ResultadoMantener:
    file_id = UUID(firmado.file_id)
    clave = firmado.clave
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k || :o, 0))"),
                     {"k": _ESPACIO_OPERACION, "o": firmado.operacion})

    # 1. ¿Ya se aplicó ESTA operación? El comprobante inmutable es la fuente.
    previo = (await db.execute(select(VinculacionOperacion).where(
        VinculacionOperacion.operacion_id == UUID(firmado.operacion)))).scalar_one_or_none()
    if previo is not None:
        return ResultadoMantener(VERSION, firmado.operacion, firmado.file_id, clave, "ya_mantenida", None,
                                 "Ya estaba mantenida: no se ha cambiado nada.", None)
    if not vigente:
        raise TokenCaducadoError(
            "Esta confirmación caducó y no se llegó a aplicar: no hay cambios. Vuelve a abrirla.",
            puede_haberse_aplicado=False)

    # 2. El archivo y su relación, con la fila bloqueada.
    f = (await db.execute(select(File.id, File.issue_id, File.metadata_).where(File.id == file_id)
                          .with_for_update())).first()
    if f is None:
        return await _omitir(db, firmado, "archivo_inexistente")
    issue = None
    if f.issue_id is not None:
        issue = (await db.execute(select(Issue.id, Issue.series_id, Issue.issue_number, Issue.format)
                                  .where(Issue.id == f.issue_id))).first()
    relacion = relacion_actual(f, issue) if issue is not None else None
    if relacion is None:
        return await _omitir(db, firmado, "sin_relacion")

    # La relación que se vio al abrir la ficha tiene que seguir siendo la misma (incluida la
    # procedencia: si el vínculo cambió, la decisión anterior ya no vale).
    operacion_actual = relacion.get("operacion_id")
    if (relacion.get("issue_id") != firmado.issue_id or relacion.get("serie_id") != firmado.serie_id
            or (operacion_actual or "00000000-0000-0000-0000-000000000000") != firmado.vinculo_operacion):
        return await _omitir(db, firmado, "cambio_desde_la_vista_previa")
    if entrada(f.metadata_, clave) is None:
        return await _omitir(db, firmado, "no_existe")

    fecha = _fecha(ahora=None)
    nuevo_meta, actualizada = mantener(f.metadata_, clave, operacion_id=firmado.operacion, fecha=fecha)
    if nuevo_meta is None:
        return await _omitir(db, firmado, "no_pendiente")
    if not actualizada:
        return ResultadoMantener(VERSION, firmado.operacion, firmado.file_id, clave, "ya_mantenida", None,
                                 "Ya estaba mantenida: no se ha cambiado nada.", fecha)
    await db.execute(
        text("UPDATE files SET metadata = CAST(:m AS jsonb) WHERE id = :f"),
        {"m": json.dumps(nuevo_meta, ensure_ascii=False), "f": file_id})
    db.add(VinculacionOperacion(
        operacion_id=UUID(firmado.operacion), series_id=UUID(firmado.serie_id),
        resultado={"version": VERSION, "tipo": "mantener_lo_mio", "operacion_id": firmado.operacion,
                   "file_id": firmado.file_id, "clave": clave, "fecha": fecha},
        token_hasta=datetime.fromtimestamp(firmado.caduca, UTC)))
    await db.flush()
    await _purgar(db)
    await db.commit()
    return ResultadoMantener(VERSION, firmado.operacion, firmado.file_id, clave, "mantenida", None,
                             "Listo: se mantiene la publicación que confirmaste. La fuente se seguirá "
                             "consultando y una propuesta distinta volverá a aparecer.", fecha)


async def _omitir(db: AsyncSession, firmado: MantenerFirmada, motivo: str) -> ResultadoMantener:
    await db.commit()
    return ResultadoMantener(VERSION, firmado.operacion, firmado.file_id, firmado.clave, "omitido", motivo,
                             MENSAJES[motivo], None)


async def _purgar(db: AsyncSession) -> None:
    """Borra, de forma acotada, comprobantes viejos de este tipo (mismas dos condiciones que la
    vinculación: creados hace más de 24 h y con el token ya caducado). Solo `vinculacion_operaciones`."""
    await db.execute(text(
        "DELETE FROM vinculacion_operaciones WHERE operacion_id IN ("
        " SELECT operacion_id FROM vinculacion_operaciones"
        " WHERE creada < now() - make_interval(hours => :h) AND token_hasta < now()"
        " ORDER BY creada LIMIT :n FOR UPDATE SKIP LOCKED)"), {"h": RETENCION_HORAS, "n": LOTE_DE_PURGA})
