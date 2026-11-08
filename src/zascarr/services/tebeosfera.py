"""
Cliente Tebeosfera (scraping) — fuente del enricher para las tradiciones
tebeo y franco_belgian (grapa/álbum en español; confirmado con búsquedas
reales — "Thorgal", BD franco-belga, aparece en Tebeosfera con ediciones
españolas de Distrinovel/Zinco/Norma).

Tebeosfera no tiene API pública: esto es scraping de dos endpoints AJAX
internos de su propio buscador (los mismos que usa su frontend). Portado
con inspiración directa de theotocopulitos/tebeosfera-scraper (Apache
2.0) — ese proyecto documentó los endpoints y la estructura HTML de la
que parte este cliente; gracias a su parser de 700 líneas para la ficha
completa de un número, que confirmó que replicarlo entero es un proyecto
en sí mismo y no algo para portar de una sentada.

Endpoints (confirmados en vivo contra tebeosfera.com, no solo leídos del
repo de referencia — el sitio puede haber cambiado desde que se escribió):
  POST /neko/templates/ajax/buscador_txt_post.php
       {tabla: "T3_publicaciones", busqueda: <query>}  → colecciones
       {tabla: "T3_series",        busqueda: <query>}  → sagas
Cada resultado es un <div class="linea_resultados"> con un <a href="/
colecciones/{slug}.html"> o <a href="/sagas/{slug}.html"> cuyo texto es
el título CON un sufijo "(año, editorial)" pegado que hay que limpiar
antes de comparar contra Series.title.

Fragilidad asumida: al no ser una API con contrato, cualquier rediseño
del sitio puede romper este cliente sin aviso. Por eso el rate limit es
más conservador que el de Comic Vine/AniList, y cualquier fallo de red o
de parseo se trata como "sin resultado" (nunca como excepción que tumbe
el ciclo del enricher — ver enricher.py, que ya envuelve esto en su
propio try/except de todos modos, pero el propio cliente no debe ni
necesita propagar fallos de parseo HTML como errores duros).

Cortesía (decisión del PROYECTO, conservadora; no una afirmación sobre la política oficial del
sitio): **2,5 s como mínimo entre peticiones**, compartido por TODAS las instancias y caminos del
proceso (`utils/cortesia.py`): la búsqueda de Descubrir y el enricher llegan al sitio por el mismo
limitador, cada salto HTTP incluido (las redirecciones se siguen a mano, ≤ 3 y solo al propio
origen). Depende de que haya un solo proceso (`uvicorn --workers 1`). Una configuración por
debajo del mínimo se eleva a él.

Alcance deliberado: solo a nivel de SERIE (título, portada, año, nº de
números). Sinopsis/créditos por número requerirían parsear la ficha
completa de cada número — fuera de alcance de esta primera pasada, igual
que AniList solo enriquece a nivel de serie.
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
import structlog
from lxml import html as lxml_html

from zascarr.config import get_settings
from zascarr.utils.cortesia import (
    CortesiaProceso,
    PoliticaFuente,
    politica_de,
)
from zascarr.utils.peticiones import (
    DemasiadasRedirecciones,
    ErrorDePeticion,
    RedireccionNoPermitida,
    RespuestaNoTransitoria,
    pedir_con_cortesia,
)

logger = structlog.get_logger()

_BASE_URL = "https://www.tebeosfera.com"
SITIO = "tebeosfera"
#: Mínimo entre peticiones, en segundos. Decisión del proyecto (revisión del 2026-10-07): es una
#: asociación cultural sin ánimo de lucro y un scraping sin contrato; se prefiere pecar de cortés.
#: Solo se puede SUBIR.
MINIMO_ENTRE_PETICIONES_S = 2.5
#: Saltos de redirección que se siguen como máximo. Cada salto es una petición más al sitio y pasa
#: por el limitador (2,5 s), igual que la inicial; se siguen A MANO, no con `follow_redirects`.
MAX_SALTOS = 3
_REDIRECCIONES = (301, 302, 303, 307, 308)
_SEARCH_ENDPOINT = "/neko/templates/ajax/buscador_txt_post.php"
#: Origen del sitio para la cola del limitador (esquema, host, puerto normalizados).
_ORIGEN_SITIO = "https://www.tebeosfera.com:443"



def destino_permitido(url: str) -> bool:
    """Política de redirecciones: solo el ORIGEN del sitio (esquema, host y puerto de `_BASE_URL`),
    sin credenciales. Cualquier otro destino (otro host, http, otro puerto, CDN, `//otrohost`) se
    rechaza."""
    try:
        destino, base = urlsplit(url), urlsplit(_BASE_URL)
        puerto = 443 if base.scheme == "https" else 80
        return (destino.scheme == base.scheme and destino.hostname == base.hostname
                and destino.port in (None, base.port, puerto)
                and destino.username is None and destino.password is None)
    except ValueError:
        return False


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# \d{1,4}, no \d+: ninguna colección real tiene 5+ dígitos de números. Si
# algún otro artefacto de concatenación cuela un número disparatado, que
# el regex no lo capture es más seguro que capturarlo y confiar en él.
_COUNT_RE = re.compile(r"(\d{1,4})\s*n[uú]meros?", re.IGNORECASE)
# "THORGAL (1981, DISTRINOVEL)" / "THORGAL (1990, NORMA) -SUBCOLECCION-"
# → "THORGAL": todo lo que sigue al primer paréntesis es ruido de catálogo,
# nunca parte del nombre real de la serie.
_TITLE_SUFFIX_RE = re.compile(r"\s*\([^)]*\).*$")


@dataclass
class TebeosferaResult:
    slug: str
    title: str  # ya limpio de sufijo "(año, editorial)"
    kind: str  # "collection" | "saga"
    start_year: int | None = None
    count_of_issues: int | None = None
    cover_url: str | None = None
    description: str | None = None  # solo disponible a veces, en sagas
    site_url: str | None = None


#: Palabras vacías que no aportan relevancia al comparar títulos.
_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "y", "en", "con", "por", "para",
    "un", "una", "unos", "unas", "al", "a",
}


def _consulta_simplificada(consulta: str) -> str | None:
    """Título principal de la consulta o sus 3 primeras palabras significativas.

    Corta en `:` o en ` - ` (subtítulo) y quita artículos/palabras vacías. Devuelve `None`
    si no hay nada que simplificar (una palabra, o el resultado normalizado no cambia):
    en ese caso no se hace el fallback.
    """
    texto = (consulta or "").strip()
    if not texto:
        return None
    titulo = re.split(r"\s*:\s*|\s+-\s+", texto, maxsplit=1)[0].strip()
    palabras = re.findall(r"[^\W_]+", titulo, flags=re.UNICODE)
    significativas = [p for p in palabras if _normalizar(p) not in _STOPWORDS]
    corta = " ".join(significativas[:3]).strip()
    if not corta or _normalizar(corta) == _normalizar(texto):
        return None
    return corta


def _sin_diacriticos(texto: str) -> str:
    """Quita solo las marcas combinantes (NFD): «Tintín» → «Tintin»."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _primera_palabra_significativa(consulta: str) -> str | None:
    """Primera palabra útil (sin artículos vacíos) para el segundo escalón del fallback."""
    texto = (consulta or "").strip()
    if not texto:
        return None
    titulo = re.split(r"\s*:\s*|\s+-\s+", texto, maxsplit=1)[0].strip()
    palabras = re.findall(r"[^\W_]+", titulo, flags=re.UNICODE)
    for palabra in palabras:
        if _normalizar(palabra) not in _STOPWORDS:
            return palabra
    return None


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y solo letras/dígitos separados por espacios."""
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", sin_acentos.lower()))


def _tokens_relevantes(texto: str) -> set[str]:
    tokens = set(_normalizar(texto).split())
    utiles = tokens - _STOPWORDS
    return utiles or tokens


def _trigramas(texto: str) -> set[str]:
    compacto = _normalizar(texto).replace(" ", "")
    return {compacto[i:i + 3] for i in range(len(compacto) - 2)}


def _puntuacion_relevancia(resultado: TebeosferaResult, consulta: str) -> float:
    """Puntuación de un resultado para una consulta; 0 si no hay relación detectable.

    Combina coincidencia normalizada exacta/contenida, tokens útiles y trigramas de
    caracteres. Los trigramas son los que permiten relacionar «Dragon Ball» con «BOLA DE
    DRAC» (comparten «dra») sin inventar equivalencias. No es una métrica de calidad
    editorial: solo ordena candidatos, nunca descarta.
    """
    consulta_norm = _normalizar(consulta)
    titulo_norm = _normalizar(resultado.title)
    if not consulta_norm or not titulo_norm:
        return 0.0
    if titulo_norm == consulta_norm:
        return 1000.0
    puntuacion = 0.0
    if consulta_norm in titulo_norm:
        puntuacion += 500.0
    elif titulo_norm in consulta_norm:
        puntuacion += 300.0
    tokens_consulta = _tokens_relevantes(consulta)
    if tokens_consulta:
        coincidencias = tokens_consulta & _tokens_relevantes(resultado.title)
        puntuacion += 100.0 * len(coincidencias) / len(tokens_consulta)
    trigramas_consulta = _trigramas(consulta)
    if trigramas_consulta:
        comunes = trigramas_consulta & _trigramas(resultado.title)
        if comunes:
            puntuacion += 50.0 * len(comunes) / len(trigramas_consulta)
    return puntuacion


def ordenar_por_relevancia(resultados: list[TebeosferaResult],
                           consulta: str) -> list[TebeosferaResult]:
    """Reordena candidatos por relación con la consulta; **no descarta ninguno**.

    Orden estable: los empates (incluidos los 0 sin relación) conservan el orden del sitio.
    Función pura: no toca red, parser ni cortesía.
    """
    return [resultado for _, resultado in sorted(
        enumerate(resultados),
        key=lambda par: (-_puntuacion_relevancia(par[1], consulta), par[0]),
    )]


@dataclass(frozen=True)
class TebeosferaColeccion:
    """Campos CRUDOS de una ficha de colección de Tebeosfera (#465).

    El servicio `detalle_edicion` los normaliza a `DetalleEdicion`; aquí no se mapea el
    formato ni se inventan campos que la ficha no trae. `idioma` siempre es `None` hasta
    que la ficha lo exponga (hoy no tiene campo).
    """
    slug: str
    editorial: str | None = None
    sello: str | None = None
    anio: int | None = None
    anio_fin: int | None = None
    numeracion_inicio: int | None = None
    numeracion_fin: int | None = None
    numeracion_texto: str | None = None
    numero_publicacion: str | None = None
    paginas: int | None = None
    formato_fuente: str | None = None
    pais: str | None = None
    idioma: str | None = None
    url_ficha: str | None = None
    peticiones: int = 1
    #: Slugs de las fichas de número enlazadas desde la colección (para resolver un nº).
    numeros_slugs: tuple[str, ...] = ()

    @property
    def formato(self) -> str | None:
        """Texto crudo del formato; el servicio lo mapea a `IssueFormat`."""
        return self.formato_fuente


@dataclass(frozen=True)
class TebeosferaNumero:
    """Campos CRUDOS de una ficha de número de Tebeosfera (#489).

    La ficha de número sí identifica el ejemplar (`numero_publicacion`), a diferencia de la
    colección. `fecha`/`paginas`/`formato_fuente` solo van si la ficha los trae.
    """
    slug: str
    numero_publicacion: str | None = None
    fecha: str | None = None
    paginas: int | None = None
    formato_fuente: str | None = None
    editorial: str | None = None
    sello: str | None = None
    anio: int | None = None
    url_ficha: str | None = None
    peticiones: int = 1

    @property
    def numero(self) -> str | None:
        """Alias de lectura del número del ejemplar."""
        return self.numero_publicacion

    @property
    def formato(self) -> str | None:
        """Texto crudo del formato; el servicio lo mapea a `IssueFormat`."""
        return self.formato_fuente


class TebeosferaClient:
    def __init__(self, transporte: httpx.AsyncBaseTransport | None = None, *,
                 politica: PoliticaFuente | None = None,
                 cortesia: CortesiaProceso | None = None,
                 reloj=time.monotonic, dormir=asyncio.sleep, espera_max_s: float = 30.0):
        # `transporte`/`cortesia`/`reloj`/`dormir`: solo para pruebas; en producción, por defecto.
        s = get_settings()
        configurado = float(s.tebeosfera_rate_limit)
        if configurado < MINIMO_ENTRE_PETICIONES_S:
            logger.warning("tebeosfera.rate_limit_elevado", configurado=configurado,
                           minimo=MINIMO_ENTRE_PETICIONES_S)
        self._politica = politica or politica_de("tebeosfera", s)
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._transporte = transporte
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            transport=self._transporte,
            base_url=_BASE_URL, timeout=30.0, follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ZascArr/0.1; +comic library manager)",
                "Referer": _BASE_URL + "/",
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        """Compatibilidad: espera con la cortesía compartida (sin cadencia por instancia)."""
        await self._cortesia_efectiva().esperar(
            "tebeosfera", _ORIGEN_SITIO, espera_max_s=self._espera_max_s)

    def _cortesia_efectiva(self) -> CortesiaProceso:
        if self._cortesia is not None:
            return self._cortesia
        from zascarr.utils.cortesia import cortesia_de_proceso

        return cortesia_de_proceso()

    async def _search_table(self, tabla: str, kind: str, query: str) -> list[TebeosferaResult]:
        if self._client is None:
            raise RuntimeError("Cliente de Tebeosfera sin abrir: úsalo con `async with`.")
        try:
            # Cada petición y cada salto pasan por la cola de la envoltura común: 2,5 s mínimo,
            # ≤3 redirecciones, solo el origen del sitio y un único intento (política de la
            # fuente). Los fallos de redirección/HTTP siguen siendo «sin resultados».
            r = await pedir_con_cortesia(
                self._client, "POST", f"{_BASE_URL}{_SEARCH_ENDPOINT}",
                politica=self._politica, espera_max_s=self._espera_max_s,
                datos={"tabla": tabla, "busqueda": query}, form=True,
                cortesia=self._cortesia, reloj=self._reloj, dormir=self._dormir,
            )
        except RedireccionNoPermitida as exc:
            # Solo el host del destino y el motivo; nunca la URL ni la query (§6.6).
            logger.warning("tebeosfera.redireccion_rechazada", host=exc.host or None,
                           motivo=exc.motivo)
            return []
        except DemasiadasRedirecciones:
            logger.warning("tebeosfera.demasiadas_redirecciones", saltos=MAX_SALTOS)
            return []
        except (httpx.HTTPError, ErrorDePeticion):
            logger.warning("tebeosfera.request_failed", tabla=tabla)
            return []
        return _parse_results(r.text, kind)

    async def search_series(self, query: str, limit: int = 10) -> list[TebeosferaResult]:
        """Busca en colecciones (ediciones/tiradas concretas) y sagas (la
        obra en su conjunto): dos peticiones, el doble que Comic Vine/
        AniList — ver la nota de rate limit en config.py."""
        async def buscar(consulta: str) -> list[TebeosferaResult]:
            colecciones = await self._search_table(
                "T3_publicaciones", "collection", consulta)
            sagas = await self._search_table("T3_series", "saga", consulta)
            return colecciones + sagas

        resultados = await buscar(query)
        if not resultados:
            # Escalón 1: título principal / 3 palabras significativas.
            corta = _consulta_simplificada(query)
            if corta:
                resultados = await buscar(corta)
            # Escalón 2: primera palabra significativa (aunque la consulta tenga
            # exactamente 3 palabras y no haya podido acortarse a 3).
            primera = _primera_palabra_significativa(query)
            if (not resultados and primera is not None
                    and _normalizar(primera) != _normalizar(query)
                    and (not corta or _normalizar(primera) != _normalizar(corta))):
                resultados = await buscar(primera)
            # Escalón 3 (último): misma palabra sin diacríticos, solo si cambia.
            if not resultados and primera is not None:
                sin_tilde = _sin_diacriticos(primera)
                if sin_tilde != primera:
                    resultados = await buscar(sin_tilde)
        # Ordenar ANTES de recortar con la consulta ORIGINAL; los empates conservan el sitio.
        return ordenar_por_relevancia(resultados, query)[:limit]

    async def get_collection(self, slug: str, *,
                             espera_max_s: float = 30.0) -> TebeosferaColeccion | None:
        """Lee UNA ficha de colección por `pedir_con_cortesia` (misma cortesía, 1 petición).

        Solo se pide la ficha HTML, nunca la galería de portadas ni imágenes. Un 404/HTML sin
        ficha devuelve `None`; los estados de #133 los decide quien consuma el resultado.
        """
        slug = (slug or "").strip()
        if not slug or self._client is None:
            return None
        url = f"{_BASE_URL}/colecciones/{quote(slug, safe='-_.~')}.html"
        try:
            r = await pedir_con_cortesia(
                self._client, "GET", url,
                politica=self._politica, espera_max_s=espera_max_s,
                cortesia=self._cortesia_efectiva(), reloj=self._reloj,
                dormir=self._dormir,
            )
        except (RespuestaNoTransitoria, ErrorDePeticion, httpx.HTTPError):
            logger.warning("tebeosfera.get_collection_failed", slug=slug)
            return None
        return _parse_collection(r.text, slug)


    async def get_numero(self, slug: str, *,
                         espera_max_s: float = 30.0) -> TebeosferaNumero | None:
        """Lee UNA ficha de número (`/numeros/<slug>.html`) por `pedir_con_cortesia`.

        Sin galería ni imágenes; un 404/HTML sin ficha devuelve `None`. No toca la ficha de
        colección ni hace una segunda petición.
        """
        slug = (slug or "").strip()
        if not slug or self._client is None:
            return None
        url = f"{_BASE_URL}/numeros/{quote(slug, safe='-_.~')}.html"
        try:
            r = await pedir_con_cortesia(
                self._client, "GET", url,
                politica=self._politica, espera_max_s=espera_max_s,
                cortesia=self._cortesia_efectiva(), reloj=self._reloj,
                dormir=self._dormir,
            )
        except (RespuestaNoTransitoria, ErrorDePeticion, httpx.HTTPError):
            logger.warning("tebeosfera.get_numero_failed", slug=slug)
            return None
        return _parse_numero(r.text, slug)


    async def get_numero_de_coleccion(self, coleccion_slug: str, numero: Any, *,
                                      espera_max_s: float = 30.0) -> TebeosferaNumero | None:
        """Resuelve un número concreto dentro de una colección: 2 peticiones.

        1) ficha de colección (para obtener los enlaces `/numeros/`);
        2) ficha del número cuyo slug termina en `-<numero>` o `_<numero>`.
        Ambas por `pedir_con_cortesia`; si no hay enlace para ese número, `None`.
        """
        try:
            objetivo = str(int(numero))
        except (TypeError, ValueError):
            return None
        coleccion = await self.get_collection(coleccion_slug, espera_max_s=espera_max_s)
        if coleccion is None:
            return None
        candidatos = [
            slug for slug in coleccion.numeros_slugs
            if re.search(rf"(?:^|[-_]){re.escape(objetivo)}$", slug)
        ]
        if not candidatos:
            return None
        numero_detalle = await self.get_numero(candidatos[0], espera_max_s=espera_max_s)
        if numero_detalle is None:
            return None
        from dataclasses import replace
        return replace(numero_detalle, peticiones=2)


def _parse_numero(html_fragment: str, slug: str) -> TebeosferaNumero | None:
    """Parser defensivo de la ficha de número; los campos ausentes quedan `None`."""
    if not html_fragment:
        return None
    try:
        tree = lxml_html.fromstring(html_fragment)
    except Exception:
        logger.warning("tebeosfera.parse_numero_failed", slug=slug)
        return None
    ficha = tree.xpath('//div[@id="cuerpo2_ficha"]')
    if not ficha:
        ficha = tree.xpath('//div[@id="div_ficha"]')
    if not ficha:
        return None
    ficha = ficha[0]
    texto = " ".join(ficha.text_content().split())

    numero = None
    m_numero = re.search(r"N[º°]\s*(\d+)\s+de\b", texto, re.IGNORECASE)
    if m_numero:
        numero = str(int(m_numero.group(1)))
    else:
        m_numero = re.search(r"N[º°]\s*(\d+)\b", texto, re.IGNORECASE)
        if m_numero:
            numero = str(int(m_numero.group(1)))

    fecha = None
    m_fecha = re.search(r"\b(\d{1,2}-[IVXLC]+-\d{4})\b", texto)
    if m_fecha:
        fecha = m_fecha.group(1)
    anio = None
    if fecha:
        m_anio = re.search(r"(\d{4})$", fecha)
        if m_anio:
            anio = int(m_anio.group(1))

    paginas = None
    m_paginas = re.search(r"(\d+)\s*p[áa]gs?\.", texto, re.IGNORECASE)
    if m_paginas:
        paginas = int(m_paginas.group(1))

    formato_fuente = _texto_dato(ficha, "Formato:")
    editorial = sello = None
    entidades = ficha.xpath('.//a[contains(@href,"/entidades/")]')
    nombres = [(a.text_content() or "").strip() for a in entidades]
    nombres = [n for n in nombres if n]
    if nombres:
        editorial = nombres[0]
    if len(nombres) > 1:
        sello = nombres[1]

    return TebeosferaNumero(
        slug=slug, numero_publicacion=numero, fecha=fecha, paginas=paginas,
        formato_fuente=formato_fuente, editorial=editorial, sello=sello, anio=anio,
        url_ficha=f"{_BASE_URL}/numeros/{quote(slug, safe='-_.~')}.html",
        peticiones=1,
    )


def _parse_collection(html_fragment: str, slug: str) -> TebeosferaColeccion | None:
    """Parser defensivo de la ficha de colección; cada campo ausente queda `None`."""
    if not html_fragment:
        return None
    try:
        tree = lxml_html.fromstring(html_fragment)
    except Exception:
        logger.warning("tebeosfera.parse_collection_failed", slug=slug)
        return None
    ficha = tree.xpath('//div[@id="div_ficha"]')
    if not ficha:
        ficha = tree.xpath('//div[@id="cuerpo2_ficha"]')
    if not ficha:
        return None
    ficha = ficha[0]

    editorial = sello = None
    # La ficha completa trae avisos con clase `tebeoaviso_titulo`; el bloque real está en
    # `#cuerpo1_ficha`. Se busca la clase EXACTA `titulo`, no una subcadena.
    cabecera = ficha.xpath('.//div[@id="cuerpo1_ficha"]')
    scope = cabecera[0] if cabecera else ficha
    titulo = scope.xpath('.//div[contains(concat(" ", normalize-space(@class), " "), " titulo ")]')
    if titulo:
        enlaces = titulo[0].xpath('.//a[contains(@href,"/entidades/")]')
        textos = [(a.text_content() or "").strip() for a in enlaces]
        textos = [t for t in textos if t]
        if textos:
            editorial = textos[0]
        if len(textos) > 1:
            sello = textos[1]

    pais = None
    bandera = ficha.xpath(
        './/*[@title="España" or @title="Espanya" or @title="Spain" '
        'or contains(@src,"spain.png")]')
    if bandera:
        pais = "ES"

    fechas = _texto_dato(ficha, "Fechas:")
    anio = anio_fin = None
    if fechas:
        años = [int(m.group(0)) for m in _YEAR_RE.finditer(fechas)]
        if años:
            anio = años[0]
            if len(años) > 1 and años[-1] != anio:
                anio_fin = años[-1]
    if anio is None:
        # La ficha a veces repite el año en el título; solo como fallback del mismo bloque.
        titulo_texto = " ".join(t for t in (ficha.xpath('.//h1//text()') or []) if t)
        años_titulo = [int(m.group(0)) for m in _YEAR_RE.finditer(titulo_texto)]
        if años_titulo:
            anio = años_titulo[0]

    numeracion_texto = None
    inicio = fin = None
    nodos_num = ficha.xpath('.//*[contains(text(),"Numeración:")]')
    if nodos_num:
        texto_num = " ".join(nodos_num[0].getparent().text_content().split())
        m = re.search(r"Numeración:\s*(\d+)\s*(?:a|–|-)\s*(\d+)", texto_num,
                      re.IGNORECASE)
        if m:
            numeracion_texto = f"{m.group(1)} a {m.group(2)}"
            inicio, fin = int(m.group(1)), int(m.group(2))
        else:
            m1 = re.search(r"Numeración:\s*(\d+)", texto_num, re.IGNORECASE)
            if m1:
                numeracion_texto = m1.group(1)
                inicio = int(m1.group(1))

    formato_fuente = _texto_dato(ficha, "Formato:")
    if formato_fuente:
        formato_fuente = re.sub(r"\[\s*\d+(?:\s*-\s*\d+)?\s*\]", "", formato_fuente)
        formato_fuente = " ".join(formato_fuente.split()).strip(" /") or None

    paginas = None
    paginacion = _texto_dato(ficha, "Paginación:")
    if paginacion:
        valores = {int(n) for n in re.findall(r"(\d+)\s*pp\.", paginacion, re.IGNORECASE)}
        if len(valores) == 1:
            paginas = valores.pop()

    numeros_slugs: list[str] = []
    for enlace in ficha.xpath('.//a[contains(@href,"/numeros/")]'):
        href = enlace.get("href") or ""
        if "/numeros/" not in href:
            continue
        slug_numero = href.split("/numeros/", 1)[1].split(".html", 1)[0].strip("/")
        if slug_numero and slug_numero not in numeros_slugs:
            numeros_slugs.append(slug_numero)

    return TebeosferaColeccion(
        slug=slug,
        editorial=editorial,
        sello=sello,
        anio=anio,
        anio_fin=anio_fin,
        numeracion_inicio=inicio,
        numeracion_fin=fin,
        numeracion_texto=numeracion_texto,
        numero_publicacion=None,       # la ficha de colección no da el ejemplar
        paginas=paginas,
        formato_fuente=formato_fuente,
        pais=pais,
        idioma=None,                   # hoy no hay campo de idioma en la ficha
        url_ficha=f"{_BASE_URL}/colecciones/{quote(slug, safe='-_.~')}.html",
        peticiones=1,
        numeros_slugs=tuple(numeros_slugs),
    )


def _texto_dato(ficha: Any, etiqueta: str) -> str | None:
    """Texto del `.dato` hermano de una etiqueta (`Fechas:`, `Formato:`...), o `None`."""
    etiquetas = ficha.xpath('.//*[contains(@class,"etiqueta")]')
    for label in etiquetas:
        if (label.text_content() or "").strip().startswith(etiqueta):
            fila = label.getparent()
            datos = fila.xpath('.//*[contains(@class,"dato")]')
            if datos:
                return " ".join(datos[0].text_content().split())
    return None


def _parse_results(html_fragment: str, kind: str) -> list[TebeosferaResult]:
    if not html_fragment or "linea_resultados" not in html_fragment:
        return []
    try:
        tree = lxml_html.fromstring(html_fragment)
    except Exception:
        logger.warning("tebeosfera.parse_failed", kind=kind)
        return []

    path = "/colecciones/" if kind == "collection" else "/sagas/"
    results = []
    for row in tree.xpath('//div[contains(@class, "linea_resultados")]'):
        links = row.xpath(f'.//a[contains(@href, "{path}")]')
        if not links:
            continue
        href = links[0].get("href", "")
        slug_match = re.search(rf'{re.escape(path)}([^/]+)\.html', href)
        raw_title = (links[0].text_content() or "").strip()
        if not slug_match or not raw_title:
            continue

        title = _TITLE_SUFFIX_RE.sub("", raw_title).strip()
        # text_content() concatena texto sin insertar espacio donde hubiera
        # un <br>: "1986 a 1988<br>4 números" se convierte en "19884
        # números" y el regex de conteo lee 19884 en vez de 4. Confirmado
        # en vivo contra tebeosfera.com, no una hipótesis: sin este fix,
        # el conteo de números salía disparatado en varias colecciones.
        for br in row.xpath(".//br"):
            br.tail = "\n" + (br.tail or "")
        row_text = row.text_content()
        year_match = _YEAR_RE.search(row_text)
        count_match = _COUNT_RE.search(row_text)
        thumb = row.xpath(".//img/@src")

        results.append(TebeosferaResult(
            slug=slug_match.group(1),
            title=title,
            kind=kind,
            start_year=int(year_match.group(0)) if year_match else None,
            count_of_issues=int(count_match.group(1)) if count_match else None,
            cover_url=thumb[0] if thumb else None,
            site_url=f"{_BASE_URL}{href}",
        ))
    return results
