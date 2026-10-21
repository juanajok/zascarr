# U15 — Resultados reales de las 20 búsquedas (2026-10-21)

- **Fecha:** 2026-10-21T13:12:56+00:00
- **Commit de producto:** `8589b47`
- **Commit de la rama de evidencia:** `b540726`
- **Límite por fuente:** 3 resultados
- **Fuentes consultadas de verdad:** GCD y Tebeosfera.
- **No disponibles:** AniList (403, API deshabilitada temporalmente) y Comic Vine (sin API key).

> Esta medición **no incluye Comic Vine ni AniList**. Por tanto, no mide la sugerencia
> «Grapa americana» de Comic Vine que originó U15; mide las otras dos fuentes y deja
> las dos que faltan como NOT RUN. No se ha usado la app ni la base de datos.

## Resultado por título

| Título | Referencia | GCD (1.º) | ¿Coincide? | Tebeosfera (1.º) | ¿Coincide? |
|---|---|---|---|---|---|
| Mortadelo y Filemón | tebeo | Mortadelo y Filemón (tebeo) | sí | ALEGRES HISTORIETAS (tebeo) | sí |
| Zipi y Zape | tebeo | Super Humor Zipi y Zape (tebeo) | sí | COMIC ZETA (tebeo) | sí |
| El Capitán Trueno | tebeo | El Capitán Trueno (tebeo) | sí | AMBRÓS, MUESTRARIO DE LÁMINAS (tebeo) | sí |
| El Jabato | tebeo | El Jabato (tebeo) | sí | ANTONIO BERNAL (tebeo) | sí |
| Superlópez | tebeo | sin resultados | sin resultados | COMIC SUPER AVENTURAS (tebeo) | sí |
| Anacleto, agente secreto | tebeo | sin resultados | sin resultados | ANACLETO, AGENTE SECRETO (tebeo) | sí |
| 13, Rue del Percebe | tebeo | sin resultados | sin resultados | 13 RUE DEL PERCEBE (tebeo) | sí |
| Carpanta | tebeo | Super Carpanta (tebeo) | sí | CARPANTA (tebeo) | sí |
| Astérix el Galo | franco_belgian | sin resultados | sin resultados | ASTERIX O GALO (tebeo) | NO |
| Las aventuras de Tintín | franco_belgian | Las Aventuras de Tintín (tebeo) | NO | TINTIN (tebeo) | NO |
| Lucky Luke | franco_belgian | Les aventures de Lucky Luke d'après Morris (franco_belgian) | sí | LUCKY LUKE (tebeo) | NO |
| Thorgal | franco_belgian | Les mondes de Thorgal  - Kriss de Valnor - La collection (franco_belgian) | sí | THORGAL (tebeo) | NO |
| Batman | american | 3-D Batman (american) | sí | ACADEMIA GOTHAM (tebeo) | NO |
| Spider-Man | american | 100% Marvel : Spider-Man (franco_belgian) | NO | BACKLASH / SPIDERMAN (tebeo) | NO |
| Watchmen | american | Absolute Watchmen (american) | sí | WATCHMEN (tebeo) | NO |
| The Sandman | american | DCE Essentials: The Sandman (american) | sí | CORINTIO, EL (tebeo) | NO |
| Dragon Ball | manga | Dragon Ball (franco_belgian) | NO | BATMAN (tebeo) | NO |
| One Piece | manga | One Piece (other) | NO | ONE PIECE (tebeo) | NO |
| Naruto | manga | Boruto - Naruto next Generation (other) | NO | BORUTO (tebeo) | NO |
| Akira | manga | Akira (american) | NO | AKIRA (tebeo) | NO |

## Recuento descriptivo (primer resultado de cada fuente)

- **gcd:** 10/16 coincidencias; 4 sin resultados.
- **tebeosfera:** 8/20 coincidencias; 0 sin resultados.

## Lectura

- **Tebeosfera** devolvió **20/20** resultados con la constante `tebeo` (no es un valor leído de cada ficha: el
  cliente de producto la asigna por diseño). Sus 8 «coincidencias» son exactamente los 8 títulos cuya referencia
  es `tebeo`; no son 8 aciertos de búsqueda. El primer resultado a veces es otra obra (p. ej. *Mortadelo* →
  *ALEGRES HISTORIETAS*), así que tampoco se puede leer como «encontró el título».
- **GCD** acertó 10 de 16 consultas con resultados. Las 6 discrepancias no son aleatorias: Tintín sale `tebeo` por
  una edición española; Spider-Man y Dragon Ball salen `franco_belgian` por ediciones francesas; One Piece y Naruto
  salen `other`; Akira sale `american`. La sugerencia describe la **edición que GCD devolvió**, no la obra.
- **Comic Vine y AniList no se midieron.** La conclusión sobre Comic Vine sigue apoyada en el código
  (`ComicTradition.AMERICAN` para cualquier resultado) y en la auditoría de *Mortadelo*, no en esta tabla.

## Límites

- Solo se evalúa el **primer resultado** de cada fuente; la app muestra varios y la
  persona elige. El recuento es descriptivo, no una tasa de acierto del producto.
- **Tebeosfera no devuelve una tradición por resultado.** `buscar_20.py` escribe la constante
  `ComicTradition.TEBEO.value` («tebeo») para todos porque el cliente de producto asigna `TEBEO` a cualquier
  resultado de esa fuente. El 20/20 no es una clasificación leída de cada ficha: describe el diseño del cliente.
  GCD sí asigna según idioma/país de la edición devuelta.
- La referencia de tradición de `titulos.json` es provisional y no está verificada
  contra un catálogo externo.
- No se ha medido Comic Vine, que es la fuente del caso Mortadelo, ni AniList.

