# Fixtures de Comic Book Herald (SCR5)

Recortes del feed RSS 2.0 real de
`https://www.comicbookherald.com/category/reading-orders/feed/`
(verificado en vivo el 2026-11-14, 10 guías, UTF-8).

- `feed_reading_orders.xml`: 12 items (para probar el tope de 10), títulos con tildes/ñ,
  `pubDate` RFC822 y categorías; incluye `description` con prosa que NO debe leerse.
- `feed_urls_no_permitidas.xml`: enlaces fuera de la allowlist, HTTP plano, credenciales y
  un item sin título; solo el primero es válido.
- `feed_xml_roto.xml` y `feed_xxe.xml`: XML inválido y entidad externa (XXE); el parser
  seguro debe devolver `[]` sin tocar la red ni el disco.
