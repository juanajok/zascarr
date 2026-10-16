"""Texto de Descubrir para la persona (U14, #201): lo que la web hace con lo que dice el servicio.

Tres cosas, todas de PRESENTACIÓN (no cambian lo que se firma ni lo que devuelve
`DiscoveryService`):
  · `texto_plano`: la descripción que entrega la fuente (Comic Vine: HTML) como texto;
  · `etiqueta_fuente`: «Comic Vine», no `comic_vine`;
  · `resumir`: qué fuentes respondieron y cuáles no, en llano, y la frase que anuncia el
    lector de pantalla.

Invariantes: «Ningún resultado» no se dice cuando TODAS las fuentes consultadas fallaron; «las
demás sí respondieron» solo se dice de las que dieron `ok`; una fuente apagada o sin clave no
es un fallo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from zascarr.services.discovery import (
    FUENTE_ERROR,
    FUENTE_OK,
    FUENTE_SIN_CLAVE,
    ORDEN_DE_FUENTES,
)

#: Cómo se llama cada fuente: los mismos nombres que usa el servicio en sus avisos.
ETIQUETAS = {
    "comic_vine": "Comic Vine", "anilist": "AniList", "tebeosfera": "Tebeosfera", "gcd": "GCD"}
OTRA_FUENTE = "otra fuente"

_BLOQUES = frozenset({
    "p", "br", "div", "li", "ul", "ol", "tr", "td", "th", "table", "blockquote", "section",
    "article", "h1", "h2", "h3", "h4", "h5", "h6"})
_OCULTOS = frozenset({"script", "style"})


def etiqueta_fuente(valor: str | None) -> str:
    """El nombre de la fuente; un valor que no se conoce NO se enseña (sería un identificador)."""
    return ETIQUETAS.get(str(valor or ""), OTRA_FUENTE)


class _APlano(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ocultos = 0

    def handle_starttag(self, tag, attrs):
        if tag in _OCULTOS:
            self._ocultos += 1
        elif tag in _BLOQUES:
            self.partes.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOQUES:
            self.partes.append(" ")

    def handle_endtag(self, tag):
        if tag in _OCULTOS:
            self._ocultos = max(0, self._ocultos - 1)
        elif tag in _BLOQUES:
            self.partes.append(" ")

    def handle_data(self, data):
        if not self._ocultos:
            self.partes.append(data)


_ETIQUETA_CORTADA = re.compile(r"<[^>]*$")
_ETIQUETAS = re.compile(r"<[^>]*>")


def texto_plano(crudo: str | None) -> str:
    """El HTML de la fuente como texto: sin etiquetas, sin el contenido de `script`/`style`, con las
    entidades decodificadas y los espacios colapsados. Nunca interpreta el HTML (se escapa)."""
    if not crudo:
        return ""
    p = _APlano()
    try:
        p.feed(crudo)
        p.close()
        texto = "".join(p.partes)
    except Exception:  # noqa: BLE001 — un HTML que el analizador no admite no puede tumbar la búsqueda
        texto = _ETIQUETAS.sub(" ", crudo)
    texto = " ".join(texto.split())
    return _ETIQUETA_CORTADA.sub("", texto).strip()


def enumerar(nombres: list[str]) -> str:
    """«A», «A y B», «A, B y C»."""
    if len(nombres) <= 1:
        return "".join(nombres)
    return f"{', '.join(nombres[:-1])} y {nombres[-1]}"


def fuentes_que_se_consultan(ajustes) -> list[str]:
    """Los nombres de las fuentes que una búsqueda va a consultar, en el orden fijo de siempre.
    Comic Vine encendida pero sin clave NO se consulta (el servicio la salta): no se nombra."""
    activas = {
        "comic_vine": bool(ajustes.comicvine_enabled and ajustes.comicvine_api_key),
        "anilist": bool(ajustes.anilist_enabled),
        "tebeosfera": bool(ajustes.tebeosfera_enabled),
        "gcd": bool(ajustes.gcd_enabled),
    }
    return [ETIQUETAS[f.value] for f in ORDEN_DE_FUENTES if activas[f.value]]


@dataclass(frozen=True)
class Resumen:
    #: Los avisos que se ven bajo el buscador (uno por cosa que decir).
    avisos: list[str]
    #: La frase que anuncia la región viva: el recuento y, si procede, lo que no respondió.
    anuncio: str
    #: Las fuentes que SÍ se consultaron (para decir «sin coincidencias en …»).
    consultadas: list[str]


def resumir(estados: dict[str, str], n_resultados: int) -> Resumen:
    """Qué decir tras una búsqueda: `estados` es el estado de cada fuente (`Busqueda.fuentes`)."""
    orden = [f.value for f in ORDEN_DE_FUENTES]
    consultadas = [ETIQUETAS[v] for v in orden if estados.get(v) == FUENTE_OK]
    caidas = [ETIQUETAS[v] for v in orden if estados.get(v) == FUENTE_ERROR]
    sin_clave = [ETIQUETAS[v] for v in orden if estados.get(v) == FUENTE_SIN_CLAVE]

    avisos: list[str] = []
    if caidas:
        if not consultadas:
            avisos.append(f"No respondió ninguna fuente: {enumerar(caidas)}. "
                          "Inténtalo de nuevo en un momento.")
        else:
            verbo = "No respondió" if len(caidas) == 1 else "No respondieron"
            ok = (f"Los resultados de {enumerar(consultadas)} sí se han consultado."
                  if len(consultadas) > 1
                  else f"El resultado de {consultadas[0]} sí se ha consultado.")
            avisos.append(f"{verbo} {enumerar(caidas)}. {ok}")
    for nombre in sin_clave:
        avisos.append(f"{nombre} no está configurado: añade su clave en Ajustes para "
                      "incluirlo en la búsqueda.")
    if not consultadas and not caidas and not sin_clave:
        avisos.append("No hay ninguna fuente activa: enciéndelas en Ajustes para poder buscar.")

    if n_resultados > 0:
        cabeza = "1 resultado." if n_resultados == 1 else f"{n_resultados} resultados."
    elif caidas and not consultadas:
        cabeza = "No respondió ninguna fuente."
    elif not consultadas:
        cabeza = "No se ha buscado en ninguna fuente."
    else:
        cabeza = "Ningún resultado."
    return Resumen(avisos=avisos, anuncio=" ".join([cabeza, *avisos]) if avisos else cabeza,
                   consultadas=consultadas)
