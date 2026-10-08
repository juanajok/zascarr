# ruff: noqa: E501
"""Tokens firmados de la superficie de revisión (rebanada 2, D9).

Un formulario nunca reenvía datos sueltos: reenvía un token que el SERVIDOR firmó (HMAC, la misma clave que
firma la cookie de sesión, `auth.sign_token`). El patrón nació en Deseados (`orchestrator.crear_token_candidato`)
tras un hallazgo de revisión: un formulario manipulado podía colar cualquier dato.

Cada token lleva tres cosas, y verificarlo exige que coincidan las tres:
- un **propósito** (`candidata`, `alta` y, más adelante, `vincular`): un token de un paso no sirve en otro;
- un **contexto** (aquí, la `clave` del grupo): no se puede usar sobre otra carpeta;
- una **caducidad corta** (15 min).

IMPORTANTE: un token garantiza la INTEGRIDAD de lo que vio la persona, **no** que una URL externa sea
segura. Por eso la `cover_url` que lleve una candidata se valida aparte (H1, `utils/url_portada.py`), tanto
al emitir el token como al usarlo.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from uuid import UUID

from zascarr.models import ComicTradition, IssueFormat, MetadataSource
from zascarr.services.auth import sign_token, verify_token
from zascarr.services.discovery import CAMPO_ID_EXTERNO

TTL_SEGUNDOS = 15 * 60
PROPOSITO_CANDIDATA = "candidata"
PROPOSITO_ALTA = "alta"
PROPOSITO_VINCULAR = "vincular"
#: La descripción que viaja en el token se recorta: no hace falta entera para dar de alta una serie.
MAX_DESCRIPCION = 1000


def crear_token(proposito: str, contexto: str, datos: dict, secret: str, *,
                ahora: float | None = None, ttl: int = TTL_SEGUNDOS) -> str:
    """Token firmado de `datos`, ligado a `proposito` y `contexto`. Sin clave no se firma nada: una firma con
    una clave vacía la puede falsificar cualquiera."""
    if not secret:
        raise ValueError("No hay clave del servidor con la que firmar")
    inicio = time.time() if ahora is None else ahora
    payload = {"p": proposito, "c": contexto, "d": datos, "exp": int(inicio + ttl)}
    crudo = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    return sign_token(base64.urlsafe_b64encode(crudo).decode(), secret)


def _verificar(token: str, proposito: str, contexto: str, secret: str, *,
               ahora: float | None = None) -> tuple[dict, int] | None:
    """(datos, caducidad) de un token válido, o `None`. Nunca lanza con un token ausente o malformado."""
    if not token or not secret or not isinstance(token, str):
        return None
    crudo = verify_token(token, secret)
    if crudo is None:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(crudo.encode()).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("p") != proposito or payload.get("c") != contexto:
        return None
    caduca = payload.get("exp")
    ahora_ = time.time() if ahora is None else ahora
    if not isinstance(caduca, int) or isinstance(caduca, bool) or caduca < ahora_:
        return None
    datos = payload.get("d")
    return (datos, caduca) if isinstance(datos, dict) else None


def verificar_token(token: str, proposito: str, contexto: str, secret: str, *,
                    ahora: float | None = None) -> dict | None:
    """Los datos del token, o `None` si falta, está manipulado o no es de este propósito, de este contexto o
    ha caducado. Nunca lanza con un token ausente o malformado."""
    verificado = _verificar(token, proposito, contexto, secret, ahora=ahora)
    return verificado[0] if verificado else None


@dataclass(frozen=True)
class CandidataFirmada:
    """Lo que el servidor vio en una fuente y la persona eligió: es lo ÚNICO que se usará para dar de alta."""
    fuente: str
    id_externo: str
    titulo: str
    anio: int | None
    tradicion: str
    descripcion: str | None
    cover_url: str | None


def crear_token_candidata(clave: str, c: CandidataFirmada, secret: str, *, ahora: float | None = None) -> str:
    return crear_token(PROPOSITO_CANDIDATA, clave, {
        "fuente": c.fuente, "id": c.id_externo, "titulo": c.titulo, "anio": c.anio,
        "tradicion": c.tradicion, "descripcion": (c.descripcion or "")[:MAX_DESCRIPCION] or None,
        "cover_url": c.cover_url,
    }, secret, ahora=ahora)


def verificar_token_candidata(token: str, clave: str, secret: str, *,
                              ahora: float | None = None) -> CandidataFirmada | None:
    """La candidata firmada, o `None`. Además de la firma comprueba la FORMA de cada campo: el contenido de un
    token válido sigue sin darse por bueno si no tiene el tipo esperado."""
    d = verificar_token(token, PROPOSITO_CANDIDATA, clave, secret, ahora=ahora)
    if d is None:
        return None
    # Cadenas REALES y no vacías (un `None` no puede convertirse en «None»), fuente y tradición dentro de sus
    # enumeraciones, año entero (un booleano no es un año) y el resto de campos opcionales con su tipo.
    fuente, id_externo, titulo, tradicion = d.get("fuente"), d.get("id"), d.get("titulo"), d.get("tradicion")
    if not all(isinstance(v, str) and v.strip() for v in (fuente, id_externo, titulo, tradicion)):
        return None
    if fuente not in {f.value for f in MetadataSource} or tradicion not in {t.value for t in ComicTradition}:
        return None
    anio = d.get("anio")
    if anio is not None and (not isinstance(anio, int) or isinstance(anio, bool)):
        return None
    descripcion, cover = d.get("descripcion"), d.get("cover_url")
    if (descripcion is not None and not isinstance(descripcion, str)) or (
            cover is not None and not isinstance(cover, str)):
        return None
    return CandidataFirmada(fuente, id_externo, titulo, anio, tradicion, descripcion, cover)


# ── Token del alta (2b) ──────────────────────────────────────────────────────────────────────────

MODOS_DE_ALTA = ("crear", "reutilizar")
CRITERIOS_DE_REUTILIZACION = ("identificador", "eleccion")
ORIGENES_DE_ALTA = ("descubrir", "manual")


@dataclass(frozen=True)
class AltaFirmada:
    """Lo que la persona vio en la vista previa del alta: es lo ÚNICO que ejecuta la confirmación.

    `modo`: `crear` una serie nueva o `reutilizar` una existente (sin tocarla). `vistas`: los ids de las series
    parecidas que la persona vio; si al confirmar aparecen OTRAS, el alta se rechaza. `operacion` identifica
    esta vista previa (idempotencia y deshacer); no es un identificador de sesión.
    """
    clave: str
    modo: str
    origen: str
    fuente: str | None
    id_externo: str | None
    titulo: str
    anio: int | None
    tradicion: str
    descripcion: str | None
    cover_url: str | None
    serie_id: str | None
    vistas: tuple[str, ...]
    operacion: str
    #: Solo con `modo == "reutilizar"`: `identificador` (la coincidencia exacta por id externo, que se REVALIDA al
    #: confirmar) o `eleccion` (la persona eligió una parecida: nunca se le atribuye una coincidencia por id).
    criterio: str | None = None
    #: Instante (época, segundos) hasta el que el token es válido: `exp` del propio token, ya verificado.
    caduca: int = 0


def crear_token_alta(a: AltaFirmada, secret: str, *, ahora: float | None = None) -> str:
    return crear_token(PROPOSITO_ALTA, a.clave, {
        "modo": a.modo, "origen": a.origen, "fuente": a.fuente, "id": a.id_externo, "titulo": a.titulo,
        "anio": a.anio, "tradicion": a.tradicion, "descripcion": (a.descripcion or "")[:MAX_DESCRIPCION] or None,
        "cover_url": a.cover_url, "serie_id": a.serie_id, "vistas": sorted(a.vistas), "operacion": a.operacion,
        "criterio": a.criterio,
    }, secret, ahora=ahora)


def _contexto_del_token(token: str, secret: str) -> str | None:
    """El contexto que lleva un token YA firmado, para tokens cuya confirmación recibe solo el token. La firma,
    el propósito y la caducidad se comprueban después en `verificar_token`; esto solo lo lee."""
    if not token or not secret or not isinstance(token, str):
        return None
    crudo = verify_token(token, secret)
    if crudo is None:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(crudo.encode()).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    contexto = payload.get("c") if isinstance(payload, dict) else None
    return contexto if isinstance(contexto, str) and contexto else None


def _uuid_texto(v: object) -> bool:
    if not isinstance(v, str):
        return False
    try:
        return str(UUID(v)) == v
    except ValueError:
        return False


def verificar_token_alta(token: str, secret: str, *, ahora: float | None = None) -> AltaFirmada | None:
    """El alta firmada, o `None`. La confirmación recibe SOLO el token, así que el contexto (la `clave` del grupo
    desde el que se hizo la vista previa) se lee de dentro del token firmado; firma, propósito y caducidad se
    comprueban igual, y después la FORMA de cada campo (defensa de esquema: una firma válida no vale por sí sola)."""
    clave = _contexto_del_token(token, secret)
    if clave is None:
        return None
    verificado = _verificar(token, PROPOSITO_ALTA, clave, secret, ahora=ahora)
    if verificado is None:
        return None
    d, caduca = verificado
    modo, origen, titulo, tradicion = d.get("modo"), d.get("origen"), d.get("titulo"), d.get("tradicion")
    if not all(isinstance(v, str) and v.strip() for v in (modo, origen, titulo, tradicion)):
        return None
    if modo not in MODOS_DE_ALTA or origen not in ORIGENES_DE_ALTA:
        return None
    if tradicion not in {t.value for t in ComicTradition}:
        return None
    fuente, id_externo, serie_id = d.get("fuente"), d.get("id"), d.get("serie_id")
    if origen == "descubrir":
        if not (isinstance(fuente, str) and fuente in {f.value for f in CAMPO_ID_EXTERNO}
                and isinstance(id_externo, str) and id_externo.strip()):
            return None
    elif fuente is not None or id_externo is not None:
        return None
    criterio = d.get("criterio")
    if modo == "reutilizar":
        if serie_id is None or criterio not in CRITERIOS_DE_REUTILIZACION:
            return None
        if criterio == "identificador" and origen != "descubrir":
            return None
    elif criterio is not None:
        return None
    if serie_id is not None and not _uuid_texto(serie_id):
        return None
    anio = d.get("anio")
    if anio is not None and (not isinstance(anio, int) or isinstance(anio, bool)):
        return None
    descripcion, cover = d.get("descripcion"), d.get("cover_url")
    if (descripcion is not None and not isinstance(descripcion, str)) or (
            cover is not None and not isinstance(cover, str)):
        return None
    vistas, operacion = d.get("vistas"), d.get("operacion")
    if not isinstance(vistas, list) or not all(_uuid_texto(v) for v in vistas) or not _uuid_texto(operacion):
        return None
    return AltaFirmada(clave, modo, origen, fuente, id_externo, titulo, anio, tradicion, descripcion, cover,
                       serie_id, tuple(vistas), operacion, criterio, caduca)


# ── Token de la vinculación (2c) ─────────────────────────────────────────────────────────────────

MAX_ARCHIVOS_FIRMADOS = 100
MAX_NUMERO = 20


@dataclass(frozen=True)
class ArchivoFirmado:
    """Lo que la persona vio de UN archivo: es lo que la confirmación (2d) comprobará de nuevo antes de vincular.
    `tamano` y `mtime_ns` son los de `stat` en la vista previa (no un hash: el contenido no se lee)."""
    id: str
    numero: str
    formato: str
    tamano: int
    mtime_ns: int


@dataclass(frozen=True)
class VinculacionFirmada:
    """La operación aprobada: serie, los archivos marcados Y ejecutables con su número y edición. El contexto del
    token es la `clave` del grupo; la `series_id` va firmada dentro (las dos son inseparables del token)."""
    clave: str
    series_id: str
    operacion: str
    archivos: tuple[ArchivoFirmado, ...]
    caduca: int = 0


def crear_token_vinculacion(v: VinculacionFirmada, secret: str, *, ahora: float | None = None) -> str:
    return crear_token(PROPOSITO_VINCULAR, v.clave, {
        "serie_id": v.series_id, "operacion": v.operacion,
        "archivos": [{"id": a.id, "numero": a.numero, "formato": a.formato, "tamano": a.tamano,
                      "mtime_ns": a.mtime_ns} for a in sorted(v.archivos, key=lambda a: a.id)],
    }, secret, ahora=ahora)


def verificar_token_vinculacion(token: str, secret: str, *, ahora: float | None = None) -> VinculacionFirmada | None:
    """La vinculación firmada, o `None`. Firma, propósito y caducidad como siempre; además el ESQUEMA (UUID
    canónicos, formatos de la enumeración, números no vacíos, enteros no booleanos, sin ids repetidos y a lo sumo
    `MAX_ARCHIVOS_FIRMADOS`). El contexto (la `clave`) se lee del propio token: la confirmación recibe solo el token."""
    clave = _contexto_del_token(token, secret)
    if clave is None:
        return None
    verificado = _verificar(token, PROPOSITO_VINCULAR, clave, secret, ahora=ahora)
    if verificado is None:
        return None
    d, caduca = verificado
    if not _uuid_texto(d.get("serie_id")) or not _uuid_texto(d.get("operacion")):
        return None
    crudos = d.get("archivos")
    if not isinstance(crudos, list) or not crudos or len(crudos) > MAX_ARCHIVOS_FIRMADOS:
        return None
    formatos = {f.value for f in IssueFormat}
    archivos: list[ArchivoFirmado] = []
    for a in crudos:
        if not isinstance(a, dict) or not _uuid_texto(a.get("id")):
            return None
        numero, formato, tamano, mtime = a.get("numero"), a.get("formato"), a.get("tamano"), a.get("mtime_ns")
        if not (isinstance(numero, str) and numero.strip() and numero == numero.strip() and len(numero) <= MAX_NUMERO):
            return None
        if formato not in formatos:
            return None
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (tamano, mtime)):
            return None
        archivos.append(ArchivoFirmado(a["id"], numero, formato, tamano, mtime))
    if len({a.id for a in archivos}) != len(archivos):
        return None
    return VinculacionFirmada(clave, d["serie_id"], d["operacion"], tuple(archivos), caduca)
