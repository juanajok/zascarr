# ADR 0002: Alcance del enricher en 1.0 — cierre formal de B4

- Estado: **Aceptado** · 2026-09-23
- Relacionado: ADR-0001 (stack UI), BACKLOG §B4

## Contexto

B4 pedía un enricher multi-fuente para que cada tebeo aparezca con portada,
guionista, dibujante y sinopsis. Durante su construcción el alcance real se
materializó así:

- **Comic Vine** (`services/comic_vine.py`) — tradiciones `american` y
  `british`. Enriquece serie **e issues** (única fuente con concepto de
  issue completo en este sistema).
- **AniList** (`services/anilist.py`) — `manga`, `manhwa`, `manhua`.
  Enriquece solo a nivel de serie (título, sinopsis, portada, nº total).
- **Tebeosfera** (`services/tebeosfera.py`) — `tebeo` y `franco_belgian`.
  Scraping cortés de los endpoints AJAX del buscador, verificado en vivo.
  Solo nivel de serie; rate limit más conservador que las demás por ser una
  asociación cultural sin ánimo de lucro.
- **GCD (Grand Comics Database)** — pensada para `fumetti` y BD antigua.
  **No implementada**: sin API pública madura ni referencia de scraping
  validada (a diferencia de Tebeosfera, que ya tenía
  `theotocopulitos/tebeosfera-scraper` como referencia).

El resultado cubre **7 de las 9 tradiciones** del modelo: `american`/`british`
(Comic Vine), `manga`/`manhwa`/`manhua` (AniList) y `tebeo`/`franco_belgian`
(Tebeosfera). Quedan sin fuente **dos**: `fumetti` (el hueco real, pospuesto
a GCD) y `other` (cajón de sastre que, por definición, no se enriquece desde
una fuente externa).

## Decisión

1. **B4 se declara cerrada** con el alcance CV + AniList + Tebeosfera. No es
   un recorte pendiente: es el alcance de 1.0.
2. **GCD queda pospuesta a post-1.0** con estrategia ya decidida: mirror
   local de los dumps públicos de GCD, nunca API en vivo (no existe una que
   podamos respetar con rate limit cortés, y montar scraping ciego contra una
   base de datos protegida por derecho *sui generis* (Directiva 96/9/CE) es
   exactamente el riesgo que `LEGAL.md` prohíbe sin verificar términos).
3. **El sistema de fuentes es extensible por diseño**: `EnrichmentService`
   enruta por `Series.tradition`, y añadir una cuarta fuente es un fichero
   nuevo en `services/` + una entrada en el mapa de routing — no requiere
   tocar el core. El día que llegue GCD (o cualquier otra), el encaje ya
   está pagado.
4. **Las series sin fuente no son errores**: se marcan
   `enrichment_attempted_at` (mismo patrón de caché negativa que H2), de modo
   que no se re-seleccionan en cada ciclo ni acaparan el lote. Un fumetti sin
   enricher es una serie más honesta que inventar datos.

## Consecuencias

**Positivas:**
- 1.0 puede cortarse: ninguna tradición queda sin una estrategia.
- El coleccionista ve el hueco como dato ("sin enriquecer aún"), no como
  error.
- El pipeline queda preparado para añadir GCD o futuras fuentes sin deuda
  arquitectónica.

**Negativas (aceptadas):**
- Fumetti (y `other`) sin portada/sinopsis automática en 1.0. El coleccionista
  con mucho fumetti lo notará; mitigación: la cascada de portadas de C1
  (primera página del CBZ) cubre la mayoría de casos sin metadatos.
- Si Comic Vine cambia su API o política, `american`/`british` quedan
  degradados: B8 (toggle por proveedor) mitiga el riesgo operativo.

## Cuándo se revisa esta decisión

- Cuando exista un mirror local de GCD listo para consumir, o
- cuando un usuario reporte que fumetti sin enriquecer le impide el uso
  normal del producto.

No se reabre por presión de completitud: 7/9 con fuentes honestas (y las dos
restantes con estrategia explícita) es mejor producto que 9/9 con una fuente
ilegalmente scrapeada.

---

*Segundo ADR del repo. Recuperar los anteriores (PostgreSQL, routing del
enricher) queda fuera de este documento, igual que en ADR-0001.*
