# ruff: noqa: E501
"""Cortesía con los sitios externos: un mínimo entre peticiones COMPARTIDO por todos los caminos del proceso.

El límite de cortesía de cada cliente de fuentes vivía en la INSTANCIA (`self._last_req`, a 0 al crearla) y cada
búsqueda de Descubrir o cada ciclo del enriquecedor crea clientes nuevos: dos búsquedas seguidas, o una búsqueda
mientras corre el enriquecedor, llegaban al sitio sin espera entre ellas. Aquí el estado vive **por sitio y por
proceso**, no por instancia.

Qué garantiza y qué NO:
- Entre el INICIO de dos peticiones al mismo sitio hay, como mínimo, `minimo` segundos, venga cada una de la
  instancia, del camino o de la tarea que sea; las concurrentes hacen cola (FIFO) y se escalonan.
- **Depende de que haya UN SOLO proceso.** La imagen arranca `uvicorn --workers 1` y el enriquecedor corre en
  ese mismo proceso (`main._enrichment_loop`), así que cubre todos los caminos que existen hoy. Con varios
  procesos o réplicas NO se coordinan (haría falta un estado compartido, p. ej. en PostgreSQL).
- Mide con `time.monotonic` (no se ve afectado por cambios de la hora del sistema).
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime


class LimitadorDeCortesia:
    """Espacia las peticiones a UN sitio. El reloj y la espera son inyectables para probarlo sin dormir."""

    def __init__(self, reloj: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._reloj = reloj
        self._dormir = dormir
        self._ultima: float | None = None          # inicio de la última petición autorizada
        self._candado: asyncio.Lock | None = None
        self._bucle: asyncio.AbstractEventLoop | None = None

    def _candado_del_bucle(self) -> asyncio.Lock:
        """Un `asyncio.Lock` queda ligado al bucle que lo usa: si el proceso cambia de bucle (las pruebas lo
        hacen en cada test), se crea otro en vez de fallar con «attached to a different loop»."""
        bucle = asyncio.get_running_loop()
        if self._candado is None or self._bucle is not bucle:
            self._candado, self._bucle = asyncio.Lock(), bucle
        return self._candado

    async def esperar(self, minimo: float) -> float:
        """Devuelve cuando ya se puede hacer la petición; cuántos segundos se esperó. La primera no espera.
        Una espera cancelada no marca la petición como hecha."""
        async with self._candado_del_bucle():
            espera = 0.0
            if self._ultima is not None:
                espera = max(0.0, self._ultima + minimo - self._reloj())
                if espera > 0:
                    await self._dormir(espera)
            self._ultima = self._reloj()
            return espera


_LIMITADORES: dict[str, LimitadorDeCortesia] = {}


def limitador_de(sitio: str) -> LimitadorDeCortesia:
    """El limitador compartido del sitio (uno por proceso)."""
    if sitio not in _LIMITADORES:
        _LIMITADORES[sitio] = LimitadorDeCortesia()
    return _LIMITADORES[sitio]


def reiniciar_para_pruebas() -> None:
    _LIMITADORES.clear()
    _reiniciar_limitador_compartido()


# ── Limitador de dos niveles, compartido por proceso (#134, MIT-M8-US02) ─────────────────────────
#
# Lo anterior (`LimitadorDeCortesia`/`limitador_de`) es el estado por sitio que usa Tebeosfera hoy y
# NO se toca aquí: Tebeosfera se migra en el corte 1b. Este bloque añade el contrato nuevo del
# limitador compartido: dos niveles (fuente y host efectivo), política declarativa por fuente,
# bloqueos por `Retry-After` visibles para todos, cancelación segura y snapshot de solo lectura.
# Sigue siendo estado EN MEMORIA de UN proceso (uvicorn --workers 1); no hay coordinación entre
# procesos ni instalaciones (ver docs/design/especificacion-cortesia-compartida.md §3).


logger = logging.getLogger(__name__)

#: Tope del bloqueo compartido que puede imponer un `Retry-After` (§5).
BLOQUEO_MAX_S = 3600.0
#: Presupuesto por defecto de un llamador que no dice el suyo (fondo, §3.7). Un caller nuevo no
#: puede dormir hasta una hora: sin presupuesto explícito se aplica este.
ESPERA_MAX_POR_DEFECTO_S = 30.0
#: Backoff local de un intento: 2 s ×2 (2, 4, 8…), con tope, sin jitter (§5).
BACKOFF_BASE_S = 2.0
FACTOR_BACKOFF = 2.0
TOPE_BACKOFF_S = 30.0

#: Mínimo de Tebeosfera: la configuración solo puede SUBIRLO (§3.1, y su propia spec).
MINIMO_TEBEOSFERA_S = 2.5

#: Nombre de cara a la persona de cada fuente (Estado/Ajustes lo reutilizan en PR-2).
NOMBRES_DE_FUENTE: dict[str, str] = {
    "comicvine": "Comic Vine",
    "anilist": "AniList",
    "tebeosfera": "Tebeosfera",
    "gcd": "GCD",
    "foro": "Foro",
    "portada": "Portadas",
}

#: Las fuentes que el snapshot lista SIEMPRE, aunque estén apagadas (§6.1).
FUENTES_DECLARADAS: tuple[str, ...] = ("comicvine", "anilist", "tebeosfera", "gcd", "foro", "portada")

#: Intervalo del nivel host para las portadas (su URL no lleva fuente; §3.1 y §14.2).
#: Se aplica por origen normalizado; los subdominios del CDN de Comic Vine heredan su intervalo.
INTERVALO_PORTADA_POR_HOST: tuple[tuple[str, float], ...] = (
    ("comicvine.gamespot.com", 1.0),
    ("cbsistatic.com", 1.0),
    ("anilist.co", 1.5),
    ("tebeosfera.com", 2.5),
    ("comics.org", 2.0),
)
INTERVALO_PORTADA_DESCONOCIDO_S = 2.5

#: Host de portada → fuente a la que pertenece (para la puerta de «fuente apagada» de AC-12).
HOST_DE_FUENTE_PARA_PORTADAS: tuple[tuple[str, str], ...] = (
    ("comicvine.gamespot.com", "comicvine"),
    ("cbsistatic.com", "comicvine"),
    ("anilist.co", "anilist"),
    ("tebeosfera.com", "tebeosfera"),
    ("comics.org", "gcd"),
)


def fuente_de_host_portada(host: str | None) -> str | None:
    """Fuente a la que pertenece una portada por su host, o None si no está en el mapa."""
    nombre = (host or "").strip().lower().split(":", 1)[0]
    for dominio, fuente in HOST_DE_FUENTE_PARA_PORTADAS:
        if nombre == dominio or nombre.endswith(f".{dominio}"):
            return fuente
    return None


class CortesiaEnEspera(Exception):  # noqa: N818 — nombre del contrato (§3.6)
    """La espera estimada no cabe en el presupuesto del llamador: NO se envía la petición.

    Lleva un código corto y seguro (§6.6): la fuente, el host efectivo, los segundos estimados y
    el motivo (`cortesia`, `reintento` o `bloqueo_fuente`). Nunca la URL ni la query."""

    def __init__(self, fuente: str, host: str, espera_estimada_s: float, motivo: str = "cortesia"):
        self.fuente = fuente
        self.host_efectivo = host
        self.espera_estimada_s = float(espera_estimada_s)
        self.motivo = motivo
        super().__init__(
            f"cortesía: {fuente} ({host}) necesita esperar ~{self.espera_estimada_s:.1f} s ({motivo})"
        )


class FuenteApagada(Exception):  # noqa: N818 — nombre del contrato (§3.6)
    """La fuente está apagada en Ajustes: no se reserva, no se envía y no se reintenta."""

    def __init__(self, fuente: str):
        self.fuente = fuente
        super().__init__(f"fuente apagada: {fuente}")


@dataclass(frozen=True)
class PoliticaFuente:
    """Política declarativa de una fuente (tabla §3.1). Pura: se construye con ajustes simulados."""

    fuente: str
    nombre: str
    intervalo_min_s: float
    max_intentos: int
    max_redirecciones: int
    obedece_retry_after: bool = True
    backoff_base_s: float = BACKOFF_BASE_S
    factor_backoff: float = FACTOR_BACKOFF
    tope_backoff_s: float = TOPE_BACKOFF_S
    bloqueo_max_s: float = BLOQUEO_MAX_S

    def backoff_s(self, intento: int) -> float:
        """Espera antes del intento `intento` (1 → 2 s, 2 → 4 s…), con tope y sin jitter."""
        return min(self.backoff_base_s * (self.factor_backoff ** max(0, intento - 1)),
                   self.tope_backoff_s)


def _ajustes(ajustes=None):
    if ajustes is not None:
        return ajustes
    from zascarr.config import get_settings

    return get_settings()


def intervalo_de_portada(host: str | None, ajustes=None) -> float:
    """Intervalo del nivel host para una portada: mapa allowlist→fuente; desconocido, 2,5 s."""
    nombre = (host or "").strip().lower().split(":", 1)[0]
    for dominio, intervalo in INTERVALO_PORTADA_POR_HOST:
        if nombre == dominio or nombre.endswith(f".{dominio}"):
            return max(0.0, float(intervalo))
    return INTERVALO_PORTADA_DESCONOCIDO_S


def politica_de(fuente: str, ajustes=None, *, host: str | None = None) -> PoliticaFuente:
    """Construye la política de §3.1. `ajustes` es cualquier objeto con los campos de `config.py`
    (las pruebas pasan uno simulado); nunca lanza por una fuente desconocida (política estricta)."""
    s = _ajustes(ajustes)
    nombre = NOMBRES_DE_FUENTE.get(fuente, fuente)
    if fuente == "comicvine":
        return PoliticaFuente(fuente, nombre, float(s.comicvine_rate_limit), 3, 3)
    if fuente == "anilist":
        return PoliticaFuente(fuente, nombre, float(s.anilist_rate_limit), 3, 3)
    if fuente == "tebeosfera":
        # Solo puede subir: una configuración menor se eleva con aviso (el comportamiento de su
        # cliente lo conserva en 1b; aquí la política ya lo deja fijado).
        intervalo = max(MINIMO_TEBEOSFERA_S, float(s.tebeosfera_rate_limit))
        return PoliticaFuente(fuente, nombre, intervalo, 1, 3)
    if fuente == "gcd":
        return PoliticaFuente(fuente, nombre, float(s.gcd_rate_limit), 2, 3)
    if fuente == "foro":
        return PoliticaFuente(fuente, nombre, float(s.forum_rate_limit), 2, 3)
    if fuente == "portada":
        return PoliticaFuente(fuente, nombre, intervalo_de_portada(host, s), 1, 3)
    return PoliticaFuente(fuente, nombre, 2.5, 1, 3)


def fuente_habilitada(fuente: str, ajustes=None) -> bool:
    """¿Está la fuente encendida en Ajustes? El foro, además, necesita URL (§6.1)."""
    s = _ajustes(ajustes)
    if fuente == "portada":
        return True
    if fuente == "foro":
        return bool(getattr(s, "forum_enabled", False) and getattr(s, "forum_url", ""))
    atributo = f"{fuente}_enabled"
    return bool(getattr(s, atributo, False))


@dataclass
class Espera:
    """Lo que se esperó (y por qué) en una petición autorizada. Nunca contiene la URL."""

    fuente: str
    host_efectivo: str
    espera_s: float = 0.0
    motivo: str = "cortesia"
    intentos_restantes: int = 0


@dataclass
class _EstadoCola:
    """Estado de una cola (fuente u host): cuándo se autorizó la última y hasta cuándo está bloqueada."""

    ultima: float | None = None
    bloqueada_hasta: float | None = None
    bloqueo_motivo: str | None = None
    esperando: int = 0


class _Candados:
    """Un `asyncio.Lock` queda atado a su bucle; estas pruebas usan uno por test. Se recrea si cambia."""

    def __init__(self) -> None:
        self._por_clave: dict[str, tuple[object, asyncio.Lock]] = {}

    def de(self, clave: str) -> asyncio.Lock:
        bucle = asyncio.get_running_loop()
        actual = self._por_clave.get(clave)
        if actual is None or actual[0] is not bucle:
            actual = (bucle, asyncio.Lock())
            self._por_clave[clave] = actual
        return actual[1]

    def limpiar(self) -> None:
        self._por_clave.clear()


def origen_normalizado(url: str) -> str:
    """Origen `(esquema, host, puerto)` normalizado: `https://x` y `http://x` son destinos distintos.

    Lanza `ValueError` si la URL no se puede partir (puerto no numérico, IPv6 roto…): quien la use
    para seguir un `Location` lo convierte en `location_invalida`, nunca en un reintento."""
    from urllib.parse import urlsplit

    try:
        partes = urlsplit(url)
        esquema = (partes.scheme or "").lower()
        host = (partes.hostname or "").lower()
        puerto = partes.port
    except ValueError as exc:
        raise ValueError("URL no válida") from exc
    if puerto is None:
        puerto = 443 if esquema == "https" else 80 if esquema == "http" else 0
    return f"{esquema}://{host}:{puerto}"


def host_efectivo(url: str) -> str:
    """El nombre del host de una URL (solo para mensajes; la cola usa el origen normalizado)."""
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "").lower()


def clave_de_host(valor: str) -> str:
    """Clave del nivel host: **origen normalizado `(esquema, host, puerto)`** (§3.2).

    `https://cdn.example` y `http://cdn.example` (o el mismo nombre en otro puerto) son destinos
    DISTINTOS y no comparten cola. Se acepta también una URL completa (se normaliza) y un nombre
    suelto (se deja tal cual: solo para pruebas o consumidores que ya traen su propia clave)."""
    limpio = (valor or "").strip().lower()
    if not limpio:
        return ""
    if "://" in limpio:
        return origen_normalizado(limpio)
    return limpio


class Turno:
    """Contexto asíncrono de una autorización (reserva en las dos colas). Ver `CortesiaProceso.reservar`."""

    def __init__(self, lim: CortesiaProceso, fuente: str, host: str, *, motivo: str,
                 espera_max_s: float | None, intentos_restantes: int = 0,
                 intervalo_s: float | None = None, solo_host: bool = False):
        self._lim = lim
        self.fuente = fuente
        self.host = host
        self._motivo = motivo
        self._intervalo_s = intervalo_s
        self._solo_host = solo_host
        self._espera_max_s = espera_max_s
        self._deadline = None if espera_max_s is None else lim._reloj() + max(0.0, espera_max_s)
        self._espera_s = 0.0
        self._motivo_visible = motivo
        self._autorizada_fuente = False
        self._autorizada = False
        self._liberado = False
        self.intentos_restantes = intentos_restantes

    async def __aenter__(self) -> Espera:
        lim = self._lim
        if not self._solo_host:
            estado_fuente = lim._estado_fuente(self.fuente)
            estado_fuente.esperando += 1
            try:
                await self._autorizar(estado_fuente, lim._intervalo_de_fuente(self.fuente))
                self._autorizada_fuente = True
            finally:
                estado_fuente.esperando -= 1
        estado_host = lim._estado_host(self.host)
        estado_host.esperando += 1
        try:
            await self._autorizar(estado_host, lim._intervalo_de_host(self.host))
            self._autorizada = True
        finally:
            estado_host.esperando -= 1
        return Espera(fuente=self.fuente, host_efectivo=self.host, espera_s=self._espera_s,
                      motivo=self._motivo_visible, intentos_restantes=self.intentos_restantes)

    async def __aexit__(self, *_exc) -> None:
        self.liberar()

    def liberar(self) -> None:
        """Idempotente. Antes de autorizar retira la reserva (no consume hueco); después no devuelve
        nada (conservador, §3.4). Con este diseño la marca solo se escribe al autorizar, así que
        aquí no hay nada que deshacer: los candados se sueltan en `_autorizar`."""
        self._liberado = True

    async def _autorizar(self, estado: _EstadoCola, intervalo: float) -> None:
        lim = self._lim
        if self._intervalo_s is not None:
            intervalo = max(0.0, float(self._intervalo_s))
        async with lim._candados.de(self._clave(estado)):
            espera, motivo = self._espera_necesaria(estado, intervalo)
            if espera > 0:
                if self._deadline is not None and lim._reloj() + espera > self._deadline:
                    # No se duerme ni se envía: espera visible (§3.4/§3.7).
                    raise CortesiaEnEspera(self.fuente, self.host, espera, motivo)
                await lim._dormir(espera)
                self._espera_s += espera
                self._motivo_visible = motivo
            estado.ultima = lim._reloj()

    def _espera_necesaria(self, estado: _EstadoCola, intervalo: float) -> tuple[float, str]:
        ahora = self._lim._reloj()
        espera = 0.0
        motivo = self._motivo
        if estado.ultima is not None:
            espera = max(0.0, estado.ultima + max(0.0, intervalo) - ahora)
        if estado.bloqueada_hasta is not None and estado.bloqueada_hasta > ahora:
            bloqueo = estado.bloqueada_hasta - ahora
            if bloqueo >= espera:
                espera, motivo = bloqueo, "bloqueo_fuente"
        return espera, motivo

    def _clave(self, estado: _EstadoCola) -> str:
        return f"{id(estado):x}"


class CortesiaProceso:
    """Limitador de dos niveles del proceso: una cola por fuente y otra por host efectivo.

    - Orden de adquisición SIEMPRE fuente → host (evita interbloqueos).
    - Los candados cubren la AUTORIZACIÓN, no la petición HTTP: no se mantiene ninguno durante la red.
    - La primera petición no espera; las concurrentes se escalonan en FIFO (el `Lock` de asyncio es FIFO).
    - Un `Retry-After` bloquea la fuente y el host para todos (estado en memoria).
    """

    def __init__(self, reloj: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._reloj = reloj
        self._dormir = dormir
        self._politicas: dict[str, PoliticaFuente] = {}
        self._fuentes: dict[str, _EstadoCola] = {}
        self._hosts: dict[str, _EstadoCola] = {}
        self._fuentes_por_host: dict[str, set[str]] = {}
        self._intentos: dict[str, deque] = {}
        self._candados = _Candados()

    # ── configuración ───────────────────────────────────────────────────────────────────────────
    def registrar_politica(self, politica: PoliticaFuente) -> None:
        self._politicas[politica.fuente] = politica

    def _politica(self, fuente: str) -> PoliticaFuente:
        politica = self._politicas.get(fuente)
        if politica is None:
            politica = politica_de(fuente)
            self._politicas[fuente] = politica
        return politica

    def _estado_fuente(self, fuente: str) -> _EstadoCola:
        return self._fuentes.setdefault(fuente, _EstadoCola())

    def _estado_host(self, host: str) -> _EstadoCola:
        return self._hosts.setdefault(host, _EstadoCola())

    def _intervalo_de_fuente(self, fuente: str) -> float:
        return max(0.0, self._politica(fuente).intervalo_min_s)

    def _intervalo_de_host(self, host: str) -> float:
        fuentes = self._fuentes_por_host.get(host) or set()
        if not fuentes:
            return 0.0
        return max(self._intervalo_de_fuente(f) for f in fuentes)

    # ── API ─────────────────────────────────────────────────────────────────────────────────────
    def reservar(self, fuente: str, host: str, *, motivo: str = "cortesia",
                 espera_max_s: float | None = ESPERA_MAX_POR_DEFECTO_S,
                 intervalo_s: float | None = None, solo_host: bool = False) -> Turno:
        """Registra la intención en las dos colas (sin dormir) y devuelve el contexto. El estado
        solo se marca al autorizar; una cancelación previa no consume hueco."""
        try:
            asyncio.get_running_loop()
        except RuntimeError as exc:  # un hilo no puede usar este limitador (§3.5, AC-13)
            raise RuntimeError(
                "El limitador de cortesía vive en el bucle de asyncio: no se puede usar desde un hilo."
            ) from exc
        host = clave_de_host(host)
        if not host:
            raise ValueError("el host efectivo no puede estar vacío")
        self._fuentes_por_host.setdefault(host, set()).add(fuente)
        self._politica(fuente)
        return Turno(self, fuente, host, motivo=motivo, espera_max_s=espera_max_s,
                     intervalo_s=intervalo_s, solo_host=solo_host)

    async def esperar(self, fuente: str, host: str, *, motivo: str = "cortesia",
                      espera_max_s: float | None = ESPERA_MAX_POR_DEFECTO_S,
                      intervalo_s: float | None = None, solo_host: bool = False) -> Espera:
        """Atajo: reserva, espera y libera. Devuelve la espera (cuánto y por qué).

        `solo_host=True` salta el nivel de FUENTE: es el caso de las portadas (§3.1), cuya política
        es por host y no por fuente; así dos hosts distintos no se bloquean entre sí."""
        async with self.reservar(fuente, host, motivo=motivo, espera_max_s=espera_max_s,
                                 intervalo_s=intervalo_s, solo_host=solo_host) as espera:
            return espera

    def liberar(self, turno: Turno) -> None:
        turno.liberar()

    def bloquear(self, fuente: str, host: str | None, segundos: float, motivo: str = "429",
                 *, maximo_s: float | None = None) -> None:
        """Comparte un `Retry-After` con todos: bloquea la fuente y el host (origen) indicado (§5)."""
        if not math.isfinite(segundos) or segundos <= 0:
            return
        host = clave_de_host(host) if host else None
        tope = BLOQUEO_MAX_S if maximo_s is None else min(BLOQUEO_MAX_S, max(0.0, maximo_s))
        if segundos > tope:
            logger.warning("cortesia: bloqueo de %s recortado a %s s", fuente, tope)
            segundos = tope
        if segundos <= 0:
            return
        hasta = self._reloj() + segundos
        for estado in (self._estado_fuente(fuente), *( (self._estado_host(host),) if host else () )):
            if estado.bloqueada_hasta is None or estado.bloqueada_hasta < hasta:
                estado.bloqueada_hasta = hasta
                estado.bloqueo_motivo = motivo

    def registrar_resultado(self, fuente: str, resultado: str, *, intento: int = 1,
                            espera_s: float = 0.0) -> None:
        """Anota un intento para el snapshot (máximo 3 por fuente, §6.1). No escribe nada."""
        cola = self._intentos.get(fuente)
        if cola is None:
            cola = deque(maxlen=3)
            self._intentos[fuente] = cola
        cola.append({
            "en": self._reloj(), "intento": int(intento),
            "resultado": resultado, "espera_s": round(float(espera_s), 1),
        })

    # ── snapshot ───────────────────────────────────────────────────────────────────────────────
    def snapshot(self, ajustes=None) -> dict:
        """Estado serializable (§6.1): solo fuentes, hosts, intervalos, contadores y bloqueos."""
        ahora = self._reloj()
        fuentes = []
        for nombre in FUENTES_DECLARADAS:
            politica = self._politicas.get(nombre) or politica_de(nombre, ajustes)
            estado = self._fuentes.get(nombre) or _EstadoCola()
            siguiente = 0.0
            if estado.ultima is not None:
                siguiente = max(siguiente, estado.ultima + politica.intervalo_min_s - ahora)
            if estado.bloqueada_hasta is not None and estado.bloqueada_hasta > ahora:
                siguiente = max(siguiente, estado.bloqueada_hasta - ahora)
            fuentes.append({
                "fuente": nombre,
                "nombre": politica.nombre,
                "habilitada": fuente_habilitada(nombre, ajustes),
                "intervalo_min_s": round(politica.intervalo_min_s, 2),
                "max_intentos": politica.max_intentos,
                "max_redirecciones": politica.max_redirecciones,
                "esperando_ahora": estado.esperando,
                "siguiente_hueco_s": round(max(0.0, siguiente), 1),
                "bloqueada_hasta_s": (
                    round(estado.bloqueada_hasta - ahora, 1)
                    if estado.bloqueada_hasta is not None and estado.bloqueada_hasta > ahora else None
                ),
                "bloqueo_motivo": (
                    estado.bloqueo_motivo
                    if estado.bloqueada_hasta is not None and estado.bloqueada_hasta > ahora else None
                ),
                "ultimos_intentos": [
                    {"hace_s": round(ahora - intento["en"], 1), "intento": intento["intento"],
                     "resultado": intento["resultado"], "espera_s": intento["espera_s"]}
                    for intento in reversed(self._intentos.get(nombre, ()))
                ],
            })
        hosts = []
        for host, estado in self._hosts.items():
            fuentes_del_host = sorted(self._fuentes_por_host.get(host) or ())
            intervalo = self._intervalo_de_host(host)
            siguiente = 0.0
            if estado.ultima is not None:
                siguiente = max(siguiente, estado.ultima + intervalo - ahora)
            if estado.bloqueada_hasta is not None and estado.bloqueada_hasta > ahora:
                siguiente = max(siguiente, estado.bloqueada_hasta - ahora)
            hosts.append({
                "host": host,
                "fuentes": fuentes_del_host,
                "intervalo_min_s": round(intervalo, 2),
                "esperando_ahora": estado.esperando,
                "siguiente_hueco_s": round(max(0.0, siguiente), 1),
                "bloqueada_hasta_s": (
                    round(estado.bloqueada_hasta - ahora, 1)
                    if estado.bloqueada_hasta is not None and estado.bloqueada_hasta > ahora else None
                ),
            })
        return {
            "coordinacion": "proceso",
            "generado": datetime.now(UTC).isoformat(),
            "fuentes": fuentes,
            "hosts": hosts,
        }

    def reiniciar(self) -> None:
        self._fuentes.clear()
        self._hosts.clear()
        self._fuentes_por_host.clear()
        self._intentos.clear()
        self._candados.limpiar()


_CORTESIA_DE_PROCESO: CortesiaProceso | None = None


def cortesia_de_proceso() -> CortesiaProceso:
    """El limitador compartido del proceso (uno; creado al primer uso)."""
    global _CORTESIA_DE_PROCESO
    if _CORTESIA_DE_PROCESO is None:
        _CORTESIA_DE_PROCESO = CortesiaProceso()
    return _CORTESIA_DE_PROCESO


def _reiniciar_limitador_compartido() -> None:
    global _CORTESIA_DE_PROCESO
    if _CORTESIA_DE_PROCESO is not None:
        _CORTESIA_DE_PROCESO.reiniciar()
    _CORTESIA_DE_PROCESO = None
