"""Cliente Prowlarr REST API."""
from dataclasses import dataclass

import httpx
import structlog

from zascarr.config import get_settings

logger = structlog.get_logger()


@dataclass(frozen=True)
class IndexerProwlarr:
    id: int
    name: str
    enabled: bool
    categories: list[str]

    @property
    def relevantes(self) -> list[str]:
        """Solo las categorías que importan para este selector (cómic/libros).

        Prowlarr devuelve listas enormes y localizadas («TV, ANIME, PC, AUDIO, …»);
        pintarlas enteras convierte la tarjeta en un muro de texto.
        """
        claves = ("comic", "cómic", "book", "libro")
        vistas: list[str] = []
        for categoria in self.categories:
            texto = str(categoria).casefold()
            if any(clave in texto for clave in claves) and categoria not in vistas:
                vistas.append(categoria)
        return vistas

    @property
    def tiene_categorias_relevantes(self) -> bool:
        return bool(self.relevantes)


@dataclass
class SearchResult:
    title: str
    indexer: str
    download_url: str
    size_bytes: int
    seeders: int
    category: str
    publish_date: str | None = None


class ProwlarrClient:
    def __init__(self, transporte: httpx.AsyncBaseTransport | None = None):
        s = get_settings()
        self._base = s.prowlarr_url
        self._api_key = s.prowlarr_api_key
        self._transporte = transporte

    async def search(self, query: str, categories: list[int] | None = None,
                     indexer_ids: list[int] | None = None) -> list[SearchResult]:
        if not self._api_key:
            logger.warning("prowlarr.no_api_key")
            return []
        params: dict = {"query": query, "type": "search"}
        if categories:
            params["categories"] = categories
        if indexer_ids:
            # Lista repetida (`indexerIds=1&indexerIds=2`): el modelo List<int> de Prowlarr
            # la enlaza así. Vacío = todos los indexers activos.
            params["indexerIds"] = list(indexer_ids)
        async with httpx.AsyncClient(timeout=30.0, transport=self._transporte) as client:
            r = await client.get(f"{self._base}/api/v1/search", params=params,
                                 headers={"X-Api-Key": self._api_key})
            r.raise_for_status()
            data = r.json()
        results = [SearchResult(
            title=item.get("title", ""),
            indexer=item.get("indexer", ""),
            download_url=item.get("downloadUrl", ""),
            size_bytes=item.get("size", 0),
            seeders=item.get("seeders", 0),
            category=str(item.get("categories", [{}])[0].get("name", "")),
            publish_date=item.get("publishDate"),
        ) for item in data]
        results.sort(key=lambda r: r.seeders, reverse=True)
        return results


    async def list_indexers(self) -> list[IndexerProwlarr]:
        """Indexers que Prowlarr conoce, para elegir cuáles usa ZascArr."""
        if not self._api_key:
            raise ValueError("Falta la API key de Prowlarr")
        async with httpx.AsyncClient(timeout=15.0, transport=self._transporte) as client:
            r = await client.get(f"{self._base}/api/v1/indexer", headers={
                "X-Api-Key": self._api_key, "Accept": "application/json"})
            r.raise_for_status()
            data = r.json()
        if not isinstance(data, list):
            raise ValueError("respuesta inválida de Prowlarr")
        indexers: list[IndexerProwlarr] = []
        for item in data:
            if not isinstance(item, dict) or "id" not in item:
                continue
            categorias = []
            capacidades = item.get("capabilities") or {}
            for cat in capacidades.get("categories") or []:
                if isinstance(cat, dict) and cat.get("name"):
                    categorias.append(str(cat["name"]))
            indexers.append(IndexerProwlarr(
                id=int(item["id"]), name=str(item.get("name") or f"Indexer {item['id']}"),
                enabled=bool(item.get("enable", True)), categories=categorias))
        # Los que declaran cómic/libros primero: son los útiles para ZascArr.
        indexers.sort(key=lambda i: (
            not i.tiene_categorias_relevantes, not i.enabled, i.name.casefold()))
        return indexers
