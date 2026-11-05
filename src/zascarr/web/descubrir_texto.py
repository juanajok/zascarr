"""Texto de Descubrir para la persona (U14, #201): lo que la web hace con lo que dice el servicio.

Tres cosas, todas de PRESENTACIÓN (no cambian lo que se firma ni lo que devuelve
`DiscoveryService`):
  · `texto_plano`: la descripción que entrega la fuente (Comic Vine: HTML) como texto;
  · `etiqueta_fuente`: «Comic Vine», no `comic_vine`;
  · `resumir`: qué fuentes respondieron y cuáles no, en llano, y la frase que anuncia el
    lector de pantalla.

Invariantes: «Ningún resultado» no se dice cuando TODAS las fuentes consultadas fallaron; «las
demás sí respondieron» solo se dice de las que respondieron; una fuente apagada, sin configurar o
que ha pedido esperar no es un fallo y no se mezcla con ellos; una capacidad no verificada no se
presenta como disponible.
"""
from __future__ import annotations

from dataclasses import dataclass

from zascarr.services.discovery import (
    CAPACIDAD_BUSQUEDA,
    FUENTE_APAGADA,
    FUENTE_CONFIGURACION_INCOMPLETA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_LIMITE_DE_CORTESIA,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
    ORDEN_DE_FUENTES,
    EstadoFuente,
)
from zascarr.utils.texto_html import (
    texto_plano,  # noqa: F401  (se reexporta: la usan Descubrir y sus pruebas)
)

#: Cómo se llama cada fuente: los mismos nombres que usa el servicio en sus avisos.
ETIQUETAS = {
    "comic_vine": "Comic Vine", "anilist": "AniList", "tebeosfera": "Tebeosfera", "gcd": "GCD"}
OTRA_FUENTE = "otra fuente"

#: Capacidades verificadas por el contrato, con su nombre para la persona. Lo que no esté aquí
#: NO se presenta como disponible: sale como «capacidad no verificada».
CAPACIDADES = {CAPACIDAD_BUSQUEDA: "búsqueda"}

#: Estado del servicio → (aspecto del chip, texto corto). El conjunto es CERRADO (#133): la
#: interfaz no deduce causas; un estado que no conozca se pinta como advertencia y se dice.
ESTADOS_VISIBLES: dict[str, tuple[str, str]] = {
    FUENTE_OK: ("ok", "ha respondido"),
    FUENTE_SIN_RESULTADOS: ("neutro", "sin coincidencias"),
    FUENTE_FALLO_TRANSITORIO: ("warn", "no ha respondido ahora mismo"),
    FUENTE_CONFIGURACION_INCOMPLETA: ("amber", "sin configurar"),
    FUENTE_LIMITE_DE_CORTESIA: ("amber", "ha pedido esperar"),
    FUENTE_APAGADA: ("neutro", "apagada en Ajustes"),
}


@dataclass(frozen=True)
class FuenteVisible:
    """Una fuente preparada para pintar: nombre y capacidad en llano, estado y su explicación."""
    fuente: str
    capacidad: str
    estado: str
    chip: str
    texto: str
    motivo: str | None
    reintentar_en: int | None


def etiqueta_capacidad(valor: str) -> str:
    """El nombre de la capacidad; la que el contrato no verifique no se presenta como disponible."""
    return CAPACIDADES.get(str(valor or ""), "capacidad no verificada")


def detalles_visibles(detalles: dict[str, EstadoFuente]) -> list[FuenteVisible]:
    """Las fuentes con detalle, en el orden fijo. Las que el servicio no nombra no se inventan."""
    visibles: list[FuenteVisible] = []
    for fuente in ORDEN_DE_FUENTES:
        detalle = detalles.get(fuente.value)
        if detalle is None:
            continue
        chip, texto = ESTADOS_VISIBLES.get(detalle.estado, ("warn", "estado desconocido"))
        visibles.append(FuenteVisible(
            fuente=ETIQUETAS.get(fuente.value, OTRA_FUENTE),
            capacidad=etiqueta_capacidad(detalle.capacidad),
            estado=detalle.estado, chip=chip, texto=texto,
            motivo=detalle.motivo, reintentar_en=detalle.reintentar_en))
    return visibles


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


def resumir(estados: dict[str, str], n_resultados: int,
            detalles: dict[str, EstadoFuente] | None = None) -> Resumen:
    """Qué decir tras una búsqueda: `estados` es el estado de cada fuente (`Busqueda.fuentes`) y
    `detalles` (opcional) el contrato nuevo con capacidad, motivo y reintento.

    Los estados son el conjunto cerrado de #133. Cada cosa se dice por separado: un fallo no se
    mezcla con una fuente apagada, sin configurar o que ha pedido esperar. «Ningún resultado» solo
    se dice si alguna fuente respondió sin coincidencias; un plazo de reintento solo se menciona si
    el servicio lo trae.
    """
    detalles = detalles or {}
    orden = [f.value for f in ORDEN_DE_FUENTES]
    por_estado = {valor: estados.get(valor) for valor in orden}

    def nombres(estado: str) -> list[str]:
        return [ETIQUETAS[valor] for valor in orden if por_estado[valor] == estado]

    consultadas = [ETIQUETAS[valor] for valor in orden
                   if por_estado[valor] in (FUENTE_OK, FUENTE_SIN_RESULTADOS)]
    sin_coincidencias = nombres(FUENTE_SIN_RESULTADOS)
    fallos = nombres(FUENTE_FALLO_TRANSITORIO)
    sin_configurar = nombres(FUENTE_CONFIGURACION_INCOMPLETA)
    apagadas = nombres(FUENTE_APAGADA)
    con_limite = [valor for valor in orden if por_estado[valor] == FUENTE_LIMITE_DE_CORTESIA]

    avisos: list[str] = []
    if fallos:
        if not consultadas:
            avisos.append(f"No respondió ninguna fuente: {enumerar(fallos)}. "
                          "Inténtalo de nuevo en un momento.")
        else:
            verbo = "No respondió" if len(fallos) == 1 else "No respondieron"
            ok = (f"Los resultados de {enumerar(consultadas)} sí se han consultado."
                  if len(consultadas) > 1
                  else f"El resultado de {consultadas[0]} sí se ha consultado.")
            avisos.append(f"{verbo} {enumerar(fallos)}. {ok}")
    for nombre in sin_configurar:
        avisos.append(f"{nombre} no está configurado: añade su clave en Ajustes para "
                      "incluirlo en la búsqueda.")
    for valor in con_limite:
        nombre = ETIQUETAS[valor]
        reintento = getattr(detalles.get(valor), "reintentar_en", None)
        aviso = f"{nombre} ha pedido esperar antes de volver a consultarla."
        if reintento:
            aviso += f" Puedes reintentar en {reintento} s."
        avisos.append(aviso)
    # Una fuente apagada no es un fallo: se dice aparte, y la global solo cubre «ninguna activa».
    if apagadas and (consultadas or fallos or sin_configurar or con_limite):
        avisos.append(f"{'Apagada' if len(apagadas) == 1 else 'Apagadas'} en Ajustes: "
                      f"{enumerar(apagadas)}.")
    if not consultadas and not fallos and not sin_configurar and not con_limite:
        avisos.append("No hay ninguna fuente activa: enciéndelas en Ajustes para poder buscar.")

    if n_resultados > 0:
        cabeza = "1 resultado." if n_resultados == 1 else f"{n_resultados} resultados."
    elif sin_coincidencias:
        # Solo se afirma «no hay resultados» de una fuente que respondió sin coincidencias.
        cabeza = "Ningún resultado."
    else:
        cabeza = ""             # lo dicen los avisos (fallos, configuración, cortesía o apagadas)
    anuncio = " ".join(x for x in [cabeza, *avisos] if x)
    return Resumen(avisos=avisos, anuncio=anuncio, consultadas=consultadas)
