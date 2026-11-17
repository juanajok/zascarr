# Benchmark detallado — comunidades de escaneos, tradumaquetas y agregadores

**Fecha:** 2026-11-15
**Tipo:** benchmark de producto y curación. **No es una integración de fuentes.**
**Decisión vigente:** [decision-curacion-comunidades.md](decision-curacion-comunidades.md).

> **Método y límites.** Se parte de la lista aportada por el PO. No se han visitado
> canales de Telegram, grupos de Facebook ni foros privados, no se han abierto enlaces de
> descarga y no se ha descargado material. Las valoraciones de interfaz son **cualitativas
> y no observadas** para esas comunidades; solo CompartiComics se observó en HTML público
> ([ficha](benchmark-comparticomics.md)). **NOT RUN:** observación directa, medición de
> catálogos y validación con personas.

## 1. Marco de evaluación

Cada fuente se mira por lo que **puede enseñar a ZascArr**, no por lo que se podría scrapear:

- **Descubrimiento:** ¿cómo encuentra el coleccionista una obra?
- **Curación:** ¿hay selección, criterio, calidad o solo volumen?
- **Orden de lectura:** ¿guía cronologías, etapas o series?
- **Metadata:** autor, año, editorial, edición, idioma, procedencia.
- **Persistencia:** ¿el enlace y la ficha sobreviven?
- **Fricción:** invitación, cuestionario, grupo, cuenta, enlaces externos.
- **Legalidad:** licencia, términos, contenido de terceros.
- **Móvil:** comodidad en tableta/móvil (no medida).

## 2. Fuentes, una a una

### 2.1 Escaneos y comunidades

| Fuente | Modelo | Aporte UX/curación | Límite principal | Lección |
|---|---|---|---|---|
| **Eurocomicss** | Escaneos propios + canales especializados; cuestionario de entrada | Curación por especialidad y conversación quincenal | Alta fricción; comunidad cerrada; sin catálogo público | La entrada filtrada crea confianza, pero no es un modelo para una app self-hosted |
| **Tradumaquetas** | Traducciones fan | El idioma/adaptación es un dato de primera clase | Derechos derivados; calidad variable; sin ficha estable | El coleccionista quiere saber **edición e idioma**, no solo el título |
| **Todo Comics** | Comunidad grande en Telegram | Volumen y novedades | Sin búsqueda ni metadata; ruido | Volumen sin curación no es biblioteca |
| **AT Cómics / Novena Dimensión** | Foro + Facebook; novedades USA casi al día | Actualidad y discusión | Dependencia de redes; enlaces y catálogo dispersos | La **cadencia** importa; ZascArr puede mostrar «recientemente añadido» |
| **All New Infinity** | Facebook | Comunidad y avisos | Sin catálogo persistente | El feed social no sustituye una ficha |
| **Hijos de la Medianoche** | Facebook | Comunidad temática | Sin estructura | Los temas funcionan como colecciones, no como fuentes |
| **Cómics 9Reinos** | Facebook | Comunidad | Sin ficha ni búsqueda | Misma lección |
| **Ladrón Corps** | Blog + Facebook + Telegram | Relato editorial y selección | Canales duplicados; enlaces cambian | Una **colección** necesita descripción y criterio |
| **Outsiders** | Series exclusivas propias | Identidad y control de calidad | Requiere prueba de titularidad; no es escalable | Solo se integra contenido propio con permiso |
| **Thunderbolts Corps** | Blog + Facebook | Curación por etapas | Sin catálogo | Las **etapas** son una dimensión de navegación útil |
| **Arsenio Lupin** | Histórico de calidad, Telegram | Calidad y fondo histórico | Sin metadata formal | La calidad debe ser visible, no supuesta |
| **Mr Hyde Cómics** | Facebook | Comunidad | Sin persistencia | — |
| **Jezzycomics** | Facebook | Comunidad | Sin persistencia | — |
| **Tierra de Larabeau** | Blog; recopila del CRG y sube a Mega | Volumen y recopilación | Enlaces Mega, caducidad, procedencia opaca | Enlaces externos = rotura y falta de trazabilidad |

### 2.2 Canales de Telegram

| Fuente | Aporte | Límite | Lección |
|---|---|---|---|
| **Los Archivos de Nolan** | Comicteca en crecimiento | Sin catálogo estructurado | Crecimiento sin índice no escala |
| **Nippur HA** | Grupo organizado | Depende de la comunidad y del canal | La organización es la diferencia |
| **Comicteca de Milhietus / Galatea** | Contenido masivo y variado | Volumen sin metadata | La masa no sustituye la búsqueda |
| **Hijos de la Malebolgia** | Spawn, argentino, clásicos | Nicho y dispersión | Los nichos se modelan mejor como etiquetas/colecciones |
| **Arkham Cómics** | Selección cuidada | Sin ficha persistente | La curaduría explícita genera confianza |
| **La Fortaleza del Cómic** | Comunidad | Sin estructura | — |
| **Todo Tebeos** | Material antiguo y Novaro | Catálogo histórico sin normalizar | El fondo antiguo necesita año/editorial/etapa |
| **CEC Cómics** | Comunidad | Sin catálogo | — |
| **Proyectos DC Post-Crisis** | Guías cronológicas de Superman, Batman y Green Lantern | Solo una franquicia; enlaces aparte | **El mejor patrón transferible:** orden de lectura explícito |
| **Condorito** | Dedicado a una serie | Monotema | Un universo puede ser una colección, no una fuente |
| **GIF-Land Comics** | Comunidad | Sin estructura | — |
| **La cueva del Cómic** | Comunidad | Sin estructura | — |
| **Comicverso** | Comunidad | Sin estructura | — |
| **El Bodegón Comiquero** | Blog + Instagram | Descubrimiento visual | El blog cura, la red social dispersa |

### 2.3 Otros idiomas y agregadores

| Fuente | Idioma/modelo | Aporte | Límite | Lección |
|---|---|---|---|---|
| **Getcomics** | Inglés; web de descargas | Búsqueda y volumen | Legalidad, enlaces externos | El buscador debe ser global, no por canal |
| **EmuleBDZ** | Francés; eMule + Telegram 9Art | Catálogo P2P grande | Sin API, disponibilidad variable | La disponibilidad no es una ficha |
| **Archivio dei Fumetti** | Italiano; Telegram | Volumen histórico | Sin metadata | El fondo histórico requiere normalización |
| **Mh comics +18** | Adultos | Nicho explícito | Fuera de alcance | No se integra |
| **Nona Art** | Portugués/varios; Telegram + BDteca/Cómics na-web | Variedad idiomática | Dispersión y enlaces | El **idioma** es una faceta, no un detalle |
| **Comic Mafia** | Alemán; web | Catálogo | Legalidad | — |
| **BD Telegram** | Francés/belga/manga; @BD_fr, @BD_FrBe, @BD_Mangas | Comunidad lingüística | Sin catálogo | La comunidad de idioma no es una API |

## 3. Patrones transversales

1. **Curaduría > volumen.** Las fuentes recordadas son las que seleccionan (Arkham, Arsenio, Eurocomicss), no las que solo acumulan.
2. **El orden de lectura es el activo más valioso.** Las cronologías DC Post-Crisis son el único contenido que un coleccionista usaría aunque no descargara nada.
3. **Telegram es distribución, no catálogo.** Gana en móvil e inmediatez; pierde en búsqueda, metadata, orden y persistencia.
4. **Las redes sociales fragmentan.** Facebook/Instagram sirven para avisar, no para archivar.
5. **La procedencia es confianza.** «Escaneo propio», «tradumaqueta», «recopilación», «Mega» no significan lo mismo; el coleccionista quiere saber qué tiene.
6. **El idioma/edición es una faceta real.** Tradumaquetas y BD lo demuestran; ZascArr hoy no tiene un campo de idioma/edición.
7. **La fricción de entrada crea comunidad, pero no producto.** Cuestionarios e invites no se trasladan a una app self-hosted.
8. **Los enlaces externos caducan.** Mega/foros/Telegram no son una base de datos.

## 4. Features propuestas para ZascArr

Prioridad por valor para el coleccionista / coste. Las tres primeras coinciden con la decisión de producto.

| # | Feature | Qué resuelve | Datos que ya existen | Coste | Prioridad |
|---|---|---|---|---|---|
| **1** | **Sagas en la ficha de serie** | Ver en qué sagas participa una serie y en qué posición, sin buscar en `/ui/arcos` | `story_arc_issues.reading_order`, `StoryArc` | S/M | **P1** |
| **2** | **Filtro por autor en Biblioteca** | Navegar por autores/etapas, como hacen los foros | `creators`, `issue_creators` | M | **P2** |
| **3** | **Favoritos locales** | Marcar series imprescindibles y filtrarlas | Nueva columna local | M | **P3** |
| **4** | **Idioma/edición de la serie** | Distinguir española/inglesa, oficial/tradumaqueta, edición | No existe; campo estructurado nuevo | M/L | P4 |
| **5** | **«Continuar leyendo»** | Volver al último número leído desde Inicio | `ReadingStatus` y estado de lectura | M | P5 |
| **6** | **Guía de lectura como saga enriquecida** | Orden comentado de una etapa, no solo una lista | `StoryArc.description` + orden | S | P6 |
| **7** | **Búsqueda por etapa/año** | Acotar por época, como las cronologías | `start_year`, `end_year`, arcos | M | P7 |

### Detalle de las tres primeras

#### 1. Sagas en la ficha de serie

- **Problema:** el orden de lectura existe, pero no se ve desde la serie.
- **Qué:** fragmento perezoso «Sagas» con enlace a `/ui/arcos/{id}` y posición (por ejemplo «puesto 3 de 12»).
- **Aceptación:** serie en varias sagas → varias filas; sin sagas → no se pinta; sin consulta hasta abrir/decidir el fragmento; no se toca ni un archivo.
- **Por qué ahora:** es el patrón de las cronologías, con datos ya modelados.

#### 2. Filtro por autor

- **Problema:** Biblioteca filtra por editorial, personaje, saga y etiquetas, no por autor.
- **Qué:** filtro por `creator` exacto, combinable, con estado en URL y limpieza; enlace desde la ficha cuando el autor sea relevante.
- **Aceptación:** autor + tradición/editorial funciona; paginación; sin N+1; sin cambios de archivos.
- **Ojo:** un número puede tener varios autores; el filtro debe ser «participa en» no «autor único».

#### 3. Favoritos

- **Problema:** con cientos de series no hay una marca rápida de «esta sí».
- **Qué:** booleano local por serie, estrella en ficha/Biblioteca y filtro «Favoritas».
- **Aceptación:** idempotente; filtro en URL; no altera Deseados, etiquetas ni archivos; migración reversible.

## 5. Lo que NO se propone

- Integrar Telegram, Facebook, foros, Mega, Getcomics, EmuleBDZ, Archivio, Comic Mafia ni BD como fuentes.
- Scrapers de descarga o enlaces directos.
- «Tendencias» sin datos propios.
- Invitaciones/cuestionarios como requisito de la app.
- Un lector externo recomendado o contenido +18.
- Importar etiquetas de calidad de scan de terceros: serían una garantía falsa y sin procedencia.

## 6. PASS / FAIL / NOT RUN

- **PASS (decisión):** se han clasificado las 35 fuentes por modelo y se han extraído patrones de curación; las features propuestas usan datos locales o campos estructurados, no scraping.
- **PASS (estado actual):** ZascArr ya tiene sagas/orden, colecciones, etiquetas, calidad, procedencia y estado de lectura; no se duplican.
- **FAIL (como fuentes):** ninguna acredita licencia/términos ni API estable; no se integran.
- **NOT RUN:** observación directa de las comunidades, catálogos reales, medición de esfuerzo y validación con coleccionistas.
