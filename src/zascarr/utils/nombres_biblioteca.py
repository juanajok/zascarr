"""Nombres de archivo para la biblioteca (BL-B9, #158).

Módulo puro: no toca BD, disco, configuración ni red. Los presets solo
deciden cómo se compone el nombre; el importador aplica el resultado al
destino. Un nombre sin título no añade sufijos inventados (nunca «Unknown»).
"""
from __future__ import annotations

from typing import Any

from zascarr.models import IssueFormat
from zascarr.utils.fs import sanitize_segment

#: Presets visibles en Ajustes. El padding es el valor por defecto del preset;
#: `construir_nombre(..., padding=...)` lo puede sobrescribir.
PRESETS: dict[str, dict[str, Any]] = {
    "clasico": {"padding": 3},
    "compacto": {"padding": 2},
    "tradicion": {"padding": 3},
    "titulo": {"padding": 3},
}

#: Etiqueta legible para las ediciones que no son una grapa suelta.
ETIQUETAS_FORMATO: dict[str, str] = {
    IssueFormat.TRADE_PAPERBACK.value: "Tomo",
    IssueFormat.HARDCOVER.value: "Tapa dura",
    IssueFormat.OMNIBUS.value: "Ómnibus",
    IssueFormat.GRAPHIC_NOVEL.value: "Novela gráfica",
    IssueFormat.ALBUM.value: "Álbum",
    IssueFormat.MANGA_TANKOBON.value: "Tankōbon",
    IssueFormat.DIGITAL.value: "Digital",
}

#: Cómo se escribe el número según la tradición con preset «tradicion».
_PATRON_TRADICION: dict[str, tuple[str, int]] = {
    "manga": ("v", 2),
    "franco_belgian": ("T", 2),
    "tebeo": ("nº ", 2),
}


def _titulo_de(serie: Any) -> str:
    if isinstance(serie, str):
        return serie
    return str(getattr(serie, "title", "") or "")


def _tradicion_de(serie: Any) -> str:
    if isinstance(serie, str):
        return ""
    tradicion = getattr(serie, "tradition", "") or ""
    return getattr(tradicion, "value", tradicion)


def _formato_de(formato: Any) -> str:
    if formato is None:
        return IssueFormat.SINGLE_ISSUE.value
    return getattr(formato, "value", str(formato))


def _numero_formateado(numero: Any, *, padding: int, prefijo: str) -> str:
    crudo = sanitize_segment(str(numero) if numero is not None else "").strip()
    if not crudo or crudo == "_Serie":
        return ""
    if crudo.isdigit() and padding > 0:
        crudo = crudo.zfill(padding)
    return f"{prefijo}{crudo}"


def construir_nombre(
    serie: Any,
    numero: Any,
    *,
    titulo: str | None = None,
    formato: Any = None,
    pack: bool = False,
    preset: str = "clasico",
    padding: int = 0,
) -> str:
    """Compone el nombre base (sin extensión) de un archivo de biblioteca.

    - ``preset``: clave de :data:`PRESETS`; uno desconocido cae a ``clasico``.
    - ``padding``: si es > 0, sustituye al del preset.
    - ``titulo``: título del número; con el preset ``titulo`` se añade como
      sufijo y sin él NUNCA se escribe «Unknown».
    - ``formato``: distinto de ``single_issue`` añade su etiqueta legible.
    - ``pack``: añade «(Pack)»; no inventa ningún rango de números.
    """
    preset = preset if preset in PRESETS else "clasico"
    pad = padding if padding and padding > 0 else int(PRESETS[preset]["padding"])
    nombre_serie = sanitize_segment(_titulo_de(serie))
    tradicion = _tradicion_de(serie)

    prefijo, pad_tradicion = "#", pad
    if preset == "tradicion" and tradicion in _PATRON_TRADICION:
        prefijo, pad_tradicion = _PATRON_TRADICION[tradicion]
        if not padding:
            pad_tradicion = _PATRON_TRADICION[tradicion][1]
    numero_txt = _numero_formateado(numero, padding=pad_tradicion, prefijo=prefijo)
    base = f"{nombre_serie} {numero_txt}".strip() if numero_txt else nombre_serie

    titulo_limpio = sanitize_segment(titulo).strip() if titulo else ""
    if titulo_limpio.lower() == "unknown":
        titulo_limpio = ""
    if preset == "titulo" and titulo_limpio and titulo_limpio != "_Serie":
        base = f"{base} - {titulo_limpio}"

    formato_txt = _formato_de(formato)
    if formato_txt != IssueFormat.SINGLE_ISSUE.value:
        etiqueta = ETIQUETAS_FORMATO.get(formato_txt, formato_txt.replace("_", " ").capitalize())
        base = f"{base} ({etiqueta})"
    if pack:
        base = f"{base} (Pack)"
    return sanitize_segment(base)
