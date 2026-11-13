"""Clientes de las wikis de Fandom: DC Database y Marvel Database (MediaWiki Action API).

Por qué este módulo (Fase 2 del estudio `docs/estudio-scraping-fuentes-v2.md`):

- Las dos wikis comparten plataforma (MediaWiki 1.43.x verificado en vivo el 2026-11-13)
  y exponen una API oficial en `/api.php`: es la única vía aceptable, nunca el HTML público
  de las páginas `/wiki/...` (va cargado de JS, anuncios y su `robots.txt` responde 403 a
  clientes planos).
- Se trabaja con el **wikitext de las plantillas** (`action=query&prop=revisions`) y no con
  el HTML renderizado: el wikitext de una ficha de serie/issue son unos pocos KB deterministas,
  mientras que páginas como las de Marvel pesan 3 MB y su maquetación cambia. Las plantillas
  verificadas en vivo son `DC Database:Volume Template`, `DC Database:Comic Template`,
  `Marvel Database:Volume Template` y `Marvel Database:Comic Template`.
- Trampas de MediaWiki que este cliente trata (ver Anexo C del estudio):
  * Los errores lógicos llegan con **HTTP 200** (`missingtitle`, `maxlag`): hay que mirar el
    JSON. `missingtitle` → `None`; `maxlag` → bloqueo compartido de cortesía (Retry-After).
  * `maxlag=5` va siempre en la petición (las wikis pueden rechazar peticiones en horas punta).
  * Las redirecciones se siguen a mano por `peticiones.py` (solo mismo origen), así que
    `follow_redirects=False` y `redirects=1` en la query.

- **Parseo acotado (M-1 de SecOps).** El texto viene de una wiki pública y **editable** y
  este módulo parsea dentro del bucle de eventos (con `--workers 1`, un parseo lento
  bloquearía también la UI). Por eso: (a) el cuerpo de una respuesta de `/api.php` tiene
  tope `MAX_CUERPO_API` y el wikitext que se entrega al parser, `MAX_WIKITEXT`; por encima
  se registra un aviso estructurado y se devuelve `None` sin parsear; (b) el parseo del
  wikitext (`limpiar_markup`, `seccion`, enlaces, plantillas) es **lineal**: escaneo manual
  con `find`/`split`, nunca expresiones con retroceso sobre texto sin cierre.

Licencia: el texto de Fandom es CC-BY-SA (atribución con enlace al artículo y a la licencia en
la UI); las portadas son *fair use* editorial y se cachean en local sin etiquetarlas CC-BY-SA.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode

import httpx
import structlog

from zascarr.models import CreatorRole
from zascarr.utils.cortesia import (
    CortesiaProceso,
    PoliticaFuente,
    cortesia_de_proceso,
    origen_normalizado,
    politica_de,
)
from zascarr.utils.peticiones import ErrorDePeticion, pedir_con_cortesia

logger = structlog.get_logger()

#: Fuente de cortesía → host de la wiki. Una fuente por wiki (desactivables por separado,
#: ADR 0013): el usuario puede querer solo Marvel o solo DC.
FUENTES = {
    "fandom_dc": "dc.fandom.com",
    "fandom_marvel": "marvel.fandom.com",
}
#: Host del CDN de portadas (común a las dos wikis). Está en `HOSTS_PERMITIDOS` de
#: `utils/url_portada.py` y en `INTERVALO_PORTADA_POR_HOST` de `utils/cortesia.py`.
CDN_HOST = "static.wikia.nocookie.net"

#: Tope del cuerpo de una respuesta de `/api.php` (M-1 de SecOps). Una revisión normal entra de
#: sobra; por encima no se parsea: el texto lo edita cualquiera en una wiki pública.
MAX_CUERPO_API = 2 * 1024 * 1024
#: Tope del wikitext que se entrega al parser (M-1). 1.000.000 de caracteres es más de 20 veces
#: la página real más grande medida; por encima se registra y se descarta sin parsear.
MAX_WIKITEXT = 1_000_000
#: Tope defensivo del título de una página (RES-2). MediaWiki limita los títulos a ~255 bytes;
#: por encima de esto el valor es hostil y `titulo_base` no lo normaliza (sus regex de sufijo
#: serían cuadráticos con rachas de espacios): se devuelve recortado a este tamaño.
MAX_TITULO_PAGINA = 1024
#: Tope del texto que se examina buscando una fecha (RES-1). Un `ReleaseDate` real ocupa <30
#: caracteres; con esto el coste es constante aunque el valor venga manipulado, y los patrones
#: en inglés siguen siendo acotados por si el texto real trae algún prefijo.
MAX_TEXTO_FECHA = 512

#: Plantillas por tipo de página (verificadas en vivo el 2026-11-13).
_PLANTILLAS = {
    "dc.fandom.com": {
        "volume": "DC Database:Volume Template",
        "comic": "DC Database:Comic Template",
        "arc": "DC Database:Storyline Template",
    },
    "marvel.fandom.com": {
        "volume": "Marvel Database:Volume Template",
        "comic": "Marvel Database:Comic Template",
        "arc": "Marvel Database:Storyline Template",
    },
}

#: Códigos de error de MediaWiki que significan «la página no existe».
_CODIGOS_INEXISTENTE = frozenset({
    "missingtitle", "invalidtitle", "pagecannotexist", "nosuchpage", "badtitle",
})

#: Roles de las plantillas de issue → `CreatorRole`. Solo se mapea lo inequívoco; el resto
#: de campos (colours, etc.) se ignora en vez de adivinar.
_ROLES = {
    "writer": CreatorRole.WRITER,
    "penciler": CreatorRole.PENCILER,
    "inker": CreatorRole.INKER,
    "colorist": CreatorRole.COLORIST,
    "letterer": CreatorRole.LETTERER,
    "coverartist": CreatorRole.COVER_ARTIST,
    "editor": CreatorRole.EDITOR,
}

#: Parámetros de rol con índice: writer1_1, penciler2_1… (también sin segundo índice).
_RE_ROL = re.compile(r"^(writer|penciler|inker|colorist|letterer|coverartist|editor)\d+(_\d+)?$")

_MESES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_RE_VOL_FINAL = re.compile(r"\s+Vol(?:ume)?\.?\s*\d+\s*$", re.IGNORECASE)
_RE_COLLECTED = re.compile(r"\s*\(Collected\)\s*$", re.IGNORECASE)
#: Negritas/cursivas wiki. `'{2,5}` no tiene cuantificadores anidados: es lineal y no puede
#: colgarse con apóstrofos sin cierre, así que se queda como regex.
_RE_NEGRITA = re.compile(r"'{2,5}")
_RE_ANIO_RANGO = re.compile(r"\(\s*(\d{4})\s*[–\-—]\s*(\d{4})?\s*\)")
_RE_FECHA_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
#: Fecha en inglés con el mes primero («August 8, 1961»). Cuantificadores ACOTADOS (RES-1 de
#: SecOps): con `[A-Za-z]+` el `search` es cuadrático sobre una cadena de letras y este texto
#: viene de una wiki editable; acotado, cada intento cuesta O(1) y el recorrido es lineal.
_RE_FECHA_MES = re.compile(
    r"([A-Za-z]{1,20})\.?\s{1,5}(\d{1,2}),?\s{1,5}(\d{4})")
#: Fecha en inglés con el día primero («8 August 1961»), también acotada (RES-1).
_RE_FECHA_DIA = re.compile(
    r"(\d{1,2})\s{1,5}([A-Za-z]{1,20})\.?,?\s{1,5}(\d{4})")


# ── Errores de la API ───────────────────────────────────────────────────────────────────────────

def _codigo_seguro(code: object) -> str:
    """Código de error de MediaWiki acotado a un identificador imprimible (m-4 de SecOps).

    El `code` es texto de un tercero y acaba en el mensaje de la excepción y en los logs: sin
    sanear, un salto de línea o una secuencia ANSI permitiría forjar líneas de log.
    """
    return re.sub(r"[^a-z0-9_]", "", str(code or ""))[:40]


class FandomPayloadError(ErrorDePeticion):  # noqa: N818 — nombre del contrato
    """La API respondió con un `error` que no es «no existe» ni `maxlag`."""

    def __init__(self, code: str):
        # El mensaje lleva el código saneado: es lo que llega a los logs (m-4).
        self.code = _codigo_seguro(code)
        super().__init__(f"error de MediaWiki: {self.code}")


class FandomMaxLagError(ErrorDePeticion):  # noqa: N818 — nombre del contrato
    """La wiki pide bajar el ritmo (`maxlag`, con HTTP 200). Transitorio: no se cachea."""

    def __init__(self, retry_after_s: float):
        self.retry_after_s = float(retry_after_s)
        super().__init__("la wiki pide bajar el ritmo (maxlag)")


# ── Utilidades puras (se prueban sin red) ───────────────────────────────────────────────────────

def extraer_plantilla(wikitext: str, prefijo: str) -> str | None:
    """Devuelve el texto completo `{{<prefijo> ... }}` balanceado, o None si no está."""
    inicio = wikitext.find("{{" + prefijo)
    if inicio < 0:
        return None
    i, profundidad = inicio, 0
    while i < len(wikitext):
        if wikitext.startswith("{{", i):
            profundidad += 1
            i += 2
        elif wikitext.startswith("}}", i):
            profundidad -= 1
            i += 2
            if profundidad == 0:
                return wikitext[inicio:i]
        else:
            i += 1
    return None


def _dividir_parametros(interior: str) -> list[str]:
    """Parte por `|` de nivel 0, respetando `{{...}}` y `[[...]]` anidados en los valores."""
    partes: list[str] = []
    actual: list[str] = []
    llaves = corchetes = 0
    i = 0
    while i < len(interior):
        dos = interior[i:i + 2]
        if dos == "{{":
            llaves += 1
            actual.append(dos)
            i += 2
        elif dos == "}}":
            llaves = max(0, llaves - 1)
            actual.append(dos)
            i += 2
        elif dos == "[[":
            corchetes += 1
            actual.append(dos)
            i += 2
        elif dos == "]]":
            corchetes = max(0, corchetes - 1)
            actual.append(dos)
            i += 2
        elif interior[i] == "|" and llaves == 0 and corchetes == 0:
            partes.append("".join(actual))
            actual = []
            i += 1
        else:
            actual.append(interior[i])
            i += 1
    partes.append("".join(actual))
    return partes


def parametros_de_plantilla(plantilla: str) -> dict[str, str]:
    """Parámetros de una plantilla ya extraída (`{{...}}`) en un dict con claves minúsculas."""
    interior = plantilla[2:-2]
    partes = _dividir_parametros(interior)
    parametros: dict[str, str] = {}
    for parte in partes[1:]:
        if "=" not in parte:
            continue
        clave, valor = parte.split("=", 1)
        parametros[clave.strip().lower()] = valor.strip()
    return parametros


def _quitar_comentarios(texto: str) -> str:
    """Quita `<!-- … -->` con búsqueda de cierre por índice (lineal); sin cierre, se conserva."""
    partes: list[str] = []
    i = 0
    while True:
        inicio = texto.find("<!--", i)
        if inicio < 0:
            partes.append(texto[i:])
            return "".join(partes)
        partes.append(texto[i:inicio])
        fin = texto.find("-->", inicio + 4)
        if fin < 0:
            # Comentario sin cierre: el wikitext roto se deja tal cual (no se inventa el final).
            partes.append(texto[inicio:])
            return "".join(partes)
        i = fin + 3


def _quitar_refs(texto: str) -> str:
    """Quita `<ref>…</ref>` y `<ref …/>` con escaneo lineal; una ref sin cierre se conserva."""
    bajo = texto.lower()
    partes: list[str] = []
    i = 0
    while True:
        inicio = bajo.find("<ref", i)
        if inicio < 0:
            partes.append(texto[i:])
            return "".join(partes)
        siguiente = inicio + 4
        # `<references>` y compañía empiezan igual: solo es una ref si la etiqueta termina aquí.
        if siguiente < len(texto) and texto[siguiente] not in " \t\r\n/>":
            partes.append(texto[i:siguiente])
            i = siguiente
            continue
        partes.append(texto[i:inicio])
        fin_etiqueta = texto.find(">", siguiente)
        if fin_etiqueta < 0:
            partes.append(texto[inicio:])
            return "".join(partes)
        if texto[fin_etiqueta - 1] == "/":
            i = fin_etiqueta + 1          # <ref … />: se quita la etiqueta entera
            continue
        cierre = bajo.find("</ref>", fin_etiqueta + 1)
        if cierre < 0:
            partes.append(texto[inicio:])  # ref sin cierre: se conserva
            return "".join(partes)
        i = cierre + len("</ref>")


def _convertir_enlaces(texto: str) -> str:
    """`[[destino|etiqueta]]` → etiqueta y `[[destino]]` → destino, en un solo escaneo lineal."""
    partes: list[str] = []
    i = 0
    while True:
        inicio = texto.find("[[", i)
        if inicio < 0:
            partes.append(texto[i:])
            return "".join(partes)
        fin = texto.find("]]", inicio + 2)
        if fin < 0:
            partes.append(texto[i:])      # sin cierre: se conserva el resto
            return "".join(partes)
        contenido = texto[inicio + 2:fin]
        if "|" in contenido:
            destino, etiqueta = contenido.split("|", 1)
            if destino and "]" not in destino and etiqueta and "]" not in etiqueta:
                partes.append(texto[i:inicio] + etiqueta)
                i = fin + 2
                continue
        # Segunda forma del enlace (`[[destino]]`) o respaldo si el destino no es válido.
        if contenido and "]" not in contenido:
            partes.append(texto[i:inicio] + contenido)
            i = fin + 2
            continue
        # Enlace roto: se deja tal cual y se sigue buscando a partir de su cierre.
        partes.append(texto[i:fin + 2])
        i = fin + 2


def _quitar_externos(texto: str) -> str:
    """`[http://… etiqueta]` → etiqueta (o nada), con escaneo lineal; sin cierre, se conserva."""
    partes: list[str] = []
    i = 0
    while True:
        inicio = texto.find("[", i)
        if inicio < 0:
            partes.append(texto[i:])
            return "".join(partes)
        pos = inicio + 1
        if texto.startswith("//", pos):
            pos += 2
        elif texto.startswith("http://", pos):
            pos += len("http://")
        elif texto.startswith("https://", pos):
            pos += len("https://")
        else:
            partes.append(texto[i:pos])   # «[» que no abre un enlace externo
            i = pos
            continue
        fin_url = pos
        while fin_url < len(texto) and not texto[fin_url].isspace() \
                and texto[fin_url] != "]":
            fin_url += 1
        if fin_url == pos:                # `[…//]`: no hay URL, no es un enlace externo
            partes.append(texto[i:pos])
            i = pos
            continue
        etiqueta_desde = fin_url
        while etiqueta_desde < len(texto) and texto[etiqueta_desde].isspace():
            etiqueta_desde += 1
        cierre = texto.find("]", etiqueta_desde)
        if cierre < 0:
            partes.append(texto[i:])      # sin cierre: se conserva el resto
            return "".join(partes)
        partes.append(texto[i:inicio] + texto[etiqueta_desde:cierre])
        i = cierre + 1


def _quitar_etiquetas(texto: str) -> str:
    """Quita `<etiqueta …>` con búsqueda de `>` por índice (lineal); un `<` sin `>` se conserva."""
    partes: list[str] = []
    i = 0
    while True:
        inicio = texto.find("<", i)
        if inicio < 0:
            partes.append(texto[i:])
            return "".join(partes)
        fin = texto.find(">", inicio + 1)
        if fin < 0:
            partes.append(texto[i:])
            return "".join(partes)
        if fin == inicio + 1:             # `<>` no es una etiqueta
            partes.append(texto[i:fin])
            i = fin
            continue
        partes.append(texto[i:inicio])
        i = fin + 1


def limpiar_markup(texto: str | None) -> str:
    """Texto wiki → texto plano: comentarios, refs, enlaces, negritas y etiquetas fuera.

    Todo el recorrido es lineal (M-1 de SecOps): el wikitext viene de una wiki editable y este
    parseo corre en el bucle de eventos; una página vandalizada no puede colgar el proceso.
    """
    if not texto:
        return ""
    texto = _quitar_comentarios(texto)
    texto = _quitar_refs(texto)
    texto = _convertir_enlaces(texto)
    texto = _quitar_externos(texto)
    texto = _RE_NEGRITA.sub("", texto)
    texto = _quitar_etiquetas(texto)
    return " ".join(texto.split()).strip()


def titulo_base(page_title: str) -> str:
    """«Batman Vol 1» → «Batman»; «Batman Archives Vol 1 (Collected)» → «Batman Archives».

    Un título de más de `MAX_TITULO_PAGINA` caracteres no es de MediaWiki (limita ~255 bytes):
    no se normaliza, se devuelve recortado. Sin el cap, los `\\s*` de los patrones de sufijo
    son cuadráticos con rachas largas de espacios (RES-2 de SecOps).
    """
    if len(page_title) > MAX_TITULO_PAGINA:
        return page_title[:MAX_TITULO_PAGINA]
    base = _RE_COLLECTED.sub("", page_title.strip())
    return _RE_VOL_FINAL.sub("", base).strip()


def referencia_de_issue(page_title: str) -> tuple[str, str] | None:
    """«Batman Vol 1 404» → («Batman Vol 1», «404»); None si no tiene esa forma."""
    m = re.match(r"^(.+?\bVol(?:ume)?\.?\s*\d+)\s+([^/\s]+)$", page_title.strip(), re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def primer_parrafo(wikitext: str) -> str | None:
    """Primer párrafo de prosa del wikitext (fuera de plantillas, tablas y encabezados)."""
    lineas: list[str] = []
    for linea in wikitext.splitlines():
        limpia = linea.strip()
        if not limpia:
            if lineas:
                break
            continue
        if limpia.startswith(("{{", "|", "}}", "==", "[[", "{|", "|-", "!", "}", "*", "#", ";")):
            if lineas:
                break
            continue
        lineas.append(limpia)
    if not lineas:
        return None
    texto = limpiar_markup(" ".join(lineas))
    return texto or None


def _cabecera(linea: str) -> tuple[int, str] | None:
    """(nivel, texto) si la línea es una cabecera wiki `== texto ==`; None si no lo es."""
    limpia = linea.strip()
    if not limpia.startswith("=="):
        return None
    nivel = len(limpia) - len(limpia.lstrip("="))
    resto = limpia[nivel:]
    sin_cierre = resto.rstrip("=")
    if len(resto) - len(sin_cierre) < 2:
        return None
    texto = sin_cierre.strip()
    if not texto or "=" in texto:
        return None
    return nivel, texto


def _empieza_seccion(linea: str) -> bool:
    """¿La línea abre una sección? Equivale al lookahead `\\n=+\\s*[^\\n=]`, sin regex global."""
    limpia = linea.lstrip()
    if not limpia.startswith("="):
        return False
    resto = limpia.lstrip("=").lstrip()
    return bool(resto) and not resto.startswith("=")


def seccion(wikitext: str, titulo: str) -> str | None:
    """Texto de la sección `== <titulo> ==` (cualquier nivel), hasta la siguiente sección.

    Se recorre línea a línea (M-1 de SecOps): sin regex con lookahead sobre todo el texto, una
    racha de `=` no puede disparar un comportamiento cuadrático.
    """
    objetivo = " ".join(titulo.split()).lower()
    lineas = wikitext.splitlines()
    inicio: int | None = None
    for indice, linea in enumerate(lineas):
        cabecera = _cabecera(linea)
        if cabecera is not None and cabecera[1].lower() == objetivo:
            inicio = indice + 1
            break
    if inicio is None:
        return None
    for indice in range(inicio, len(lineas)):
        if _empieza_seccion(lineas[indice]):
            return "\n".join(lineas[inicio:indice])
    return "\n".join(lineas[inicio:])


def _destinos_de_enlace(texto: str | None) -> list[str]:
    """Destinos `[[…]]` en orden de aparición y sin repetir (`set` para no ser O(k²))."""
    if not texto:
        return []
    vistos: set[str] = set()
    destinos: list[str] = []
    for destino in re.findall(r"\[\[([^\]|#]+)", texto):
        destino = destino.strip()
        if destino and destino not in vistos:
            vistos.add(destino)
            destinos.append(destino)
    return destinos


def enlaces_de_issues(texto: str | None) -> list[str]:
    """Destinos `[[X Vol N M]]` de un texto, en orden y sin repetir (orden de lectura)."""
    return [destino for destino in _destinos_de_enlace(texto)
            if referencia_de_issue(destino)]


def issues_de_valor_de_arc(valor: str | None) -> list[str]:
    """Números de un arco a partir del parámetro `Issues` de su plantilla.

    En las wikis de Fandom ese valor es una lista con el número envuelto en la plantilla
    `{{c|Batman Vol 1 404}}` (y, a veces, también como enlace `[[…]]`); los recopilatorios
    usan otras plantillas (`{{co|…}}`) y no cuentan. Se devuelve en orden de lectura.
    """
    if not valor:
        return []
    encontrados: list[str] = []
    for titulo in re.findall(r"\{\{c\s*\|\s*([^}|]+?)\s*(?:\||\}\})", valor):
        titulo = titulo.strip()
        if referencia_de_issue(titulo) and titulo not in encontrados:
            encontrados.append(titulo)
    for titulo in enlaces_de_issues(valor):
        if titulo not in encontrados:
            encontrados.append(titulo)
    return encontrados


def enlaces_de_pagina(texto: str | None) -> list[str]:
    """Destinos `[[X]]` de un valor de plantilla, en orden y sin repetir."""
    return _destinos_de_enlace(texto)


def fecha_inglesa(texto: str | None) -> date | None:
    """«August 8, 1961» / «8 August 1961» / «1961-08-08» → date; None si no es una fecha.

    Los patrones en inglés están acotados a propósito (RES-1 de SecOps): el texto viene de una
    wiki pública y un `[A-Za-z]+` sin tope haría cuadrático el `search` sobre una cadena de
    letras. Acotar el patrón no pierde fechas válidas (a diferencia de truncar la entrada),
    porque el recorrido sigue siendo completo, solo que lineal. Además se examina como mucho
    `MAX_TEXTO_FECHA` caracteres: un valor hostil de 1M no cuesta recorrerlo entero.
    """
    if not texto:
        return None
    texto = texto[:MAX_TEXTO_FECHA]
    m = _RE_FECHA_ISO.search(texto)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    for patron, grupo_mes, grupo_dia in (
            (_RE_FECHA_MES, 1, 2), (_RE_FECHA_DIA, 2, 1)):
        m = patron.search(texto)
        if m is None:
            continue
        mes = _MESES.get(m.group(grupo_mes).lower())
        if mes is None:
            return None
        try:
            return date(int(m.group(3)), mes, int(m.group(grupo_dia)))
        except ValueError:
            return None
    return None


def _mes(valor: str | None) -> int | None:
    if not valor:
        return None
    texto = valor.strip().lower()
    if texto.isdigit():
        mes = int(texto)
        return mes if 1 <= mes <= 12 else None
    return _MESES.get(texto)


def fecha_de_parametros(parametros: dict[str, str]) -> date | None:
    """Fecha de salida de un `Comic Template` de DC.

    `Pubmonth`/`Pubyear` son la fecha de **venta** y `Day` su día (así lo marca la propia
    wiki, con la nota GCD): es la fecha que corresponde a `Issue.release_date`. `Month`/`Year`
    son la fecha de **portada** y solo se usan como respaldo si la plantilla no declara la de
    venta: mezclar el día de venta con el mes de portada daría una fecha que la fuente no
    afirma (Batman Vol 1 404: portada 1987-02, venta 1986-10-21).
    """
    dia = re.sub(r"\D", "", limpiar_markup(parametros.get("day"))) or "1"
    mes = _mes(limpiar_markup(parametros.get("pubmonth")))
    anio = re.sub(r"\D", "", limpiar_markup(parametros.get("pubyear")))
    if mes is None or not anio:
        mes = _mes(limpiar_markup(parametros.get("month")))
        anio = re.sub(r"\D", "", limpiar_markup(parametros.get("year"))) or anio
    if mes is None or not anio:
        return None
    try:
        return date(int(anio), mes, int(dia))
    except ValueError:
        return None


def anios_de_displaytitle(displaytitle: str | None) -> tuple[int | None, int | None]:
    """«Fantastic Four Vol 1 (1961–1996)» → (1961, 1996); tolera el HTML del `span`."""
    if not displaytitle:
        return None, None
    m = _RE_ANIO_RANGO.search(displaytitle)
    if not m:
        suelto = re.search(r"\((\d{4})", displaytitle)
        return (int(suelto.group(1)), None) if suelto else (None, None)
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def creditos_de_parametros(parametros: dict[str, str]) -> dict[str, list[str]]:
    """Roles → nombres limpios, a partir de los parámetros `writer1_1`, `penciler1_1`…"""
    creditos: dict[str, list[str]] = {}
    for clave, valor in parametros.items():
        m = _RE_ROL.match(clave)
        if not m or not valor:
            continue
        rol = _ROLES[m.group(1)]
        for nombre in limpiar_markup(valor).split(";"):
            nombre = nombre.strip()
            if nombre and nombre not in creditos.setdefault(rol.value, []):
                creditos[rol.value].append(nombre)
    return creditos


def nombre_de_imagen(parametros: dict[str, str], claves: tuple[str, ...]) -> str | None:
    """Nombre de fichero de una portada (`Image`, `IssueImage`, `Image1`), sin `File:`."""
    for clave in claves:
        valor = (parametros.get(clave) or "").strip()
        if valor:
            valor = valor.removeprefix("File:").strip()
            if valor.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                return valor
    return None


# ── Resultados normalizados ─────────────────────────────────────────────────────────────────────

@dataclass
class FandomVolume:
    """Ficha de serie («volume») de una wiki Fandom."""

    page_title: str
    title: str
    start_year: int | None = None
    end_year: int | None = None
    total_issues: int | None = None
    kind: str | None = None
    description: str | None = None
    cover_url: str | None = None
    #: Títulos de página de los arcos declarados por la plantilla (solo DC).
    story_arcs: list[str] = field(default_factory=list)


@dataclass
class FandomIssue:
    """Ficha de un número («comic») de una wiki Fandom."""

    page_title: str
    release_date: date | None = None
    synopsis: str | None = None
    story_title: str | None = None
    cover_url: str | None = None
    #: `CreatorRole.value` → nombres (sin repetir).
    credits: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class FandomArc:
    """Ficha de un arco («story arc») con sus números en orden de lectura."""

    page_title: str
    title: str
    description: str | None = None
    #: Títulos de página de issue, en orden de lectura declarado; sin repetir.
    issues: list[str] = field(default_factory=list)


# ── Cliente ─────────────────────────────────────────────────────────────────────────────────────

class FandomClient:
    """Cliente de UNA wiki Fandom (DC o Marvel). La fuente y el ritmo salen de `cortesia.py`."""

    def __init__(
        self,
        host: str,
        *,
        transporte: httpx.AsyncBaseTransport | None = None,
        cortesia: CortesiaProceso | None = None,
        politica: PoliticaFuente | None = None,
        reloj=time.monotonic,
        dormir=asyncio.sleep,
        espera_max_s: float = 30.0,
    ):
        if host not in FUENTES.values():
            raise ValueError(f"host Fandom desconocido: {host}")
        self._host = host
        self._fuente = next(f for f, h in FUENTES.items() if h == host)
        self._transporte = transporte  # solo pruebas
        self._politica = politica
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> FandomClient:
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── transporte ─────────────────────────────────────────────────────────────────────────────
    def _cliente(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=self._transporte, timeout=25.0, follow_redirects=False
            )
        return self._client

    def _politica_actual(self) -> PoliticaFuente:
        if self._politica is None:
            self._politica = politica_de(self._fuente)
        return self._politica

    def _cortesia_actual(self) -> CortesiaProceso:
        if self._cortesia is None:
            self._cortesia = cortesia_de_proceso()
        return self._cortesia

    async def _api(self, params: dict[str, str]) -> dict | None:
        """Una llamada a `/api.php`. Devuelve el JSON, o None si la página no existe."""
        base = {
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
            "redirects": "1",
            **params,
        }
        url = f"https://{self._host}/api.php?{urlencode(base)}"
        respuesta = await pedir_con_cortesia(
            self._cliente(), "GET", url,
            politica=self._politica_actual(),
            espera_max_s=self._espera_max_s,
            cortesia=self._cortesia_actual(),
            reloj=self._reloj, dormir=self._dormir,
        )
        # M-1 de SecOps: una respuesta desmedida no se parsea (el wikitext lo edita cualquiera).
        cuerpo = respuesta.content or b""
        if len(cuerpo) > MAX_CUERPO_API:
            logger.warning("fandom.respuesta_demasiado_grande", wiki=self._host,
                           bytes=len(cuerpo), limite=MAX_CUERPO_API)
            return None
        data = respuesta.json()
        error = data.get("error")
        if error:
            codigo = str(error.get("code") or "")
            if codigo == "maxlag":
                segundos = _segundos_de_maxlag(respuesta, error)
                try:
                    origen = origen_normalizado(f"https://{self._host}/")
                except ValueError:
                    origen = self._host
                self._cortesia_actual().bloquear(
                    self._fuente, origen, segundos, motivo="maxlag")
                raise FandomMaxLagError(segundos)
            if codigo in _CODIGOS_INEXISTENTE:
                return None
            logger.warning("fandom.error_api", wiki=self._host,
                           code=_codigo_seguro(codigo))
            raise FandomPayloadError(codigo)
        return data

    async def _wikitext(self, page_title: str) -> str | None:
        data = await self._api({
            "action": "query", "prop": "revisions", "rvprop": "content",
            "rvslots": "main", "titles": page_title,
        })
        if not data:
            return None
        pages = (data.get("query") or {}).get("pages") or []
        if not pages or pages[0].get("missing"):
            return None
        revisiones = pages[0].get("revisions") or []
        if not revisiones:
            return None
        contenido = (revisiones[0].get("slots") or {}).get("main", {}).get("content")
        if not isinstance(contenido, str):
            return None
        # M-1 de SecOps: el wikitext que va al parser también tiene tope.
        if len(contenido) > MAX_WIKITEXT:
            logger.warning("fandom.wikitext_demasiado_grande", wiki=self._host,
                           page=page_title, caracteres=len(contenido),
                           limite=MAX_WIKITEXT)
            return None
        return contenido

    async def _displaytitle(self, page_title: str) -> str | None:
        data = await self._api({"action": "parse", "page": page_title,
                                "prop": "displaytitle"})
        if not data:
            return None
        return (data.get("parse") or {}).get("displaytitle")

    async def _url_de_imagen(self, nombre: str | None) -> str | None:
        if not nombre:
            return None
        data = await self._api({
            "action": "query", "prop": "imageinfo", "iiprop": "url",
            "titles": f"File:{nombre}",
        })
        if not data:
            return None
        pages = (data.get("query") or {}).get("pages") or []
        if not pages or pages[0].get("missing"):
            return None
        info = (pages[0].get("imageinfo") or [])
        return (info[0].get("url") if info else None) or None

    # ── API pública ────────────────────────────────────────────────────────────────────────────
    async def search_series(self, titulo: str, limit: int = 10) -> list[str]:
        """Títulos de página que la wiki devuelve para una búsqueda (sin filtrar)."""
        data = await self._api({
            "action": "query", "list": "search", "srsearch": titulo,
            "srlimit": str(max(1, min(50, limit))),
        })
        if not data:
            return []
        return [s["title"] for s in (data.get("query") or {}).get("search") or []
                if isinstance(s, dict) and s.get("title")]

    async def get_volume(self, page_title: str,
                         incluir_portada: bool = True) -> FandomVolume | None:
        """Ficha de serie. DC: plantilla + arcos + portada; Marvel: años del displaytitle.

        `incluir_portada=False` evita la consulta `imageinfo` cuando la serie ya tiene portada:
        es tráfico que no hace falta y la cortesía de la wiki es costosa (§5.10 del estudio).
        """
        wikitext = await self._wikitext(page_title)
        if wikitext is None:
            return None
        prefijo = _PLANTILLAS[self._host]["volume"]
        plantilla = extraer_plantilla(wikitext, prefijo)
        if plantilla is None:
            logger.info("fandom.volume_sin_plantilla", wiki=self._host, page=page_title)
            return None
        parametros = parametros_de_plantilla(plantilla)

        inicio = _anio(parametros.get("startyear"))
        fin = _anio(parametros.get("endyear"))
        if inicio is None and fin is None:
            inicio, fin = anios_de_displaytitle(await self._displaytitle(page_title))

        cover = None
        if incluir_portada:
            cover = await self._url_de_imagen(
                nombre_de_imagen(parametros, ("issueimage", "image")))

        if self._host == "dc.fandom.com":
            arcos = enlaces_de_pagina(parametros.get("storyarcs"))
        else:
            # Marvel Database: la plantilla de volumen no declara StoryArcs.
            arcos = []

        return FandomVolume(
            page_title=page_title,
            title=titulo_base(page_title),
            start_year=inicio,
            end_year=fin,
            total_issues=_entero(parametros.get("totalissues")),
            kind=limpiar_markup(parametros.get("type") or parametros.get("format")) or None,
            description=primer_parrafo(wikitext),
            cover_url=cover,
            story_arcs=arcos,
        )

    async def get_issue(self, page_title: str) -> FandomIssue | None:
        """Ficha de número: fecha, sinopsis, créditos y portada."""
        wikitext = await self._wikitext(page_title)
        if wikitext is None:
            return None
        prefijo = _PLANTILLAS[self._host]["comic"]
        plantilla = extraer_plantilla(wikitext, prefijo)
        if plantilla is None:
            logger.info("fandom.issue_sin_plantilla", wiki=self._host, page=page_title)
            return None
        parametros = parametros_de_plantilla(plantilla)

        if self._host == "marvel.fandom.com":
            fecha = fecha_inglesa(parametros.get("releasedate"))
        else:
            fecha = fecha_de_parametros(parametros)

        cover = await self._url_de_imagen(
            nombre_de_imagen(parametros, ("image1", "image")))

        return FandomIssue(
            page_title=page_title,
            release_date=fecha,
            synopsis=limpiar_markup(parametros.get("synopsis1")) or None,
            story_title=limpiar_markup(parametros.get("storytitle1")) or None,
            cover_url=cover,
            credits=creditos_de_parametros(parametros),
        )

    async def get_arc(self, page_title: str) -> FandomArc | None:
        """Arco: descripción y números en orden de lectura (sección `Issues`)."""
        wikitext = await self._wikitext(page_title)
        if wikitext is None:
            return None
        # 1) La plantilla del arco declara sus números en `Issues` ({{c|…}}), que es la vía
        #    fiable: la página de «Batman: Year One» no tiene enlaces [[…]] en el wikitext.
        prefijo = _PLANTILLAS[self._host].get("arc")
        plantilla = extraer_plantilla(wikitext, prefijo) if prefijo else None
        issues: list[str] = []
        if plantilla is not None:
            issues = issues_de_valor_de_arc(parametros_de_plantilla(plantilla).get("issues"))
        if not issues:
            issues = enlaces_de_issues(seccion(wikitext, "Issues"))
        if not issues:
            # Respaldo: todos los enlaces a números, en orden de aparición.
            issues = enlaces_de_issues(wikitext)
        return FandomArc(
            page_title=page_title,
            title=page_title,
            description=primer_parrafo(wikitext),
            issues=issues,
        )


def _segundos_de_maxlag(respuesta: httpx.Response, error: dict) -> float:
    """Segundos del `Retry-After` de la respuesta o del `lag` del error (mínimo 5 s)."""
    try:
        segundos = float(respuesta.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        segundos = 0.0
    if segundos <= 0:
        try:
            segundos = float(error.get("lag", 0))
        except (TypeError, ValueError):
            segundos = 0.0
    return max(5.0, segundos)


def _anio(valor: str | None) -> int | None:
    if not valor:
        return None
    m = re.search(r"(19|20)\d{2}", valor)
    return int(m.group(0)) if m else None


def _entero(valor: str | None) -> int | None:
    if not valor:
        return None
    m = re.search(r"\d{1,6}", valor)
    return int(m.group(0)) if m else None
