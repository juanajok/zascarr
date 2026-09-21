"""Alias para compatibilidad. La implementación canónica está en core/importer_triage.py."""
from secuenciarr.core.importer_triage import ComicInfo, parse_comic_info, triage

__all__ = ["ComicInfo", "parse_comic_info", "triage"]
