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
from zascarr.utils.url_portada import LONGITUD_MAXIMA_URL

TTL_SEGUNDOS = 15 * 60
PROPOSITO_CANDIDATA = "candidata"
PROPOSITO_ALTA = "alta"
PROPOSITO_VINCULAR = "vincular"
#: La descripción que viaja en el token se recorta: no hace falta entera para dar de alta una serie.
MAX_DESCRIPCION = 1000

#: Cotas de los textos que viajan en los tokens de candidata y alta. No son arbitrarias: son lo que el alta puede
#: GUARDAR (`Series.title` y `Series.cover_url` son `String(500)`, `tebeosfera_slug` es `String(255)` y el año va en
#: una `SmallInteger`) y lo que la política de portadas ya admite (`LONGITUD_MAXIMA_URL`). Sin ellas el tamaño de un
#: token no tendría máximo: lo fijaría lo que devuelva una fuente externa.
MAX_TITULO = 500
MAX_ID_EXTERNO = 255
MAX_COVER_URL = LONGITUD_MAXIMA_URL
ANIO_MIN_FIRMABLE, ANIO_MAX_FIRMABLE = -32768, 32767
#: A cuántas series «parecidas» puede referirse un alta que CREA (van firmadas en `vistas`). Por encima de esto no
#: se emite token: ver `DemasiadasParecidasError`.
MAX_PARECIDAS_FIRMADAS = 100

_CONTROLES_PERMITIDOS = "\t\n\r"


def texto_firmable(texto: str) -> bool:
    """¿Se puede firmar este texto sin sorpresas? Dos clases de carácter no: los sustitutos sueltos de Unicode
    (`"\\ud800"` no se codifica en UTF-8: `crear_token` lanzaría `UnicodeEncodeError`) y los controles salvo
    tabulador y saltos de línea (Postgres no admite el NUL en un `text`, y JSON escribe cada control como seis
    bytes, lo que rompería la cota de tamaño de más abajo)."""
    for ch in texto:
        o = ord(ch)
        if 0xD800 <= o <= 0xDFFF or (o < 0x20 and ch not in _CONTROLES_PERMITIDOS):
            return False
    return True


def _depurar(texto: str) -> str:
    """El mismo texto con cada carácter no firmable sustituido por un espacio."""
    return "".join(ch if texto_firmable(ch) else " " for ch in texto)


def _textos_acotados(titulo: str, id_externo: str, descripcion: str | None, cover: str | None) -> bool:
    return (len(titulo) <= MAX_TITULO and len(id_externo) <= MAX_ID_EXTERNO
            and texto_firmable(titulo) and texto_firmable(id_externo)
            and (descripcion is None or (len(descripcion) <= MAX_DESCRIPCION and texto_firmable(descripcion)))
            and (cover is None or (len(cover) <= MAX_COVER_URL and texto_firmable(cover))))


def _anio_firmable(anio: object) -> bool:
    return anio is None or (isinstance(anio, int) and not isinstance(anio, bool)
                            and ANIO_MIN_FIRMABLE <= anio <= ANIO_MAX_FIRMABLE)


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
               ahora: float | None = None, ignorar_caducidad: bool = False) -> tuple[dict, int] | None:
    """(datos, caducidad) de un token válido, o `None`. Nunca lanza con un token ausente o malformado.
    `ignorar_caducidad` solo sirve para LEER la operación de un token ya caducado (reproducir un informe
    guardado); la firma, el propósito y el contexto se comprueban igual."""
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
    if not isinstance(caduca, int) or isinstance(caduca, bool) or (caduca < ahora_ and not ignorar_caducidad):
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


def candidata_firmable(fuente: str, id_externo: object, titulo: str | None, anio: int | None, tradicion: str,
                       descripcion: str | None, cover_url: str | None) -> CandidataFirmada | None:
    """La candidata TAL COMO se firmará, o `None` si no se puede dar de alta (su título o su identificador no caben
    en lo que la base guarda, o llevan caracteres no firmables). El resto se ajusta sin descartar: el título pierde
    controles y espacios sobrantes (el alta hace lo mismo), la descripción se depura y se recorta, la portada se
    omite si no cabe o no es firmable y un año fuera de la `SmallInteger` se ignora. Es lo que hace que el tamaño de
    un token tenga máximo (`MAX_TOKEN_CANDIDATA`), por mucho que devuelva una fuente."""
    ident = str(id_externo)
    if not ident.strip() or len(ident) > MAX_ID_EXTERNO or not texto_firmable(ident):
        return None
    limpio = " ".join(_depurar(titulo or "").split())
    if not limpio or len(limpio) > MAX_TITULO:
        return None
    desc = _depurar(descripcion or "")[:MAX_DESCRIPCION]
    desc = desc if desc.strip() else None
    cover = cover_url if cover_url and len(cover_url) <= MAX_COVER_URL and texto_firmable(cover_url) else None
    return CandidataFirmada(fuente, ident, limpio, anio if _anio_firmable(anio) else None, tradicion, desc, cover)


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
    # Las cotas de `MAX_TOKEN_CANDIDATA`: un token firmado por el servidor ya las cumple; se exigen igualmente.
    if not _anio_firmable(anio) or not _textos_acotados(titulo, id_externo, descripcion, cover):
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
    if clave is None or len(clave) > MAX_CLAVE_GRUPO:
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
    # Las cotas de `MAX_TOKEN_ALTA`. `fuente` e `id` solo existen con origen `descubrir`, y entonces son cadenas.
    if len(vistas) > MAX_PARECIDAS_FIRMADAS or not _anio_firmable(anio):
        return None
    if not _textos_acotados(titulo, id_externo or "", descripcion, cover):
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
    #: Códigos de las señales de severidad «conflicto» que la persona VIO al marcar este archivo. `()` = ninguno.
    conflictos: tuple[str, ...] = ()


@dataclass(frozen=True)
class VinculacionFirmada:
    """La operación aprobada: serie, los archivos marcados Y ejecutables con su número y edición. El contexto del
    token es la `clave` del grupo; la `series_id` va firmada dentro (las dos son inseparables del token)."""
    clave: str
    series_id: str
    operacion: str
    archivos: tuple[ArchivoFirmado, ...]
    caduca: int = 0


#: Versión del esquema del token de vinculación. La 2 añade `conflictos` OBLIGATORIO por archivo: la ausencia del
#: campo no significa «ninguno», así que los tokens anteriores (2c) se rechazan y exigen una vista previa nueva.
VERSION_TOKEN_VINCULAR = 2
MAX_CONFLICTOS = 20
MAX_CODIGO = 60


def clave_de_numero(numero: str) -> str:
    """UNA sola equivalencia de números en toda la operación (duplicados del token, claves y orden de candados,
    búsqueda de `Issue` y ocupación): sin distinguir mayúsculas. El texto presentado no cambia."""
    return numero.strip().lower()


def crear_token_vinculacion(v: VinculacionFirmada, secret: str, *, ahora: float | None = None) -> str:
    return crear_token(PROPOSITO_VINCULAR, v.clave, {
        "version": VERSION_TOKEN_VINCULAR, "serie_id": v.series_id, "operacion": v.operacion,
        "archivos": [{"id": a.id, "numero": a.numero, "formato": a.formato, "tamano": a.tamano,
                      "mtime_ns": a.mtime_ns, "conflictos": sorted(a.conflictos)}
                     for a in sorted(v.archivos, key=lambda a: a.id)],
    }, secret, ahora=ahora)


def verificar_token_vinculacion(token: str, secret: str, *, ahora: float | None = None,
                                ignorar_caducidad: bool = False) -> VinculacionFirmada | None:
    """La vinculación firmada, o `None`. Firma, propósito y caducidad como siempre; además el ESQUEMA (UUID
    canónicos, formatos de la enumeración, números no vacíos, enteros no booleanos, sin ids repetidos y a lo sumo
    `MAX_ARCHIVOS_FIRMADOS`; sin números repetidos, sin distinguir mayúsculas; `version` 2 y `conflictos` explícitos
    por archivo). El contexto (la `clave`) se lee del propio token: la confirmación recibe solo el token."""
    clave = _contexto_del_token(token, secret)
    if clave is None:
        return None
    verificado = _verificar(token, PROPOSITO_VINCULAR, clave, secret, ahora=ahora, ignorar_caducidad=ignorar_caducidad)
    if verificado is None:
        return None
    d, caduca = verificado
    version = d.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != VERSION_TOKEN_VINCULAR:
        return None
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
        conflictos = a.get("conflictos")
        if (not isinstance(conflictos, list) or len(conflictos) > MAX_CONFLICTOS
                or not all(isinstance(c, str) and c.strip() and c == c.strip() and len(c) <= MAX_CODIGO
                           for c in conflictos) or len(set(conflictos)) != len(conflictos)):
            return None
        archivos.append(ArchivoFirmado(a["id"], numero, formato, tamano, mtime, tuple(conflictos)))
    if len({a.id for a in archivos}) != len(archivos):
        return None
    if len({clave_de_numero(a.numero) for a in archivos}) != len(archivos):      # dos archivos, un mismo número
        return None
    return VinculacionFirmada(clave, d["serie_id"], d["operacion"], tuple(archivos), caduca)


# ── Tamaño máximo del token de vinculación ───────────────────────────────────────────────────────

#: Longitud máxima de la `clave` de un grupo que acepta la vista previa (`max_length` de su petición).
MAX_CLAVE_GRUPO = 1000
#: Los códigos que la vista previa PUEDE firmar como conflicto (los de `RevisionCarpetas._senales`). Una prueba
#: comprueba que coinciden con los del código fuente: si se añade uno nuevo, el límite se recalcula solo.
CODIGOS_DE_SENAL = (
    "anio_discrepa", "calificador_de_carpeta", "candidatas_distintas", "titulo_distinto",
    "titulo_exacto_sin_corroboracion", "carpeta_de_autor_o_contenedor", "coincide_y_corrobora",
    "sin_contexto_de_carpeta",
)


#: Instante usado al calcular el peor caso: una época de 11 dígitos (hasta el año 2286 bastan 10): la caducidad del
#: token (`exp`) no puede hacerlo más largo.
EPOCA_DEL_PEOR_CASO = 10**10


def _longitud_peor_caso_del_token_de_vinculacion() -> int:
    """La longitud del MAYOR token que la vista previa puede emitir (calculada, no elegida): 100 archivos, cada uno
    con número de 20 caracteres, la edición de nombre más largo, tamaño y mtime de 63 bits y TODOS los códigos de
    señal como conflicto, en un grupo cuya `clave` tiene 1000 caracteres de 4 bytes en UTF-8. El mismo cálculo se
    repite en las pruebas con un token emitido de verdad."""
    ident = "00000000-0000-4000-8000-000000000000"
    formato = max((f.value for f in IssueFormat), key=len)
    grande = 2**63 - 1
    archivos = tuple(
        ArchivoFirmado(f"{i:08d}-0000-4000-8000-000000000000", "9" * MAX_NUMERO, formato, grande, grande, CODIGOS_DE_SENAL)
        for i in range(MAX_ARCHIVOS_FIRMADOS))
    token = crear_token_vinculacion(
        VinculacionFirmada("\U0001F600" * MAX_CLAVE_GRUPO, ident, ident, archivos), "x" * 32,
        ahora=EPOCA_DEL_PEOR_CASO)
    return len(token)


#: El límite del cuerpo de `POST /api/revision/vinculacion`: acotado, y IGUAL al peor caso emitible.
MAX_TOKEN_VINCULACION = _longitud_peor_caso_del_token_de_vinculacion()


# ── Tamaño máximo de los tokens de candidata y alta ──────────────────────────────────────────────

#: El carácter que más pesa en el JSON del token **dentro de la `clave` del grupo**. La clave es la ruta de la carpeta
#: tal como está en `files.file_path` (`"/".join` de los nombres de carpeta, sin tocar: identifica al grupo y debe
#: conservar su significado), y un nombre de carpeta de Linux puede llevar cualquier byte salvo `/` y NUL, es decir,
#: controles. `json.dumps(..., ensure_ascii=False)` escribe los controles como `\u00XX`: **seis bytes**, más que los
#: cuatro de cualquier carácter UTF-8 (una prueba lo comprueba sobre todos los puntos de código). Los demás textos del
#: token pasan por `texto_firmable` y no pueden llevar esos controles. El NUL no puede estar: Postgres no lo guarda.
CARACTER_MAS_PESADO_DE_UNA_CLAVE = "\x01"


def _longitud_peor_caso_del_token_de_candidata() -> int:
    """La longitud del MAYOR token de candidata que el servidor puede emitir y el verificador acepta (calculada, no
    elegida): cada texto en su cota y de caracteres de 4 bytes en UTF-8 (el máximo de cualquier texto firmable: el
    JSON se escribe con `ensure_ascii=False`, así que cada carácter pesa lo que su UTF-8; las comillas, las barras y
    los saltos de línea pesan dos), año de seis caracteres (`-32768`), la tradición más larga, una de las fuentes que
    el servidor emite (`CAMPO_ID_EXTERNO`: son las únicas que el alta puede procesar) y una `clave` de grupo de 1000
    controles de seis bytes. Sale de `crear_token_candidata`, es decir, de la serialización, la codificación y la
    firma reales."""
    ch = "\U0001F600"
    fuente = max((m.value for m in CAMPO_ID_EXTERNO), key=len)
    tradicion = max((t.value for t in ComicTradition), key=len)
    c = CandidataFirmada(fuente, ch * MAX_ID_EXTERNO, ch * MAX_TITULO, ANIO_MIN_FIRMABLE, tradicion,
                         ch * MAX_DESCRIPCION, ch * MAX_COVER_URL)
    return len(crear_token_candidata(CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO, c, "x" * 32,
                                     ahora=EPOCA_DEL_PEOR_CASO))


def _longitud_peor_caso_del_token_de_alta() -> int:
    """Idem para el alta. El mayor es el que CREA y firma `MAX_PARECIDAS_FIRMADAS` series vistas; el que reutiliza
    lleva `serie_id` y `criterio` pero ninguna vista. Se calculan los dos y se toma el mayor."""
    ch = "\U0001F600"
    ident = "00000000-0000-4000-8000-000000000000"
    fuente = max((m.value for m in CAMPO_ID_EXTERNO), key=len)
    tradicion = max((t.value for t in ComicTradition), key=len)
    comunes = dict(clave=CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO, origen="descubrir", fuente=fuente,
                   id_externo=ch * MAX_ID_EXTERNO, titulo=ch * MAX_TITULO, anio=ANIO_MIN_FIRMABLE, tradicion=tradicion,
                   descripcion=ch * MAX_DESCRIPCION, cover_url=ch * MAX_COVER_URL, operacion=ident)
    vistas = tuple(f"{i:08d}-0000-4000-8000-000000000000" for i in range(MAX_PARECIDAS_FIRMADAS))
    crea = AltaFirmada(modo="crear", serie_id=None, vistas=vistas, **comunes)
    reutiliza = AltaFirmada(modo="reutilizar", criterio="identificador", serie_id=ident, vistas=(), **comunes)
    return max(len(crear_token_alta(a, "x" * 32, ahora=EPOCA_DEL_PEOR_CASO)) for a in (crea, reutiliza))


#: Los límites del cuerpo de `POST /api/revision/serie/previsualizar` (campo `candidata`) y de `POST
#: /api/revision/serie` (campo `token`): acotados e IGUALES al peor caso emitible, no un número redondo.
MAX_TOKEN_CANDIDATA = _longitud_peor_caso_del_token_de_candidata()
MAX_TOKEN_ALTA = _longitud_peor_caso_del_token_de_alta()
