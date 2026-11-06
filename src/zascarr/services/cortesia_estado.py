"""Presentación del snapshot de cortesía (§6.1-§6.4): JSON público y filas de Estado.

El snapshot interno guarda hosts como **origen normalizado** (`https://host:puerto`, §3.2); aquí se
reduce a lo publicable y legible: nombre de host de la allowlist, nunca URL, query ni esquema/puerto
crudos (§6.6). Las fuentes se listan siempre (también apagadas); las portadas no son una fila de
Estado porque su intervalo es por host y no por fuente.

Este módulo no escribe ni consulta BD/disco/red: solo transforma el snapshot en memoria.
"""
from __future__ import annotations

import math
from urllib.parse import urlsplit

from zascarr.config import get_settings
from zascarr.utils.cortesia import NOMBRES_DE_FUENTE, cortesia_de_proceso
from zascarr.utils.url_portada import HOSTS_PERMITIDOS

#: Textos §6.3; en un solo sitio para que Estado y las pruebas no diverjan.
#: #134: escritos para El Coleccionista; la tabla y la coordinación van plegadas.
SUBTITULO = (
    "ZascArr espera un poco entre consulta y consulta para no saturar las webs de las que saca "
    "datos."
)
COORDINACION = (
    "Esta espera vale para este ZascArr. Si tienes otra copia, cada una espera por su cuenta."
)
NOTA_BLOQUEOS = (
    "Algunas webs han pedido que no les preguntemos durante un rato. ZascArr esperará y volverá a "
    "intentarlo; puede que sigan sin responder."
)
NOTA_APAGADA = "No se consulta ni se reintenta."

#: Resultados de `ultimos_intentos` en llano (códigos de un conjunto cerrado, §6.1): el código
#: HTTP no sale a pantalla; se cuenta qué pasó.
RESULTADOS = {
    "ok": "Correcto",
    "red": "Sin conexión",
    "408": "No respondió a tiempo",
    "429": "Nos pidió esperar",
    "4xx": "Rechazó la consulta",
    "5xx": "Falló",
    "redireccion": "Nos redirigió",
}


def _host_permitido(hostname: str) -> bool:
    return any(hostname == d or hostname.endswith(f".{d}") for d in HOSTS_PERMITIDOS)


def _host_publico(host: str) -> str | None:
    """Del origen interno al nombre de host de la allowlist; None si no es publicable."""
    try:
        hostname = (urlsplit(host).hostname or "").strip().lower()
    except ValueError:
        return None
    if not hostname or not _host_permitido(hostname):
        return None
    return hostname


def snapshot_publico(ajustes=None, *, servicio=None) -> dict:
    """§6.1 listo para publicar: fuentes siempre, hosts solo de la allowlist y sin origen crudo."""
    servicio = servicio or cortesia_de_proceso()
    ajustes = ajustes if ajustes is not None else get_settings()
    datos = servicio.snapshot(ajustes)
    hosts: dict[str, dict] = {}
    for host in datos.get("hosts", []):
        nombre = _host_publico(host.get("host", ""))
        if nombre is None:
            continue
        previo = hosts.get(nombre)
        if previo is None:
            hosts[nombre] = {
                "host": nombre,
                "fuentes": list(host.get("fuentes") or []),
                "intervalo_min_s": host.get("intervalo_min_s", 0.0),
                "esperando_ahora": host.get("esperando_ahora", 0),
                "siguiente_hueco_s": host.get("siguiente_hueco_s", 0.0),
                "bloqueada_hasta_s": host.get("bloqueada_hasta_s"),
            }
        else:
            previo["fuentes"] = sorted(set(previo["fuentes"]) | set(host.get("fuentes") or []))
            previo["intervalo_min_s"] = max(previo["intervalo_min_s"],
                                            host.get("intervalo_min_s", 0.0))
            previo["siguiente_hueco_s"] = max(previo["siguiente_hueco_s"],
                                              host.get("siguiente_hueco_s", 0.0))
            bloqueos = [b for b in (previo["bloqueada_hasta_s"],
                                    host.get("bloqueada_hasta_s")) if b is not None]
            previo["bloqueada_hasta_s"] = max(bloqueos) if bloqueos else None
    return {
        "coordinacion": datos.get("coordinacion", "proceso"),
        "generado": datos.get("generado"),
        "fuentes": datos.get("fuentes", []),
        "hosts": list(hosts.values()),
    }


def _segundos(valor: float) -> int:
    """Segundos hacia arriba y mínimo 1 para una espera visible («~Ns»)."""
    return max(1, math.ceil(float(valor)))


def _espera(segundos: float) -> str:
    return f"~{_segundos(segundos)} s"


def _reintento_legible(intento: dict) -> str:
    resultado = RESULTADOS.get(str(intento.get("resultado")), "—")
    return f"{resultado} hace {_espera(intento.get('hace_s', 0))}"


def _fila(fuente: dict, ajustes) -> dict:
    nombre = fuente.get("fuente")
    etiqueta = fuente.get("nombre") or NOMBRES_DE_FUENTE.get(nombre, nombre)
    habilitada = bool(fuente.get("habilitada"))
    bloqueo = fuente.get("bloqueada_hasta_s")
    if not habilitada:
        if nombre == "foro" and not getattr(ajustes, "forum_url", ""):
            estado, clase = "Sin configurar", "neutral"
        else:
            estado, clase = "Apagada", "neutral"
        proxima, en_espera = "—", "—"
    else:
        if bloqueo:
            estado, clase = f"Bloqueada temporalmente ({_espera(bloqueo)})", "warn"
        elif fuente.get("siguiente_hueco_s", 0) > 0.05:
            estado, clase = f"En espera ({_espera(fuente['siguiente_hueco_s'])})", "warn"
        else:
            estado, clase = "Disponible", "ok"
        proxima = ("Ahora" if not bloqueo and fuente.get("siguiente_hueco_s", 0) <= 0.05
                   else f"En {_espera(bloqueo or fuente['siguiente_hueco_s'])}")
        en_espera = str(fuente.get("esperando_ahora") or 0)
    intentos = fuente.get("ultimos_intentos") or []
    return {
        "fuente": etiqueta,
        "estado": estado,
        "clase": clase,
        "proxima": proxima,
        "en_espera": en_espera,
        "reintentos": _reintento_legible(intentos[0]) if intentos else "Ninguno",
        "nota_apagada": estado == "Apagada",
        "motivo_bloqueo": fuente.get("bloqueo_motivo"),
    }


def filas_cortesia(datos: dict, ajustes=None) -> dict:
    """Contexto listo para `estado.html` (§6.3). Las portadas no son fila: su ritmo es por host."""
    ajustes = ajustes if ajustes is not None else get_settings()
    filas = [_fila(f, ajustes) for f in datos.get("fuentes", []) if f.get("fuente") != "portada"]
    bloqueadas = [f["fuente"] for f in filas
                  if f["estado"].startswith("Bloqueada temporalmente")]
    return {
        "filas": filas,
        "hay_bloqueos": bool(bloqueadas),
        "fuentes_bloqueadas": bloqueadas,
        "nota_bloqueos": NOTA_BLOQUEOS,
        "subtitulo": SUBTITULO,
        "coordinacion": COORDINACION,
        "nota_apagada": NOTA_APAGADA,
    }


def _numero(valor: float) -> str:
    texto = f"{float(valor):g}"
    return texto.replace(".", ",")


def texto_politica_ajustes(ajustes=None) -> dict:
    """§6.4: la línea de política con los valores de `config.py`, no escritos a mano."""
    ajustes = ajustes if ajustes is not None else get_settings()
    linea = (
        f"Cortesía: Comic Vine {_numero(ajustes.comicvine_rate_limit)} s y 3 intentos; "
        f"AniList {_numero(ajustes.anilist_rate_limit)} s y 3; Tebeosfera 2,5 s y 1; "
        f"GCD {_numero(ajustes.gcd_rate_limit)} s y 2. Las portadas se descargan al ritmo del "
        "sitio del que vienen y no se reintentan."
    )
    apagadas = [
        NOMBRES_DE_FUENTE[f] for f, atributo in (
            ("comicvine", "comicvine_enabled"), ("anilist", "anilist_enabled"),
            ("tebeosfera", "tebeosfera_enabled"), ("gcd", "gcd_enabled"),
        ) if not getattr(ajustes, atributo, False)
    ]
    return {
        "politica": linea,
        "coordinacion": COORDINACION,
        "apagadas": apagadas,
        "nota_apagada": NOTA_APAGADA,
    }
