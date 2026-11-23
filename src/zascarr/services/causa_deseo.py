# ruff: noqa: E501
"""Qué bloquea un deseo y qué se puede hacer (UXA-13a, #1130). Funciones puras, sin BD ni red.

El orquestador deja en `Wishlist.last_error` un motivo en español (D9). Aquí se clasifica en las cuatro
causas que la persona necesita distinguir y se le dice **qué hacer y adónde ir**:

- **Sin configurar**: falta una fuente o un cliente de descarga; se arregla en Ajustes.
- **En espera**: el foro o una fuente pidió esperar; se reintenta sola, no hay que hacer nada.
- **Falló**: algo no respondió o falló al enviar; se puede reintentar.
- **Sin resultados**: se buscó y no hay nada utilizable; no es un fallo de ZascArr.

Un motivo que no se reconoce **no se clasifica** (`None`): se muestra tal cual, no se inventa una causa."""
from __future__ import annotations

from dataclasses import dataclass

from zascarr.services import orchestrator as o

AJUSTES = "/ui/ajustes"
#: Destinos estables de Ajustes (UXA-14, #1131): el `id` de cada tarjeta; `test_ajustes_anclas` los comprueba.
DESCARGAS = AJUSTES + "#ajustes-descargas"
PROWLARR = AJUSTES + "#ajustes-prowlarr"
TRANSMISSION = AJUSTES + "#ajustes-transmission"
AMULE = AJUSTES + "#ajustes-amule"
PENDIENTES = "/ui/pendientes"


@dataclass(frozen=True)
class CausaDeDeseo:
    tipo: str            # sin_configurar | en_espera | fallo | sin_resultados
    etiqueta: str        # lo que ve la persona
    aspecto: str         # aspecto de `ui.chip`
    accion: str          # qué puede hacer (frase corta)
    destino: str | None = None   # a dónde ir a configurarlo
    enlace: str | None = None    # texto del enlace al destino


def _sin_configurar(accion: str, destino: str = DESCARGAS) -> CausaDeDeseo:
    return CausaDeDeseo("sin_configurar", "Sin configurar", "amber", accion, destino, "Ir a Ajustes")


def _en_espera(accion: str = "No hace falta hacer nada: se reintenta sola.") -> CausaDeDeseo:
    return CausaDeDeseo("en_espera", "En espera", "info", accion)


def _fallo(accion: str, destino: str | None = None, enlace: str | None = None) -> CausaDeDeseo:
    return CausaDeDeseo("fallo", "Ha fallado", "warn", accion, destino, enlace)


def _sin_resultados(accion: str, destino: str | None = None, enlace: str | None = None) -> CausaDeDeseo:
    return CausaDeDeseo("sin_resultados", "Sin resultados", "neutro", accion, destino, enlace)


_POR_MOTIVO: dict[str, CausaDeDeseo] = {
    o.MOTIVO_SIN_FUENTE: _sin_configurar(
        "Enciende Prowlarr, el foro o un blog/RSS para que pueda buscar."),
    o.MOTIVO_PROWlARR_CONFIGURACION: _sin_configurar(
        "Completa la URL y la clave de Prowlarr.", PROWLARR),
    o.MOTIVO_CANDIDATO_RECHAZADO: _sin_configurar(
        "Se encontró algo, pero falta un cliente de descarga: enciende Transmission o aMule."),
    o.MOTIVO_FORO_ESPERA: _en_espera(),
    o.MOTIVO_ESPERA_CON_DESCARTES: _en_espera(),
    o.MOTIVO_FUENTE_INACCESIBLE: _en_espera("No hace falta hacer nada: se reintenta sola."),
    o.MOTIVO_CLIENTE_INACCESIBLE: _fallo(
        "Comprueba que tu cliente de descarga esté encendido y alcanzable.", DESCARGAS, "Ir a Ajustes"),
    o.MOTIVO_TRANSMISSION_INACCESIBLE: _fallo(
        "Comprueba que Transmission esté encendido y que la URL de Ajustes sea correcta.",
        TRANSMISSION, "Ir a Ajustes"),
    o.MOTIVO_AMULE_INACCESIBLE: _fallo(
        "Comprueba que aMule esté encendido y que la URL de Ajustes sea correcta.",
        AMULE, "Ir a Ajustes"),
    o.MOTIVO_ERROR_INESPERADO: _fallo("Pulsa «Reintentar»; si se repite, mira Estado.", "/estado", "Ver Estado"),
    o.MOTIVO_CANDIDATO_INVALIDO: _fallo("Pulsa «Buscar ahora» y elige uno de la lista nueva."),
    o.MOTIVO_SIN_RESULTADOS: _sin_resultados(
        "Prueba «Buscar ahora» para ver las opciones, o enciende otra fuente.", DESCARGAS, "Ver las fuentes"),
    o.MOTIVO_NUMERO_DISTINTO: _sin_resultados(
        "Si el release usa otro nombre para la serie, importa un fichero y asígnalo una vez.",
        PENDIENTES, "Ir a Por revisar"),
}


def causa_de_motivo(motivo: str | None) -> CausaDeDeseo | None:
    """La causa de un motivo guardado, o `None` si no hay motivo o no se reconoce."""
    if not motivo:
        return None
    return _POR_MOTIVO.get(motivo)


def cliente_de_descarga(url: str) -> str:
    """A qué cliente irá un candidato, según su enlace (misma regla que el orquestador, solo para decirlo)."""
    return "aMule" if (url or "").startswith("ed2k://") else "Transmission"
