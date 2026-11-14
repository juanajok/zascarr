# ADR 0019: Relleno de huecos con GCD, Metron y Open Library (enricher secundario)

- **Estado:** **Aceptado** · 2026-11-14. El PO pidió **SCR7** (issue #736) y aceptó el **ADR 0018** (caché HTTP y fuentes
  externas) la misma jornada; esta redacción fija las condiciones que ya se le presentaron en la historia.
- **Relacionado:** [ADR 0002](0002-enricher-scope.md) (alcance del enricher, hoy superado en parte), [ADR 0013](0013-fuentes-de-metadatos-apagadas-por-defecto.md)
  (fuentes apagadas por defecto), [ADR 0018](0018-cache-http-y-fuentes-externas-lectura.md) (caché y fuentes nuevas), `LEGAL.md` §4/§7,
  CLAUDE.md §3.1.5 (decisión → ADR), §5 (legal) y §12 (IDs en columnas paralelas).

## Contexto

ADR 0002 cerró el alcance del enricher en Comic Vine, AniList y Tebeosfera, y dejó GCD fuera; después, la actualización de 2026-09-25
y la épica SCR añadieron GCD, Metron y Open Library **solo para Descubrir** (`/ui/descubrir`): dan de alta una `Series` con su
identificador (`gcd_id`, `metron_id`, `open_library_id`) pero no completan fichas ya catalogadas. Las tres columnas existen en el
modelo desde entonces y el alta guarda el id y el `metadata_source` de origen.

El PO quiere que esos identificadores ya guardados **sirvan también para rellenar huecos** de la ficha (año, fin, sinopsis) sin
volver a preguntar por título ni reclamar identidad. El riesgo es claro: pisar datos del coleccionista, cambiar de fuente una serie,
confundir una obra/tomo de Open Library con una grapa, quemar la cuota anónima de GCD (30 peticiones/hora sin cifra publicada) y
mostrar datos CC BY-SA 4.0 sin atribución. ADR 0013 exige que nada de esto ocurra con una fuente apagada.

## Decisión

1. **Solo por identificador ya guardado.** El relleno pide la ficha por `gcd_id`/`metron_id`/`open_library_id`. **No** se busca por
   título: una coincidencia de título no prueba que sea la misma edición (mismo criterio que el enricher primario desde ADR 0002) y
   no se reclama identidad nueva. Si el PO quiere búsqueda por título, será otra decisión con su propio ADR.
2. **Campos cerrados y solo vacíos.** GCD: `start_year`, `end_year` (datos bibliográficos; su API de series no trae sinopsis ni
   portada, ADR 0002 actualización). Metron: `description`, `start_year`, `end_year` (sin portadas por licencia). Open Library:
   `description`, `start_year` (obras/tomos, nunca grapas). Nunca se tocan `title`, los `*_id`, `metadata_source`, `cover_url` ni
   `total_issues`, ni campos en `locked_fields`; una fila `manual` queda fuera. Un campo no vacío **no se sobrescribe jamás**.
3. **Enricher secundario, después del primario.** Se ejecuta tras la cadena Comic Vine → Fandom y solo si quedan huecos, en el orden
   **Metron → Open Library → GCD** (GCD último recurso factual). Metron exige token y tradición `american`/`fumetti` (EN/IT); Open
   Library solo si hay `open_library_id` (obra/tomo); GCD solo `american`/`british`. Tope por ciclo y fuente, cortesía por
   `politica_de` (GCD 2 s, Open Library 1 s, Metron 3 s ≈ 20/min) y un fallo transitorio corta esa fuente en el ciclo sin quemar
   cuota ni marcar la caché negativa del primario.
4. **Fuentes apagadas por defecto (ADR 0013).** Sin `*_enabled` no se instancia cliente ni se hace red; Metron sin token tampoco.
5. **Procedencia y atribución.** El relleno se registra en `metadata_["relleno"]` (fuente, id, campos, fecha, URL de ficha) sin
   migración ni cambio de modelo. La ficha muestra enlace a la fuente y licencia: GCD/Metron **CC BY-SA 4.0** y Open Library con su
   enlace y licencia vigente; ninguna portada de Metron. Se actualizan `LEGAL.md` y la nota de metadatos (el hash de la aceptación
   cambia solo). Los datos rellenados **no** se copian al `ComicInfo.xml` (LEGAL.md §7.1).
6. **Sin modelo nuevo ni migración.** Un fallo (404, rate-limit, red) no borra nada y un resultado no se repite: TTL de 30 días en
   `metadata_` para la negativa, idempotencia por campos ya llenos.

## Consecuencias

**Positivas:** los ids que el coleccionista ya eligió en Descubrir dejan de ser un callejón sin salida; el primario sigue mandando y
nadie pisa datos humanos; no hay búsqueda por título ni reclamación de identidad; el gasto de cuota queda acotado y apagable.

**Negativas/aceptadas:** las series sin id de esas fuentes no se rellenan (no hay búsqueda por título); Metron sin token y las
tradiciones fuera de EN/IT quedan como están; Open Library no aporta grapas; las descripciones de Metron/OL son texto de la fuente y
obligan a atribución visible (no se escriben en el XML). Una fila nueva en `LEGAL.md` invalida la aceptación legal anterior.

**Revisión:** si el PO pide rellenar series **sin** identificador previo (búsqueda por título), o que Metron/OL aporten portadas, se
reabre este ADR con un benchmark §13 y una decisión de producto explícita; no se implementa como añadido silencioso.
