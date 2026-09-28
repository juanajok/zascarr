# Ficha de benchmarking — fuentes de enriquecimiento on/off (B8)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Breve: el
> riesgo está en el contrato de "apagada = cero tráfico", no en la UI.

**Historia / problema observado:**
B8 — apagar una fuente de metadatos (p. ej. Tebeosfera) sin redesplegar ni
perder lo catalogado, cuando su scraping se rompe.

**Datos reales y medición de partida:**
Sin instalación todavía (B22 en espera). El enricher actual crea los tres
clientes (`ComicVineClient`/`AniListClient`/`TebeosferaClient`) en cada ciclo y
enruta por `Series.tradition` sin ningún on/off.

**Referencias consultadas (URL, versión/commit):**
- Sonarr/Radarr (indexadores por proveedor con enable/disable individual; solo
  los habilitados participan en la búsqueda). Patrón de referencia, no
  implementación — versión/commit no fijado.
- Patrón local ya existente: `prowlarr_enabled`/`transmission_enabled`/
  `amule_enabled`/`forum_enabled` en `config.py` + override en caliente D11
  (`runtime_settings.py`).

**Cómo lo resuelve cada una:**
- Sonarr/Radarr: cada indexador tiene un flag; el cliente solo se instancia y
  llama para los habilitados. Desactivar no borra historial ni caché.
- ZascArr (D11): `forum_enabled` ya hace "off = no se consulta" para descargas.

**Supuestos que NO valen en ZascArr:**
- Un indexador *Arr vive en un proceso con estado; aquí el enricher es un ciclo
  `asyncio` por request y no tiene un "servicio de fuentes" propio. El flag debe
  leerse de `get_settings()` (mutado por D11) en cada ciclo, no cachearse.

**Adoptar / adaptar / descartar:**
- **Adoptar:** flag por fuente (`comicvine_enabled`/`anilist_enabled`/
  `tebeosfera_enabled`), default `True`.
- **Adaptar:** reutilizar D11 (`OVERRIDABLE_FIELDS` + `/ui/ajustes`) — no un
  segundo sistema de ajustes.
- **Descartar:** ocultar resultados en UI en vez de cortar el tráfico (lo que
  pide B8 es **cero peticiones**, no maquillar).

**Invariantes de ZascArr:**
- Apagar no borra metadatos ya catalogados.
- No marcar el intento omitido como `enrichment_attempted_at` (no consume el
  plazo de reintento de 30 días).
- Reactivar → vuelve a ser elegible según la regla de reintento existente.

**Casos de prueba antes de implementar:**
- Fuente apagada → su cliente no se instancia ni se llama (cero tráfico) y la
  serie pendiente NO queda marcada como intentada.
- Reactivar tras una caché negativa antigua → la serie vuelve a ser elegible.
- `OVERRIDABLE_FIELDS` acepta los tres flags y `/ui/ajustes` los persiste.

**Decisión final / ADR:** no requiere ADR (no cambia arquitectura; reutiliza D11).
