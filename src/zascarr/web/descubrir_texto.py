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

from dataclasses import dataclass

from zascarr.services.discovery import (
    FUENTE_ERROR,
    FUENTE_OK,
    FUENTE_SIN_CLAVE,
    ORDEN_DE_FUENTES,
)
from zascarr.utils.texto_html import (
    texto_plano,  # noqa: F401  (se reexporta: la usan Descubrir y sus pruebas)
)

#: Cómo se llama cada fuente: los mismos nombres que usa el servicio en sus avisos.
ETIQUETAS = {
    "comic_vine": "Comic Vine", "anilist": "AniList", "tebeosfera": "Tebeosfera", "gcd": "GCD"}
OTRA_FUENTE = "otra fuente"


ETIQUETAS_PROCEDENCIA = {
    "explicita": "dato explícito de la fuente",
    "transformada": "deducida de otros datos de la fuente",
    "por_defecto": "valor por defecto: la fuente no lo indica",
    "desconocida": "origen desconocido",
}


def _valor_de_procedencia(procedencia) -> str:
    return str(getattr(procedencia, "value", procedencia) or "")


def etiqueta_procedencia(procedencia: str | None) -> str:
    """Etiqueta corta para el contexto de una sugerencia ya mostrada (nunca un dato de la obra)."""
    return ETIQUETAS_PROCEDENCIA.get(
        _valor_de_procedencia(procedencia), ETIQUETAS_PROCEDENCIA["desconocida"])


def pista_de_tradicion(etiqueta: str, procedencia: str | None) -> str:
    """La frase que presenta una tradición sugerida SIN confirmarla.

    La procedencia cambia la atribución, no la recomendación: en todos los casos la persona elige y
    nada llega preseleccionado. Para `explicita` se conserva literalmente la copy de U15; para las
    demás se dice de dónde sale (transformada de otros datos, valor por defecto del producto o
    desconocida) para no presentar como clasificación de la fuente lo que no lo es. Sin
    sugerencia no se llama a esta función: no hay pista que mostrar.
    """
    inicio = {
        "explicita": f"La fuente lo clasifica como {etiqueta}.",
        "transformada": (
            f"La fuente no usa esta tradición: a partir de sus datos "
            f"se sugiere {etiqueta}."
        ),
        "por_defecto": f"La fuente no indica tradición: se sugiere {etiqueta} por defecto.",
        "desconocida": f"La fuente sugiere {etiqueta}, pero no consta de dónde sale.",
    }.get(_valor_de_procedencia(procedencia) or "desconocida",
          f"La fuente sugiere {etiqueta}, pero no consta de dónde sale.")
    return f"{inicio} Es solo una pista de la fuente, no de la obra: elige tú."


def etiqueta_fuente(valor: str | None) -> str:
    """El nombre de la fuente; un valor que no se conoce NO se enseña (sería un identificador)."""
    return ETIQUETAS.get(str(valor or ""), OTRA_FUENTE)


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
    elif not consultadas:
        cabeza = ""             # ya lo dicen los avisos («No respondió ninguna fuente…»)
    else:
        cabeza = "Ningún resultado."
    anuncio = " ".join(x for x in [cabeza, *avisos] if x)
    return Resumen(avisos=avisos, anuncio=anuncio, consultadas=consultadas)
