# Fixtures de dominio público

> Material **de dominio público** para pruebas y demos de ZascArr. No es contenido de producción ni
> se distribuye como tebeoteca. Cada página se ha descargado de Wikimedia Commons, se ha reducido
> para que el fixture sea pequeño y se ha dividido en dos páginas cuando la tira era muy alta.

| Fixture | Obra / autor | Fecha | Fuente | Licencia |
|---|---|---|---|---|
| `yellow-kid-1895-1896.cbz` | *At the Circus in Hogan's Alley* (R. F. Outcault, †1928) y *Yellow Kid* 1896-11-08 | 1895/1896 | [Commons: At the Circus](https://commons.wikimedia.org/wiki/File:At_the_Circus_in_Hogan%27s_Alley.gif) · [Commons: 1896-11-08](https://commons.wikimedia.org/wiki/File:1896-11-08_Yellow_Kid.jpg) | Dominio público (PD-old; obra publicada antes de 1931) |
| `little-nemo-1905.cbz` | *Little Nemo in Slumberland* — «giant girl» (Winsor McCay, †1934) | c. 1905 | [Commons: Little Nemo giant girl](https://commons.wikimedia.org/wiki/File:Little_Nemo_giant_girl.jpg) | Dominio público (PD-old) |
| `rarebit-fiend-1904.cbz` | *Dream of the Rarebit Fiend* 1904-12-10, primera aparición de Little Nemo (Winsor McCay, †1934) | 1904 | [Commons: Dream-of-the-Rarebit-Fiend-12-10-1904](https://commons.wikimedia.org/wiki/File:Dream-of-the-Rarebit-Fiend-12-10-1904.jpg) | Dominio público (PD US expired / PD-old) |

## Cómo se generaron

- Descarga directa de las URLs de Commons con `User-Agent` propio; sin usar imágenes de la biblioteca del PO.
- Redimensionado a 560 px de ancho, JPEG calidad 68; las tiras verticales se dividen en dos páginas.
- `ComicInfo.xml` mínimo con serie, número, año y nota de procedencia/dominio público.
- El ZIP de paquete **no se versiona** (duplicaría los bytes): los tests lo construyen en un temporal a partir de los tres CBZ.

## Límites

- La obra es de dominio público; la **marca** de un personaje es otra cosa y no se usa aquí como marca de producto.
- No se incluyen scans sin licencia clara ni obras publicadas después de 1930.
- Para demos, etiquetar siempre los datos como **ejemplo**; no mezclar con la biblioteca real.
