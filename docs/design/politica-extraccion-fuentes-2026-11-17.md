# Dictamen OCTA-E4 — extracción de fichas y derecho *sui generis*

- **Estado:** dictamen del PO (2026-11-17), pendiente de revisión jurídica externa si el repo
  sigue público.
- **Historia:** [#939](https://github.com/juanajok/zascarr/issues/939), épica OCTA-E [#918](https://github.com/juanajok/zascarr/issues/918).
- **Cambio de código:** política y texto legal; sin extracción nueva.

## Regla general

ZascArr puede **consultar datos factuales** de una fuente que el usuario active, para su uso
privado, pero **no extrae ni redistribuye bases de datos**. Se entiende por dato factual:
título, año, editorial, número, créditos, fecha, identificadores y enlace a la ficha. Quedan
fuera la prosa creativa, las sinopsis, las reseñas y los volcados masivos.

## Por fuente

| Fuente | Uso permitido | Límite |
|---|---|---|
| **Tebeosfera** | Metadatos factuales para uso personal; sin portadas (OCTA-E5) | Base protegida por *sui generis*: sin extractos masivos, sin volcados, sin redistribución; permiso explícito para reutilizar |
| **Whakoom** | Texto CC-BY-SA con atribución | Atribución; portadas editoriales no incluidas; sin redistribución masiva |
| **Comic Vine / AniList** | API conforme a sus términos, caché local | Sin redistribución masiva ni publicación de volcados |
| **GCD** | CC BY-SA 4.0; consulta puntual | Atribución y enlace; sin redistribución masiva |
| **Metron** | Datos bibliográficos y descripción para huecos por id | Sin portadas, sin búsqueda masiva, sin redistribuir textos |
| **Open Library** | Obras/tomos ya identificados por id | Sin portadas en el relleno, sin redistribución |
| **Fandom (DC/Marvel Database)** | Texto CC-BY-SA 3.0 con atribución | Portadas © fuera de esa licencia; no se presentan como CC-BY-SA; sin redistribución de textos/fichas |
| **Comic Book Herald / Continuity Guide** | Solo referencias fácticas de lectura | Sin prosa, sin portadas, con enlace de atribución |

## Lo que no se hará

- Publicar un dump, CSV completo o base pre-poblada con fichas de terceros.
- Incluir capturas públicas con fichas extraídas o portadas comerciales (E2/E6).
- Copiar sinopsis creativas al `ComicInfo.xml` (ya decidido el 2026-11-10).
- Usar estas fuentes para entrenar modelos o redistribuir sus datos.

## Consecuencia

No hace falta una feature de extracción nueva. Si en el futuro se plantea exportar fichas, será
una decisión aparte con revisión jurídica y, probablemente, permiso de la fuente.
