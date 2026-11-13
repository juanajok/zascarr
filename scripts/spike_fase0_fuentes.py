"""Spike manual de Fase 0 — Verificación puntual de contenido real con httpx.

Uso manual desde el entorno del proyecto (NO ejecutar en CI):
    python scripts/spike_fase0_fuentes.py
"""
import asyncio
import httpx

USER_AGENT = "ZascArr/1.15.1 (+https://github.com/juanajok/zascarr; verificacion puntual Fase 0)"

CHECKS = [
    # 1. Fandom API: artículo real con posible redirección
    (
        "Fandom DC (parse + redirects)",
        "https://dc.fandom.com/api.php",
        {
            "action": "parse",
            "page": "Batman_Vol_1_404",
            "redirects": "1",
            "prop": "properties|images|displaytitle",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        },
    ),
    # 2. Fandom API: artículo inexistente (confirmar HTTP 200 + error.code == 'missingtitle')
    (
        "Fandom DC (missingtitle sobre HTTP 200)",
        "https://dc.fandom.com/api.php",
        {
            "action": "parse",
            "page": "Zascarr_Articulo_Inexistente_999999",
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
        },
    ),
    # 3. Reading Orders: comprobar que una guía interior no recibe 403 JS Challenge de Cloudflare
    (
        "Comic Book Reading Orders (sitemap_index.xml)",
        "https://comicbookreadingorders.com/sitemap_index.xml",
        None,
    ),
    # robots.txt declara sitemap.xml (no sitemap_index.xml): se comprueban ambos
    (
        "Comic Book Reading Orders (sitemap.xml)",
        "https://comicbookreadingorders.com/sitemap.xml",
        None,
    ),
    (
        "Comic Book Reading Orders (guía interior)",
        "https://comicbookreadingorders.com/dc/events/crisis-on-infinite-earths-reading-order/",
        None,
    ),
    # 4. Continuity Guide: comprobar página interior HTML normal (SIN ?format=json)
    (
        "Continuity Guide (página interior)",
        "https://www.continuityguide.net/planet-x",
        None,
    ),
    # 5. Comic Book Herald: comprobar si /feed/ también está bloqueado por WAF (403)
    (
        "Comic Book Herald (RSS /feed/)",
        "https://www.comicbookherald.com/feed/",
        None,
    ),
]


async def main() -> None:
    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        for nombre, url, params in CHECKS:
            try:
                r = await client.get(url, params=params)
                ct = r.headers.get("content-type", "-")
                etag = r.headers.get("etag", "-")
                lm = r.headers.get("last-modified", "-")
                extra = ""
                if "application/json" in ct:
                    payload = r.json()
                    if "error" in payload:
                        extra = f" | mw_error={payload['error'].get('code')}"
                    elif "parse" in payload:
                        extra = f" | title={payload['parse'].get('displaytitle')}"
                print(
                    f"[{r.status_code}] {nombre}\n"
                    f"      CT={ct} | bytes={len(r.content)} | ETag={etag} | LM={lm}{extra}"
                )
            except httpx.HTTPError as exc:
                print(f"[ERR] {nombre}: {type(exc).__name__}")
            await asyncio.sleep(2.5)


if __name__ == "__main__":
    asyncio.run(main())
