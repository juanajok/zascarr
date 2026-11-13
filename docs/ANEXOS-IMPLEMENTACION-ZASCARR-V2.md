# Anexos de Implementación (v2): Código de Referencia, Spike de Fase 0, ADR y Gobernanza Legal

> Documento complementario a `estudio-scraping-fuentes-v2.md` para ejecución asistida por LLM en el repositorio `juanajok/zascarr`.

---

## Anexo A: Prompt de Arranque para pasar al Agente LLM (Claude Code / Codex / Cursor)

Copia y pega este bloque como instrucción inicial al agente dentro del repositorio:

```text
Lee primero `CLAUDE.md`, `LEGAL.md`, `pyproject.toml`, `src/zascarr/utils/cortesia.py`,
`src/zascarr/utils/peticiones.py`, `src/zascarr/services/forum_scraper.py`,
`src/zascarr/services/tebeosfera.py`, `src/zascarr/services/enricher.py`,
`src/zascarr/services/legal.py` y `src/zascarr/config.py`.

A continuación lee íntegros `docs/estudio-scraping-fuentes-v2.md` y
`docs/ANEXOS-IMPLEMENTACION-ZASCARR-V2.md`.

Tu objetivo actual es ejecutar EXCLUSIVAMENTE la Fase 0 (inspección de firmas reales del
repositorio, propuesta de ajuste exacto de tipos/argumentos si difieren del documento,
ejecución o preparación del spike puntual de verificación y borrador del ADR), deteniéndote
para confirmar conmigo las decisiones abiertas del apartado 8 antes de generar migraciones
Alembic de Fase 1. Respeta estrictamente la prohibición de añadir dependencias distintas de
`protego` y la regla de usar `.xpath()` nativo de `lxml`.
```

---

## Anexo B: Script Ejecutable de Fase 0 (`scripts/spike_fase0_fuentes.py`)

Script autónomo y puntual (1 sola petición por comprobación, con pausa de cortesía) para cerrar las incógnitas reales de WAFs, *challenges* en páginas interiores y respuestas de MediaWiki antes de escribir adaptadores.

```python
"""Spike manual de Fase 0 — Verificación puntual de contenido real con httpx.

Uso manual desde el entorno del proyecto (NO ejecutar en CI):
    python scripts/spike_fase0_fuentes.py
"""
import asyncio
import httpx

USER_AGENT = "ZascArr/1.15.1 (+https://github.com/juanajok/zascarr; verificacion puntual Fase 0)"

CHECKS = [
    # 1. Fandom API: artículo real con posible redirección
    (
        "Fandom DC (parse + redirects)",
        "https://dc.fandom.com/api.php",
        {
            "action": "parse",
            "page": "Batman_Vol_1_404",
            "redirects": "1",
            "prop": "properties|images|displaytitle",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        },
    ),
    # 2. Fandom API: artículo inexistente (confirmar HTTP 200 + error.code == 'missingtitle')
    (
        "Fandom DC (missingtitle sobre HTTP 200)",
        "https://dc.fandom.com/api.php",
        {
            "action": "parse",
            "page": "Zascarr_Articulo_Inexistente_999999",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        },
    ),
    # 3. Reading Orders: comprobar que una guía interior no recibe 403 JS Challenge de Cloudflare
    (
        "Comic Book Reading Orders (sitemap)",
        "https://comicbookreadingorders.com/sitemap_index.xml",
        None,
    ),
    (
        "Comic Book Reading Orders (guía interior)",
        "https://comicbookreadingorders.com/dc/events/crisis-on-infinite-earths-reading-order/",
        None,
    ),
    # 4. Continuity Guide: comprobar página interior HTML normal (SIN ?format=json)
    (
        "Continuity Guide (página interior)",
        "https://www.continuityguide.net/planet-x",
        None,
    ),
    # 5. Comic Book Herald: comprobar si /feed/ también está bloqueado por WAF (403)
    (
        "Comic Book Herald (RSS /feed/)",
        "https://www.comicbookherald.com/feed/",
        None,
    ),
]


async def main() -> None:
    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        for nombre, url, params in CHECKS:
            try:
                r = await client.get(url, params=params)
                ct = r.headers.get("content-type", "-")
                etag = r.headers.get("etag", "-")
                lm = r.headers.get("last-modified", "-")
                extra = ""
                if "application/json" in ct:
                    payload = r.json()
                    if "error" in payload:
                        extra = f" | mw_error={payload['error'].get('code')}"
                    elif "parse" in payload:
                        extra = f" | title={payload['parse'].get('displaytitle')}"
                print(
                    f"[{r.status_code}] {nombre}\n"
                    f"      CT={ct} | bytes={len(r.content)} | ETag={etag} | LM={lm}{extra}"
                )
            except httpx.HTTPError as exc:
                print(f"[ERR] {nombre}: {type(exc).__name__}")
            await asyncio.sleep(2.5)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Anexo C: Implementaciones Base de Infraestructura (Fase 1)

> **Nota para el LLM:** Adapta los nombres de argumentos al contrato exacto de `pedir_con_cortesia`, `PoliticaFuente`, `CortesiaProceso` y la sesión SQLAlchemy `AsyncSession` del proyecto.

### C.1 `src/zascarr/utils/robots.py` — Evaluación RFC 9309 estricta

```python
"""Evaluador de robots.txt conforme a RFC 9309 usando protego."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse
import weakref

import httpx
from protego import Protego

EstadoRobots = Literal["parsed", "unavailable_allow", "unreachable_disallow"]


@dataclass(slots=True, frozen=True)
class EntradaRobots:
    estado: EstadoRobots
    parser: Protego | None
    expira_monotonic: float


class GestorRobots:
    """Cachea en memoria las reglas robots.txt por origen (scheme://netloc)."""

    TTL_OK_S = 86400.0            # 24 h cuando responde 200 OK
    TTL_UNAVAILABLE_S = 43200.0   # 12 h cuando responde 403/404 (RFC 9309 §2.3.1.3)
    TTL_UNREACHABLE_S = 900.0     # 15 min bloqueo preventivo en 429/5xx/red (RFC 9309 §2.3.1.4)

    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._cache: dict[str, EntradaRobots] = {}
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def _lock_para(self, origen: str) -> asyncio.Lock:
        lock = self._locks.get(origen)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[origen] = lock
        return lock

    async def evaluar(
        self,
        url: str,
        *,
        descargar_robots_fn,
    ) -> tuple[bool, float | None]:
        """Devuelve (permitido, crawl_delay_segundos).

        `descargar_robots_fn(robots_url)` debe ejecutar el GET pasando por la cortesía del proyecto.
        """
        parsed = urlparse(url)
        origen = f"{parsed.scheme}://{parsed.netloc}"
        ahora = time.monotonic()

        entrada = self._cache.get(origen)
        if entrada is None or ahora >= entrada.expira_monotonic:
            lock = self._lock_para(origen)
            async with lock:
                entrada = self._cache.get(origen)
                if entrada is None or time.monotonic() >= entrada.expira_monotonic:
                    entrada = await self._cargar_origen(origen, descargar_robots_fn)
                    self._cache[origen] = entrada

        if entrada.estado == "unreachable_disallow":
            return False, None
        if entrada.estado == "unavailable_allow" or entrada.parser is None:
            return True, None

        permitido = entrada.parser.can_fetch(url, self.user_agent)
        delay = entrada.parser.crawl_delay(self.user_agent)
        return permitido, (float(delay) if delay is not None else None)

    async def _cargar_origen(self, origen: str, descargar_robots_fn) -> EntradaRobots:
        robots_url = f"{origen}/robots.txt"
        ahora = time.monotonic()
        try:
            resp: httpx.Response = await descargar_robots_fn(robots_url)
        except Exception:
            # Fallo de red / timeout -> RFC 9309 §2.3.1.4: asumir Disallow temporal
            return EntradaRobots("unreachable_disallow", None, ahora + self.TTL_UNREACHABLE_S)

        code = resp.status_code
        if 200 <= code < 300:
            texto = resp.text[:512_000]  # RFC 9309 exige al menos 500 KiB
            return EntradaRobots("parsed", Protego.parse(texto), ahora + self.TTL_OK_S)

        if code == 429 or code >= 500:
            return EntradaRobots("unreachable_disallow", None, ahora + self.TTL_UNREACHABLE_S)

        if 400 <= code < 500:
            # 403 (Fandom WAF) / 404 (CRG) -> RFC 9309 §2.3.1.3 unavailable = permitido
            return EntradaRobots("unavailable_allow", None, ahora + self.TTL_UNAVAILABLE_S)

        return EntradaRobots("unreachable_disallow", None, ahora + self.TTL_UNREACHABLE_S)
```

---

### C.2 `src/zascarr/utils/cache_http.py` — Utilidades de Normalización, Compresión y *Singleflight*

Usa `weakref.WeakValueDictionary` para los locks en vuelo de modo que **nunca crezca la huella de RAM** en el contenedor de 512 MB aunque pasen miles de URLs a lo largo de semanas:

```python
"""Primitivas de caché HTTP condicional en PostgreSQL con protección de RAM."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import weakref
import zlib

MAX_CACHEABLE_BODY_BYTES = 2 * 1024 * 1024  # 2 MiB descomprimido
ZLIB_LEVEL = 6

_INFLIGHT_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def lock_singleflight(url_hash: str) -> asyncio.Lock:
    """Devuelve un Lock compartido mientras haya corrutinas compitiendo por el mismo hash."""
    lock = _INFLIGHT_LOCKS.get(url_hash)
    if lock is None:
        lock = asyncio.Lock()
        _INFLIGHT_LOCKS[url_hash] = lock
    return lock


def normalizar_y_hashear_url(metodo: str, url: str, params: dict | None = None) -> tuple[str, str, str]:
    """Devuelve (url_hash, url_canonica_sin_credenciales, domain).

    Elimina cualquier userinfo (usuario:password@) y ordena query params para maximizar hits.
    """
    p = urlparse(url)
    host_limpio = p.hostname or ""
    if p.port and not ((p.scheme == "http" and p.port == 80) or (p.scheme == "https" and p.port == 443)):
        netloc_limpio = f"{host_limpio}:{p.port}"
    else:
        netloc_limpio = host_limpio

    ares = list(parse_qsl(p.query, keep_blank_values=True))
    if params:
        for k, v in params.items():
            if v is not None:
                ares.append((str(k), str(v)))
    ares.sort(key=lambda kv: (kv[0], kv[1]))
    query_ordenada = urlencode(ares, doseq=True)

    url_canonica = urlunparse((p.scheme.lower(), netloc_limpio.lower(), p.path or "/", "", query_ordenada, ""))
    material = f"{metodo.upper()} {url_canonica}".encode("utf-8")
    return hashlib.sha256(material).hexdigest(), url_canonica, host_limpio.lower()


def comprimir_cuerpo(raw: bytes) -> bytes | None:
    """Comprime si no supera el techo de 2 MiB; devuelve None si excede el límite."""
    if len(raw) > MAX_CACHEABLE_BODY_BYTES:
        return None
    return zlib.compress(raw, level=ZLIB_LEVEL)


def descomprimir_cuerpo(comprimido: bytes) -> bytes:
    return zlib.decompress(comprimido)


@dataclass(slots=True, frozen=True)
class PoliticaCacheDominio:
    ttl_positivo: timedelta
    margen_retencion_304: timedelta
    ttl_negativo: timedelta

    def calcular_ventanas(self, ahora: datetime, *, es_negativo: bool) -> tuple[datetime, datetime]:
        if es_negativo:
            fin = ahora + self.ttl_negativo
            return fin, fin  # Las entradas negativas no usan revalidación 304
        fresh = ahora + self.ttl_positivo
        retain = fresh + self.margen_retencion_304
        return fresh, retain
```

---

## Anexo D: Motor Puro de Normalización de Guías (`services/reading_order_resolver.py`)

Resuelve las variantes habituales de notación estadounidense en guías de lectura sin tocar red ni BD:

```python
"""Normalizador puro de referencias textuales de cómics en órdenes de lectura."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

TipoEntrega = Literal["issue", "annual", "special", "tpb"]

# Normaliza guiones tipográficos (en-dash, em-dash, minus) a guion ASCII
_RE_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
# Elimina sufijos de miniserie como "(of 12)" o "(1 of 4)" al final
_RE_MINISERIES_SUFFIX = re.compile(r"\s*\((?:\d+\s+)?of\s+\d+\)\s*$", re.IGNORECASE)
# Extrae año entre paréntesis p.ej. "(1963)" o "(2016-)"
_RE_YEAR = re.compile(r"\((19\d{2}|20\d{2})(?:\s*[-–]\s*(?:19\d{2}|20\d{2})?)?\)")
# Extrae volumen explícito p.ej. "Vol. 2" o "Volume 3"
_RE_VOL = re.compile(r"\bVol(?:ume|\.)?\s*(\d+)\b", re.IGNORECASE)
# Extrae número o rango tras '#' (soporta #1, #1-6, #0.1, #1/2, #12.NOW, #1A)
_RE_ISSUE_RANGE = re.compile(
    r"#\s*(\d+(?:\.\w+|/\d+)?|[½])\s*(?:-\s*#?\s*(\d+(?:\.\w+|/\d+)?))?\b",
    re.IGNORECASE,
)
_RE_ANNUAL = re.compile(r"\bAnnual\b", re.IGNORECASE)
_RE_SPECIAL = re.compile(r"\b(?:Special|Giant-Size|One-Shot|80-Page Giant)\b", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class ReferenciaComicNormalizada:
    titulo_serie: str
    anio_inicio: int | None
    volumen: int | None
    numero_inicio: str
    numero_fin: str | None
    tipo: TipoEntrega


def parsear_referencia_guia(texto_crudo: str) -> ReferenciaComicNormalizada | None:
    """Convierte una línea como 'Uncanny X-Men (1963) #141–142' en estructura tipada.

    Devuelve None si la línea es un encabezado, nota editorial o texto sin numeración reconocible.
    """
    if not texto_crudo or not texto_crudo.strip():
        return None

    limpio = _RE_DASHES.sub("-", texto_crudo.strip())
    limpio = _RE_MINISERIES_SUFFIX.sub("", limpio)

    m_issue = _RE_ISSUE_RANGE.search(limpio)
    if not m_issue:
        return None

    num_ini = "0.5" if m_issue.group(1) == "½" else m_issue.group(1)
    num_fin = m_issue.group(2)

    prefijo = limpio[: m_issue.start()].strip(" -:,")
    if not prefijo:
        return None

    anio: int | None = None
    m_year = _RE_YEAR.search(prefijo)
    if m_year:
        anio = int(m_year.group(1))
        prefijo = (prefijo[: m_year.start()] + " " + prefijo[m_year.end() :]).strip()

    volumen: int | None = None
    m_vol = _RE_VOL.search(prefijo)
    if m_vol:
        volumen = int(m_vol.group(1))
        prefijo = (prefijo[: m_vol.start()] + " " + prefijo[m_vol.end() :]).strip()

    tipo: TipoEntrega = "issue"
    if _RE_ANNUAL.search(prefijo):
        tipo = "annual"
        prefijo = _RE_ANNUAL.sub("", prefijo).strip()
    elif _RE_SPECIAL.search(prefijo):
        tipo = "special"

    titulo = re.sub(r"\s{2,}", " ", prefijo).strip(" -:,()")
    if not titulo:
        return None

    return ReferenciaComicNormalizada(
        titulo_serie=titulo,
        anio_inicio=anio,
        volumen=volumen,
        numero_inicio=num_ini,
        numero_fin=num_fin,
        tipo=tipo,
    )
```

### Casos base obligatorios para `tests/test_reading_order_resolver.py`
- `"Uncanny X-Men (1963) #141–142"` → `("Uncanny X-Men", 1963, None, "141", "142", "issue")`
- `"Batman Vol. 3 (2016) #1-6"` → `("Batman", 2016, 3, "1", "6", "issue")`
- `"Crisis on Infinite Earths #1 (of 12)"` → `("Crisis on Infinite Earths", None, None, "1", None, "issue")`
- `"Swamp Thing Annual (1982) #2"` → `("Swamp Thing", 1982, None, "2", None, "annual")`
- `"Amazing Spider-Man #0.1"` → `("Amazing Spider-Man", None, None, "0.1", None, "issue")`
- `"Part II: The Dark Phoenix Saga"` (encabezado de sección sin `#`) → `None`

---

## Anexo E: Borrador de ADR y Entradas para `LEGAL.md`

### E.1 Plantilla de ADR (`docs/adr/00XX-cache-http-y-fuentes-externas-lectura.md`)

```text
# ADR 00XX: Caché HTTP condicional en PostgreSQL e integración de wikis Fandom y guías de lectura

- Estado: Propuesto
- Fecha: 2026-11-13
- Relacionado con: ADR-0011 (PostgreSQL como única tienda sin Redis), ADR-0013 (Fuentes apagadas por defecto)

## Contexto
ZascArr necesita consultar fuentes adicionales de metadatos (DC/Marvel Database en Fandom) y
órdenes de lectura (Comic Book Reading Orders, Continuity Guide), manteniendo el límite de
512 MB de RAM en Raspberry Pi y la política de máxima cortesía con terceros.

## Decisión
1. No introducir frameworks de crawling ni navegadores headless (Scrapy, Crawlee, Scrapling,
   Playwright) ni un segundo cliente HTTP: reutilizar `httpx` + `cortesia.py` + `peticiones.py` + `lxml`.
2. Incorporar `protego` (BSD-3) como única dependencia nueva para cumplimiento estricto de RFC 9309
   (`robots.txt`, comodines, `Crawl-delay` y bloqueo preventivo ante `429`/`5xx`).
3. Crear la tabla `http_cache` en PostgreSQL con cuerpos comprimidos (`zlib`, máx. 2 MiB),
   separando `fresh_until` (hit sin red) de `retain_until` (ventana de revalidación `304 Not Modified`)
   y aplicando coalescencia en vuelo (*singleflight*).
4. Consumir Fandom exclusivamente mediante su API oficial `/api.php` (`redirects=1`, `maxlag=5`),
   nunca mediante scraping del frontend web.
5. Mantener todas las fuentes nuevas desactivadas por defecto (`ADR-0013`) y vinculadas a
   `LEGAL.md` + `legal_version`.

## Consecuencias
- Cero servicios adicionales en Docker y huella de memoria controlada en 512 MB.
- Reducción drástica de tráfico repetido hacia blogs independientes mantenidos por creadores.
- Obligación de separar legal y visualmente en UI el texto CC-BY-SA de Fandom de las portadas
  editoriales, y de almacenar solo referencias fácticas (`use=reference`) en guías de lectura.
```

### E.2 Filas a incorporar en `LEGAL.md` (recordar subir `legal_version` el mismo día)

- **DC Database / Marvel Database (Fandom — `dc.fandom.com`, `marvel.fandom.com`):**
  - *Acceso:* Exclusivamente vía MediaWiki Action API (`/api.php`) con `maxlag=5`, desactivadas por defecto.
  - *Licencia y atribución:* Los textos y metadatos descriptivos aportados por la comunidad están bajo **CC-BY-SA 3.0**; la interfaz muestra siempre enlace directo al artículo original y a la licencia `CC-BY-SA 3.0`. Las imágenes de portadas no están cubiertas por CC-BY-SA (derechos editoriales respectivos): se cachean localmente en disco del usuario solo para identificación privada de su colección, sin hotlinking ni redistribución.
- **Comic Book Reading Orders (`comicbookreadingorders.com`):**
  - *Acceso:* Desactivada por defecto; respeta `robots.txt` y sus directivas `Content-Signals` (`use=reference`, `ai-train=no`, reserva Art. 4 Directiva (UE) 2019/790).
  - *Uso permitido:* Consulta personal local extrayendo únicamente referencias fácticas de ordenación (título, número y posición) con enlace obligatorio a la guía original. ZascArr no almacena ni reproduce los textos editoriales del autor, no redistribuye listas precompiladas y no emplea estos datos para entrenamiento ni entrada de modelos de IA.
- **Continuity Guide (`continuityguide.net`):**
  - *Acceso:* Desactivada por defecto; respeta `robots.txt` (incluyendo la exclusión expresa de `/*?format=json`), intervalos amplios de cortesía y caché local prolongada, enlazando siempre a la guía original sin redistribuir su contenido.
- **Foros externos configurados por el usuario sobre HTTP sin TLS (ej. `forum_scraper`):**
  - *Aviso de seguridad y responsabilidad:* Desactivado por defecto; el usuario introduce bajo su responsabilidad la URL y sus credenciales personales. Si el foro opera sobre `http://` sin cifrado TLS, las credenciales y sesiones transitan sin cifrar hacia dicho servidor externo, recomendándose expresamente no reutilizar contraseñas.