# Anexo — Propuesta externa de etiquetas pegada por el PO (2026-11-04)

> **Estado:** documento de TRABAJO, no aprobado. Recoge la propuesta externa tal
> como la pegó el PO (dos mensajes casi idénticos, resumidos aquí sin añadir
> afirmaciones) para que benchmark, especificación, UI y seguridad la contrasten
> contra el código vigente. Ninguna de sus afirmaciones se da por cierta: las
> que se puedan comprobar se marcan [verificado] / [incorrecto] en
> `docs/design/evaluacion-propuesta-etiquetas.md`.
>
> **Regla de interpretación:** la propuesta describe una intención de producto;
> el repo manda. Cuando la propuesta contradice el código o los ADR, se anota y
> se propone la alternativa que respeta el repo.

## 1. Decisión previa: qué NO se convierte en etiqueta

Regla citada de Hydrus: «los tags sirven para reencontrar, no para describir».
Se propone dejar como columna/relación lo que es identidad del objeto y reservar
tags para descriptores flexibles:

| Se queda estructurado | Va a tags con namespace |
|---|---|
| Tradición, editorial, año, número, estado de publicación | `genero:` (noir, superheroicos, humor) |
| Serie, número, saga (identidad) | `tema:` / `motivo:` (escuela, venganza, space opera) |
| Guionista / dibujante | `personaje:` (batman, mortadelo), pudiendo convivir con la relación existente |
| Formato físico (CBZ/CBR, páginas) | `universo:` (dc, marvel), `publico:` (infantil, adulto), `formato:` (grapa, integral, tankoubon) |

Namespaces en español sin acentos (`genero`, `tema`, `publico`) para la UI;
búsqueda insensible a acentos con `unaccent` + `pg_trgm`.

## 2. Modelo de datos propuesto (texto literal, corregido solo en el nombre de la migración)

> «Una migración Alembic más (sería la 0010) con cuatro tablas», con ids `int`
> y nombres en singular. Se transcribe para evaluar; **no es el diseño aceptado**:

```python
class Tag(Base):
    __tablename__ = "tag"
    id: Mapped[int] = mapped_column(primary_key=True)
    namespace: Mapped[str]          # genero, tema, personaje, universo, publico, formato
    name: Mapped[str]               # normalizado: "noir", "escuela"
    __table_args__ = (UniqueConstraint("namespace", "name"),)

class TagAlias(Base):               # "super-man", "superman" -> personaje:superman
    __tablename__ = "tag_alias"
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id"), primary_key=True)
    alias: Mapped[str] = mapped_column(primary_key=True)

class TagParent(Base):              # batman -> universo:dc (implicación)
    __tablename__ = "tag_parent"
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id"), primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("tag.id"), primary_key=True)

class SerieTag(Base):
    __tablename__ = "serie_tag"
    serie_id: Mapped[int] = mapped_column(ForeignKey("series.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id"), primary_key=True)
    source: Mapped[str]             # manual | comicvine | anilist | tebeosfera | comicinfo | regla
    weight: Mapped[int]             # 0-100; del rank de AniList o fijo por fuente
```

Detalles para la Pi: índice GIN trigram sobre `tag.name` para autocompletado
(reaprovechando pg_trgm) y facet counts con `COUNT(*) ... GROUP BY` sobre índice
compuesto `serie_tag(tag_id, serie_id)`; sin vistas materializadas. Alias y
padres son el mecanismo de siblings/implications de Hydrus.

## 3. Pipeline de etiquetado propuesto

- **Comic Vine:** `genres` → `genero:`; `characters` → `personaje:`.
- **AniList:** tags nativos («School Life», «Ninja») → `tema:`; su campo `rank`
  (0-100) cae en `weight`; `isAdult` alimenta `publico:adulto`.
- **Tebeosfera / Gran Catálogo:** género y argumento → `genero:` / `tema:`.
- **ComicInfo.xml del CBZ:** `<Tags>` separados por comas → tags con
  `source='comicinfo'`, importados en el ciclo del importer junto al SHA256.
- **Reglas:** mapper estilo Kavita que remapea genres↔tags y deriva age rating
  desde ambos; p. ej. «si `genero:superheroicos` y `universo:dc` →
  `tema:vigilantes`».
- **Caché negativa:** si una fuente no devuelve tags para una serie, no se
  reintenta cada ciclo (se extiende la existente de rate limits).

## 4. UX propuesta (Jinja2 + HTMX, ADR-0001)

1. `GET /api/etiquetas/sugerir?q=noi` devuelve un parcial HTML con sugerencias
   ordenadas por `similarity(name, q)` y conteo de series (autocompletado tipo
   Hydrus).
2. Barra de filtros con chips: clic = AND; `alt`-clic o prefijo
   `-tema:escuela` = exclusión (patrón Hydrus/boorus). Facet counts junto a cada
   filtro, como los smart filters de Kavita.
3. En la ficha de serie, chips coloreados por namespace y edición inline con
   `hx-post`, reutilizando el patrón de la bandeja de pendientes.
4. Exportar los tags al `<Tags>` del `ComicInfo.xml` para que Kavita los lea en
   sus filtros (la propuesta cita la integración opcional con Kavita baremetal).

## 5. Roadmap propuesto

1. **MVP:** tablas + tags manuales desde la ficha + filtrado AND/exclusión en
   biblioteca.
2. **Importación:** leer `<Tags>` de ComicInfo.xml en el importer y volcarlos
   con `source='comicinfo'`.
3. **Enriquecimiento:** mappers por fuente en el enricher, con `weight` y caché
   negativa.
4. **Taxonomía:** alias, padres e implicaciones, reglas automáticas y smart
   filters guardados.

**Consejo de calado de la propuesta:** etiquetar a nivel de **serie** por
defecto y dejar `issue_tag` para una fase posterior, porque huecos y wishlist ya
viven a nivel de número y mezclar ambos desde el día uno complica el motor de
filtros.

## 6. Afirmaciones a verificar (no se aceptan por la UI ni por el texto)

1. El repo usa FastAPI + SQLAlchemy async + PostgreSQL 15 + Jinja2/HTMX y está
   orientado a Raspberry Pi.
2. Ya existen pg_trgm, `unaccent` y una función de normalización reutilizable.
3. Ya existe un util de ComicInfo donde enchufar `<Tags>`.
4. El enricher ya es multi-fuente (Comic Vine, AniList, Tebeosfera) y tiene
   procedencia por campo.
5. El modelo ya filtra por tradición, editorial, personaje y saga.
6. El repo ya tiene integración opcional con Kavita baremetal.
7. Kavita tiene smart filters y un mapper genres↔tags; Calibre-Web usa
   typeahead sobre su tabla de tags; Hydrus tiene aliases/parents; LANraragi y
   los boorus usan el patrón de búsqueda con AND/exclusión.
8. La migración siguiente sería la 0010 y el repo va por 0001–0009.
9. AniList devuelve tags con `rank` 0-100 e `isAdult`.
10. ComicInfo define `<Tags>` como lista separada por comas y Kavita lo lee.

## 7. Límites de este anexo

- No autoriza implementación, ni migración, ni cambios de UI.
- No fija nombres de tablas, tipos de id, número de migración ni alcance de la
  primera entrega: eso lo decide la especificación tras el benchmark.
- Las citas de producto (Hydrus, Kavita, Calibre-Web, boorus) se comprueban con
  versión/commit en `docs/design/benchmark-etiquetas.md`; la barrera legal de
  `CLAUDE.md` §13 aplica (se copian patrones, nunca código, textos ni diseños).
