"""
Extracción de portada bajo demanda — B2 (miniaturas en la bandeja de
pendientes). No reutiliza triage(): esta solo necesita los bytes de la
primera página redimensionados para una miniatura, no todo el triaje
(SHA256, ComicInfo.xml, etc.), que ya se hizo una vez al importar.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image

from secuenciarr.core.importer_triage import IMAGE_EXTS, natural_key

# Ancho de miniatura razonable para una tarjeta de revisión; no la portada
# a tamaño completo (esto se sirve muchas veces mientras la bandeja está
# abierta, y el dispositivo es una Pi).
_THUMB_MAX_WIDTH = 240


def extract_cover_thumbnail(path: Path) -> tuple[bytes, str] | None:
    """(bytes JPEG, content-type) de una miniatura de la primera página en
    orden natural, o None si el archivo no es un zip legible o no tiene
    páginas de imagen (CBR, por ejemplo: requeriría unrar, fuera de
    alcance — ver importer_triage.py)."""
    if path.suffix.lower() not in {".cbz", ".zip"} or not path.exists():
        return None

    try:
        with zipfile.ZipFile(path) as zf:
            pages = sorted(
                (n for n in zf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS),
                key=natural_key,
            )
            if not pages:
                return None
            data = zf.read(pages[0])
    except (OSError, zipfile.BadZipFile):
        return None

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.thumbnail((_THUMB_MAX_WIDTH, _THUMB_MAX_WIDTH * 2))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            return buf.getvalue(), "image/jpeg"
    except Exception:
        # Pillow no pudo decodificar la imagen: mejor sin miniatura que
        # un error que tumbe la carga de toda la bandeja.
        return None
