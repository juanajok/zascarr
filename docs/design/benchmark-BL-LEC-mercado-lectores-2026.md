# Benchmark de mercado — lectores de cómics 2026 para el lector de ZascArr

> **Ficha de benchmarking (§13 de `CLAUDE.md`)** según
> [`benchmark-referencias.md`](benchmark-referencias.md). **Fecha:** 2026-11-17.
> **Base contrastada:** `origin/main` `edf2fa61` (2026-11-17, con **BL-LEC4 #827 ya
> fusionada** en la PR #1056). El checkout local se puso al día al terminar la ficha; todo lo
> de ZascArr que se cita se releyó sobre esa base.
> **Insumo:** informe «Los mejores lectores de cómics digitales del mercado (2026)», aportado
> por el PO el 2026-11-17. Es una comparativa de **12 aplicaciones** (más KOReader, que se
> añadió al verificar los clientes OPDS-PSE) **sin versiones, sin enlaces
> a documentación y sin pruebas**: se trata como fuente secundaria.
> **Complementa, no sustituye,** [`benchmark-BL-LEC-lector.md`](benchmark-BL-LEC-lector.md)
> (ya en `main`), que decide **cómo se sirven las páginas** (Komga, Kavita, Suwayomi) y ya
> tiene su matriz. Esta ficha mira **producto y clientes**: qué ideas de los lectores de
> consumo se igualan, adaptan o descartan, y qué apps pueden leer de verdad por OPDS/OPDS-PSE.
> **Nivel:** 2 por alcance (varias referencias y decisión de producto), **sin matriz
> ponderada**; el motivo está en §7.3. No sustituye a la ficha de nivel 2 de ninguna historia
> concreta.
> **Alcance:** insumo para la épica BL-LEC (#822): LEC3 (#826) y LEC5 (#828). LEC4 (#827)
> se fusionó mientras se escribía la ficha y aquí se refleja ya como hecha.
> **Insumo, no aprobación:** decide el PO. No autoriza implementar ni cambia las decisiones
> D-L1–D-L4 de #822.

---

## 0. Respuesta para el PO

1. **El informe sirve como mapa de mercado, no como especificación.** No cita versiones ni
   pruebas, y tiene errores corregibles: la incompatibilidad «Chunky 1.4.0» está mal
   atribuida (la doc de Komga habla de **Komga 1.4.0+**), el «Web» de YACReader es una WebUI
   con lector «muy básico», y **Mihon y YACReader no hablan OPDS** aunque #828 los nombre
   entre las apps a probar (§2.3, §5).
2. **No cambia la decisión de producto ya tomada** (2026-11-14, #822): lector propio en
   ZascArr (D-L1/D-L2) y OPDS-PSE como fase posterior. La refuerza: los clientes que hoy
   hacen *streaming* por PSE son **Panels, Chunky y KOReader**; ninguno devuelve el progreso
   por OPDS. La lectura de CBR ya está en `main` (**LEC4 #827**, fusionada el 2026-11-17), así
   que el «solo ≈14 % legible» de los borradores anteriores es histórico.
3. **Lo que sí mueve las historias vivas:**
   - **LEC3 (#826):** la idea «al acabar, seguir con el siguiente número» está en el mercado
     (CDisplayEx «siguiente álbum», YACReader «continuar leyendo»), pero ZascArr la implementa
     con su numeración (grapa, packs), nunca con `sort_order`; #826 ya lo fija y lo midió.
   - **LEC5 (#828):** el criterio 6 (probar con una app real) debe hacerse con **KOReader**
     (gratis), **Panels** (OPDS de pago) o **Chunky** (compra dentro de la app). Mihon y
     YACReader no son clientes OPDS: no pueden validar el criterio.
   - **Límite que conviene enseñar antes de prometer PSE:** el progreso leído en la app
     externa **no vuelve** a ZascArr. PSE es de ida; Panels/Chunky solo sincronizan contra la
     API de Komga/Kavita, no por OPDS. Decisión de producto: aceptar dos silos de progreso
     (lector propio y app externa) o no ofrecer PSE (§5.3).
4. **Ideas nuevas que sobreviven al filtro:** dos, y ninguna exige servidor — los
   **filtros de imagen del lector** (brillo, contraste, sepia, invertir), en cliente y sin
   coste de la Pi (§4.2, §7.4), y la **decisión pequeña de LEC3** de si el lector marca
   «Leído» al llegar al final (§4.2, §7.4). Añadido por el PO, no por el informe: la
   **lectura inmersiva** sin el marco de ZascArr, con flechas superpuestas en el PC y gesto
   en táctil (§4.2, §7.4 y épica BL-LECUX). El resto de funciones de lectura «de mercado»
   (zoom propio, navegación por viñetas, modo webtoon, estadísticas, marcadores, IA de
   imagen) se descarta o se aparca con motivo.
5. **Nada que copiar en código.** YACReader, OpenComic y Kavita son GPL-3.0; Komga es MIT;
   Mihon Apache-2.0; KMReader MIT. ZascArr es GPL-3.0, pero esta ficha toma **patrones e
   ideas**, no implementaciones (§10.3).
6. **Lo que esta ficha no decide:** el contrato de servido (BL-LEC), la cuota y topes de la
   caché de RAR ya fijados en LEC4, el alcance de LEC5 ni la seguridad de servir contenido
   por Basic (pasada de SecOps de #828). Nada de eso se autoriza aquí.

---

## 1. Problema local y datos reales

**Historia y pregunta.** La épica **BL-LEC** (#822) decidió el 2026-11-14 un lector propio
en ZascArr, con un único JavaScript (ADR 0021), progreso por archivo (D-L2) y OPDS-PSE como
fase posterior. LEC0–LEC2 y **LEC4 están cerradas y en `main`**; LEC3 (siguiente número) y
LEC5 (OPDS-PSE) siguen abiertas. El PO aporta una comparativa de lectores de consumo de
2026 y la pregunta es: **¿qué de lo que hacen esas apps conviene igualar, adaptar o descartar
en el lector propio y en la lectura desde apps, sin romper el presupuesto de la Pi ni las
decisiones ya tomadas?**

**Datos reales que mandan** (ficha BL-LEC §2 y #822; medidos en la Pi):

| Dato | Valor |
|---|---|
| Archivos legibles en la biblioteca | 5.640 = 4.891 CBR + 746 CBZ + 3 (PDF/CB7) |
| Peso de los CBR | 202,1 GiB (media ≈ 42,3 MiB por archivo) |
| `.cbr` que por dentro son ZIP | 56; RAR reales ≈ 4.835 |
| Cobertura del lector con LEC4 | Casi toda: CBZ y CBR; quedan fuera RAR5 sólidos, cifrados/multivolumen y PDF |
| CBR ya legibles (LEC4) | 4.891 (86,7 %), extraídos a una caché de ~1 GiB; sin LEC4 el lector solo cubría ≈14 % |
| PDF / CB7 | 2 / 1; fuera de alcance (decisión de la épica) |

**Estado real del lector en `origin/main` (`edf2fa61`), no en el informe:**

- `web/lector.py`: `GET /ui/leer/{file_id}` (pantalla), `GET /ui/leer/{file_id}/pagina/{n}`
  (bytes originales con `ETag`/`private` vía `cached_image_response`),
  `GET /ui/leer/{file_id}/estado` (JSON `preparando`/`listo`/`error` para los CBR),
  `POST /ui/leer/{file_id}/sentido` y `POST /ui/leer/{file_id}/progreso` (204).
- `services/lector.py`: página por índice de un listado validado (#307), tope de entradas,
  orden natural, `ETag` por hash+índice, `guardar_progreso` y sentido de lectura con
  prioridad serie > `<Manga>` de ComicInfo > tradición.
- `services/cache_lectura.py` (LEC4): extrae el RAR entero a una caché con cuota
  (`lector_cache_bytes`, 1 GiB por defecto), `os.replace` atómico, nombres saneados y
  limpieza de lo antiguo salvo lo que se está leyendo. `RAR5` sólidos siguen fuera (ADR 0015).
- `static/lector.js` (~240 líneas, único JS propio, ADR 0021): modos ajustar al ancho /
  ajustar a la pantalla / doble página, sentido RTL, teclado, zonas táctiles, pantalla
  completa.
- Progreso: `ReadingProgress` 1:1 con `Issue`, con `file_id` opcional (migración 0050) y
  `current_page`; la ficha del número ofrece **«Leer» / «Continuar (pág. N)»**. Inicio ya
  tiene «Continuar leyendo» (`services/inicio.py::continuar_leyendo`, CUR5).
- Lectura manual (BL-C3): estado, puntuación 1–5 y nota por número; filtro «Leídos» en
  Biblioteca. Las estadísticas y el «siguiente número» estaban descartados en el backlog
  anterior; **LEC3 reabre de facto el segundo** y habrá que reconciliar la lista de
  descartados al cerrarla.
- OPDS: catálogo 1.2 en `/opds` (solo catálogo, sin contenido). La decisión de C5
  («solo catálogo») queda **superada por LEC5** (decisión del PO, 2026-11-14).
- Kavita: exportación B20 fusionada en `main` (fases 1 y 2; pendiente de despliegue real) y
  WK5 descartado por ahora con condiciones (`spike-kavita-343.md`).

**Lo que no existe hoy** (y esta ficha evalúa si debe existir): zoom propio del lector,
navegación por viñetas, modo webtoon/tira vertical, marcadores de página, estadísticas de
lectura, soporte PDF/CB7/EPUB, sincronización de progreso desde apps externas y streaming de
contenido por OPDS (LEC5).

---

## 2. Referencias, método y correcciones

### 2.1 Método

- **Fuente del PO:** informe de 2026 sobre 12 aplicaciones (YACReader, OpenComic, Kavita,
  Komga, Panels, TritonPanels, CDisplayEx, Perfect Viewer, ComicScreen, KMReader, Chunky,
  Mihon). Sin versiones, sin fechas de consulta y con «citas» del tipo «sitio oficial +1»;
  se usa como **mapa de funciones**, nunca como prueba de compatibilidad. **KOReader no
  estaba en el informe**: se añade al verificar los clientes OPDS-PSE (§5, Anexo A).
- **Verificación propia (2026-11-17):** documentación oficial, notas de release y LICENSE
  de los proyectos; solo lectura. **No se ejecutó ningún servidor ni ninguna app**, así que
  todo lo que exige abrir la interfaz o probar un endpoint queda **NOT RUN**.
- **Regla de la casa:** no se infiere soporte por la UI, ni ausencia por no encontrarlo. Lo
  no verificado va marcado.

### 2.2 Referencias verificadas (versión, licencia y límites)

| Referencia | Versión / fecha | Licencia | Qué es de verdad | Límite comprobado |
|---|---|---|---|---|
| **Kavita** | 0.9.1.4 (2026-09-02) | GPL-3.0 | Servidor de biblioteca con lector web; OPDS por usuario con AuthKey y **OPDS-PS**; API REST con OpenAPI | El spike de WK5 midió contra **0.9.0.2** (2026-11-11); no se debe asumir la API de `develop` |
| **Komga** | 1.30.1 (2026-11-10) | MIT | Servidor con OPDS 1.2 (PSE 1.2) y OPDS 2.0, API REST | No se probó en vivo; su doc es la referencia de clientes |
| **Panels** | — | Propietaria | Lector Apple (iPhone/iPad/Mac); OPDS 1.x y **PSE 1.0 (v2.8.0+) / 1.1 (v2.9.7+)** | **OPDS exige Panels+ o compra dentro de la app**; sync de progreso solo con API de Komga/Kavita; **no hay Android comprometido** |
| **Chunky** | — | Propietaria | Lector iPad; OPDS y **PSE 1.0** | OPDS exige compra dentro de la app (3,99 $ según la doc de Komga); **no sincroniza progreso** |
| **KOReader** | — | — (no verificada) | Lector multiplataforma; OPDS y **PSE** (Komga lo lista) | El progreso se sincroniza por API dedicada, no por OPDS |
| **TritonPanels** | — | Propietaria | Lector iOS 17+/Android 7+; OPDS de catálogo; API nativa de Komga/Kavita con sync bidireccional | **Suscripción obligatoria** (14 días de prueba); **sin PSE**; por OPDS genérico el progreso se queda en el dispositivo |
| **Mihon** | — | Apache-2.0 | Lector de manga Android | **Sin OPDS nativo**; usa extensión de Komga o API de Kavita; sync por capítulo |
| **CDisplayEx** | Android 1.3.96 (2026-09-12); Windows | Propietaria (precio no verificado) | Lector Android/Windows | **Sin OPDS**; conexión a Kavita por API. Sus conexiones cloud/Komga/Mega en Pro: **NOT RUN** |
| **YACReader** | 10.5.1 (2026-11-13) | GPL-3.0 | Escritorio Win/macOS/Linux + iOS/Android; servidor Docker (YACReaderLibraryServer) con **WebUI y lector web «muy básico»** | **Sin OPDS**: *feature request* #98 abierto desde 2019 (última actividad 2023-09) |
| **KMReader** | — | MIT | Cliente nativo de **Komga** para iOS 17+/iPadOS 17+/macOS 14+/tvOS 17+ | Solo Komga; no aplica a ZascArr salvo que se imite una API |
| **OpenComic** | 2.0.0 (2026-11-14) | GPL-3.0 | Lector de escritorio; **IA local nativa** (modelos propios y de terceros descargados, no en la nube) | Coste de CPU/RAM incompatible con la Pi; OPDS según el informe (**NOT RUN** en esta ronda); **PSE NOT RUN** |
| **Perfect Viewer / ComicScreen** | — | — | Lectores Android | Vivos en Play; versión, licencia, precio y PSE **NOT RUN** (no se pudo leer la ficha) |

El papel de cada aplicación, lo que aporta y su veredicto están en el **Anexo A**; esta
tabla es la evidencia de versión y licencia.

### 2.3 Correcciones al informe del PO

| # | El informe dice | Lo comprobado | Efecto |
|---|---|---|---|
| 1 | «Komga documenta incompatibilidad con [Chunky] 1.4.0 y posteriores» | La doc real dice «**Chunky Reader does not work anymore with Komga 1.4.0+**»: la versión 1.4.0 es de **Komga**, no de Chunky; la misma página sigue documentando OPDS y PSE 1.0 de Chunky (actualizada 2026-11-10). Causa raíz: **NOT RUN** | **No excluir Chunky** de la prueba de LEC5 por este dato |
| 2 | YACReader «Web · NAS» | El servidor Docker ofrece WebUI y un lector web «muy básico» desde 10.2.0; **no** es un cliente web completo y **no** habla OPDS | No vale como cliente OPDS de referencia |
| 3 | Panels como lector de referencia | Correcto en plataformas (Apple) y OPDS/Komga/Kavita; el **OPDS es de pago** y el progreso no viaja por OPDS | Sirve para UX; para probar PSE, contar con el coste |
| 4 | Mihon como lector de referencia | **No tiene OPDS nativo** (extensión de Komga o API de Kavita) | No sirve para validar el criterio 6 de #828 |
| 5 | CDisplayEx Pro conecta OneDrive/Dropbox/Komga/Kavita/Mega | Solo se comprobó que la app sigue viva; las conexiones **NOT RUN** | No se usa como hecho |
| 6 | «Kavita+ añade recomendaciones y sincronización» | Kavita+ es de pago; el alcance exacto de su *Progress Sync* **NOT RUN**; el core, OPDS y la API son gratis | No se apoya ninguna decisión en Kavita+ |

**Conclusión de método:** el informe se puede usar para ordenar funciones y para copiar
vocabulario de producto; **no** para afirmar que una app concreta podrá leer de ZascArr. Eso
solo lo dice una prueba real, que es el criterio 6 de #828.

---

## 3. Supuestos del informe que NO valen en ZascArr

1. **SPA o cliente con build** (Kavita, Komga): ADR 0001 y ADR 0021 lo prohíben; el único JS
   propio es `static/lector.js`, sin dependencias ni compilación.
2. **RAM y CPU de sobra**: 512 MiB en una Pi compartida, un solo worker. Nada de recodificar
   imágenes por página, analizar la biblioteca entera ni ejecutar IA local.
3. **Multiusuario con perfiles**: ZascArr tiene una sola contraseña y no tiene usuarios; está
   en el parking lot del backlog.
4. **La unidad libro/capítulo es un archivo**: aquí un número puede tener varios archivos y
   un archivo puede cubrir varios números (`covered_issue_ids`); la numeración incluye
   decimales, anuales y packs. `sort_order` no es fiable (medido en #826).
5. **Nube, SMB, FTP o WebDAV propios**: no aplican; los archivos ya están en el servidor y
   la «nube» es la LAN, con proxy TLS si se expone (ADR 0004). El lector no descarga de
   fuera.
6. **Telemetría, comunidad, reseñas y recomendaciones**: prohibidas o fuera de alcance
   (LEGAL.md, parking lot). El producto es autoalojado y de un solo operador.
7. **Escribir en la biblioteca o en los CBZ al leer**: prohibido. El lector solo lee; la
   ficha de número es de solo lectura (#447) y la extracción de RAR va a caché aparte.
8. **Un solo formato de página**: aquí se sirven los bytes originales; si una página no es
   JPEG/PNG/GIF, LEC5 no la anuncia por PSE antes que recodificarla.

---

## 4. Resultado por idea

Vocabulario de §13: **Adoptar** (misma regla y mismos supuestos), **Adaptar** (cambia el
supuesto que aquí no vale), **Mejorar** (hacer algo mejor que la referencia, con evidencia),
**Construir sobre lo propio** (la base buena ya está en ZascArr) y **Descartar** (con motivo).
Se decide **por idea**, no por aplicación. Esta ficha no propone copiar pantallas.

### 4.1 Biblioteca, metadatos y automatización (informe §4-A, §4-B y §4-F)

| Idea del informe | ZascArr hoy | Resultado | Motivo |
|---|---|---|---|
| Biblioteca visual con portadas; navegar por editorial, serie, personaje, saga | Biblioteca con filtros combinables, chips y recuento (BL-IT01); portadas en caché local sin hotlinking | **Construir sobre lo propio** | Ya es el núcleo del producto; no hay hueco que copiar |
| Agrupar números por serie y volumen; huecos y series incompletas | `Series`/`Issue`, «huecos» C2, estado derivado en WK2 (backlog) | **Construir sobre lo propio** | La unidad (grapa/tomo/pack) y la honestidad del «no se puede calcular» son mejores que las de las apps del informe |
| Detección de duplicados | B16 `LibraryAudit` + BL-DUP0/BL-DUP1 (ADR 0017) | **Construir sobre lo propio** | Ya existe, y no borra ni sugiere borrar |
| Estados de lectura y puntuación | BL-C3: tres estados en la UI (Sin leer / Leyendo / Leído), 1–5, nota y filtro en Biblioteca; `on_hold` y `dropped` viven en el modelo sin superficie (decisión de BL-C3) | **Construir sobre lo propio** | El lector de consumo rara vez tiene nota personal; aquí ya está. «Abandonado» no se ofrece a propósito; no se añade un cuarto estado |
| Favoritos y etiquetas | Etiquetas con filtros (ETQ); «favoritos» como colección no está en el backlog | **Construir sobre lo propio** (etiquetas) | Las etiquetas cubren el caso de «marcar para encontrar»; no hay hueco medido para favoritos |
| Colecciones, sagas y listas | Colecciones BL-D6 y sagas C4; `reading_lists` en el modelo | **Construir sobre lo propio** | Cubierto; las «listas inteligentes» del informe no aportan un caso que BL-IT01 no resuelva |
| ComicInfo.xml (importar/exportar), autores por rol, ediciones y variantes | B6 (lectura y escritura), modelos de creadores/roles, identidad editorial y CCM (ADR 0020, edición y colecciones) | **Construir sobre lo propio** | Ya está; lo que falta son campos concretos, no el patrón |
| Identificación automática y metadatos desde fuentes | Enricher con Comic Vine/AniList/Tebeosfera (GCD pospuesto); fuentes **apagadas por defecto** (ADR 0013) | **Construir sobre lo propio** | Las apps del informe no resuelven el tebeo español; no hay nada que adoptar |
| Edición masiva de metadatos, reglas de organización y renombrado automático | Importador y rescan (BL-R9); metadatos editables; **renombrar la biblioteca** no es una operación soportada | **Descartar** el renombrado masivo | Cambiar rutas de una biblioteca ya vinculada rompe archivos y enlaces; no hay historia ni demanda que lo justifique |
| Escaneo e importación automáticos; detección de series incompletas | Importador periódico, rescan a demanda/periódico (BL-R9), registro incremental (#326) | **Construir sobre lo propio** | Cubierto y con más cautela que las referencias (no mueve ni borra sin confirmación) |
| Alertas de novedades y series que no se tienen | Deseados (D8/C6) y descubrir (C0); avisos D5/E4 en backlog | **Adaptar** (ya en backlog) | No se decide aquí; el informe no aporta contrato nuevo |

**Conclusión:** las ideas de biblioteca y metadatos del informe **no abren hueco**. ZascArr ya
las tiene o ya las decidió en otras fichas (§13: Whakoom, Metron, IT01, B6, BL-DUP0). Esta
ficha no las reabre.

### 4.2 Experiencia de lectura (informe §4-C)

| Idea del informe | ZascArr hoy | Resultado | Motivo |
|---|---|---|---|
| Una página o doble; ajustar al ancho/pantalla | LEC2: modos y página apaisada sola | **Construir sobre lo propio** (ya hecho) | No hay nada que adoptar; comparar solo el detalle fino (gesto y textos) |
| Pantalla completa real y lectura sin el marco de ZascArr | **Parcial:** LEC2 añadió el botón de Fullscreen API, pero la página sigue con barra lateral/marco y sin flechas superpuestas | **Adaptar** (petición del PO, 2026-11-17) | El «modo visor de fotos» no estaba en el informe; ver candidata 5 de §7.4 y LECUX6 |
| Sentido de lectura manga (derecha a izquierda) | Serie > `<Manga>` del ComicInfo > tradición; ajuste por serie en `Series.metadata_` | **Mejorado** sobre el mercado | Las apps suelen tener un ajuste global; aquí manda la serie y, si no hay ajuste, el ComicInfo del archivo |
| Táctil, teclado y atajos | LEC2: zonas 30/40/30 invertidas en RTL, **deslizar (50 px, `dx > 2·dy`)**, teclas `f`, `m` | **Construir sobre lo propio** (ya hecho) | Cubierto; las flechas superpuestas de escritorio son la novedad de LECUX6 |
| Precarga de la página siguiente | `lector.js` no precarga; el navegador reutiliza la caché HTTP y servir una página en la Pi cuesta 0,7–2 ms (LEC0) | **Construir sobre lo propio** (no prioritario) | La ganancia en LAN sería pequeña; si se quiere, es un cambio de JS pequeño, no una historia propia |
| «Continuar leyendo» y recordar la página | Botón «Continuar (pág. N)» en la ficha e Inicio «Continuar leyendo» (CUR5); progreso por archivo | **Construir sobre lo propio** | Ya existe; no hace falta la nube de las apps |
| Al terminar, ofrecer el siguiente número | LEC3 (#826), pendiente: grapa+1, packs, «te falta» → Deseados, `SIN_SIGUIENTE` | **Mejorar** | El mercado identifica el siguiente álbum; ZascArr además distingue «no lo tengo» de «no sé si existe» y no inventa huecos |
| Zoom propio y «zoom inteligente» | No existe. LEC2 decidió **zoom nativo del navegador** (`touch-action: pan-y pinch-zoom`) | **Descartar** | Un zoom propio exige gestos y estado en `lector.js` y no aporta sobre el del navegador; la decisión ya está tomada y probada |
| Navegación guiada por viñetas (*Guided View*, panel a panel) | No existe | **Descartar por ahora** | Exigiría detectar viñetas (análisis de imagen en la Pi) o una dependencia de JS; choca con «no analizar todas las páginas» (ficha BL-LEC L6), con «sin dependencias» y con el presupuesto de la Pi. Sin evidencia de necesidad; solo volvería con ADR y medición |
| Recorte automático de márgenes | No existe | **Descartar por ahora** | Recortar en cliente puede cortar arte o bocadillos; detectarlo en servidor exige analizar cada página. Sin evidencia de que el coleccionista lo pida |
| Modo webtoon / scroll vertical continuo | No existe | **Descartar** | La épica lo excluye a propósito: la tradición no dice el formato y un manhwa impreso no es un webtoon. No hay contenido webtoon en el objetivo |
| Filtros de imagen (brillo, contraste, gamma, sepia, invertir) | No existen | **Adoptar/Adaptar como candidata pequeña** | Se resuelven con `filter` de CSS en el cliente: **coste 0 en la Pi** y ningún byte recodificado. Referencias: YACReader, OpenComic, Panels, TritonPanels y Perfect Viewer (según el informe, sin probar en vivo). Condiciones en §7.4 |
| Marcadores por página y notas | Nota y puntuación por **número** (BL-C3); la página se reanuda por progreso | **Descartar por ahora** | El progreso ya resuelve «volver donde lo dejé»; los marcadores añaden modelo y UI sin demanda medida |
| Marcar «Leído» al llegar a la última página | No: el lector actualiza `current_page` y pasa a «Leyendo», pero no cierra el número; el estado se cambia a mano (BL-C3) | **Adaptar, candidata a decidir en LEC3** | Es la diferencia funcional más clara frente al mercado. Choca con la regla de no escribir de más: llegará como decisión de producto en LEC3, con su caso de prueba, no por imitación |
| Historial, estadísticas y relecturas | No existe; el backlog lo descartaba (lo cubría Kavita) | **Descartar** | Producto de un solo operador, sin telemetría ni panel de estadísticas. El lector ya escribe `current_page`; si algún día se quiere, será otra historia con su ficha |
| Sincronización de progreso entre dispositivos | Para el lector propio es **inherente**: todos leen la misma base de datos | **Construir sobre lo propio** | No hay nube que sincronizar; el «sync» del mercado resuelve un problema que aquí no existe |
| Descargas para leer sin conexión | No aplica al lector propio (LAN); las apps externas pueden descargar, pero LEC5 no ofrece enlaces de descarga | **Descartar** | La épica excluye descarga del archivo entero; PSE es streaming de páginas |
| PDF y cómics en EPUB | 2 PDF en el disco; EPUB no está en la biblioteca | **Descartar** | Ya decidido en BL-LEC (L13); una app de consumo no cambia el coste de un lector PDF/EPUB propio |
| CB7/CBT, RAR5 sólidos | CB7 = 1 archivo; RAR5 sólidos no se extraen con `unar` (ADR 0015) | **Descartar** | CB7 no compensa; RAR5 sólidos son una limitación conocida y aceptada, no una función a copiar |

### 4.3 Descubrimiento y comunidad (informe §4-D y §4-E)

**Descartado**, con motivo, y no se reabre sin uno nuevo:

- **Catálogo de novedades, rankings, recomendaciones por autor/personaje, cómics similares,
  series relacionadas, valoraciones medias externas, reseñas públicas y «mejores cómics»**:
  requieren un catálogo de referencia continua, telemetría o una comunidad; ZascArr es
  autoalojado, de un solo operador y sin telemetría (LEGAL.md). Lo que sí existe —Deseados,
  descubrir (C0) y novedades D5 en backlog— cubre el caso base.
- **Perfiles, biblioteca compartida, listas públicas, comentarios y recomendaciones entre
  usuarios**: el multiusuario está en el parking lot; además, compartir una biblioteca de
  archivos es redistribuir contenido (LEGAL.md, CLAUDE.md §5).
- **Valoración personal 1–5 y nota**: no es descubrimiento; ya existe por número (BL-C3).

---

## 5. Clientes OPDS y OPDS-PSE (para LEC5, #828)

### 5.1 Matriz de clientes

Leyenda: ✅ comprobado en documentación oficial · ❌ no soportado · — no aplica · `NOT RUN`
no se pudo comprobar en vivo.

| Cliente | Plataformas | OPDS catálogo | OPDS-PSE | Progreso de vuelta | Coste | Sirve para el criterio 6 |
|---|---|---|---|---|---|---|
| **KOReader** | Escritorio/móvil (multiplataforma) | ✅ | ✅ (Komga lo lista) | Por API dedicada de Komga, no por OPDS | Gratis | **Sí, primera opción gratuita** |
| **Panels** | iPhone/iPad/Mac | ✅ OPDS 1.x | ✅ PSE 1.0/1.1 | Solo API de Komga/Kavita | OPDS requiere Panels+ o compra | **Sí, si hay licencia**; útil además para UX |
| **Chunky** | iPad | ✅ | ✅ PSE 1.0 | ❌ | Compra dentro de la app | **Sí**, con el aviso de §2.3 (la incompatibilidad documentada es *Komga* 1.4.0+, no Chunky) |
| **TritonPanels** | iOS 17+/Android 7+ | ✅ | ❌ | Solo API de Komga/Kavita | Suscripción | Solo catálogo; **no valida PSE** |
| **Mihon** | Android | ❌ nativo (extensión Komga/API Kavita) | ❌ | Por capítulo, vía API | Gratis | **No**; probarlo exigiría imitar la API de Komga, fuera de alcance |
| **CDisplayEx** | Android/Windows | ❌ | — | API de Kavita | Propietaria | **No** |
| **YACReader** | Escritorio + iOS/Android | ❌ (#98 abierto desde 2019) | ❌ | Contra su propio servidor | Gratis | **No** |
| **KMReader** | iOS/iPadOS/macOS/tvOS | Solo Komga | — | Solo Komga | Gratis | **No** |
| **OpenComic** | Escritorio | `NOT RUN` (el informe dice ✅) | `NOT RUN` | — | Gratis | No prioritario para móvil/tablet |
| **Perfect Viewer** | Android | El informe dice ✅; `NOT RUN` | `NOT RUN` | — | — | Solo si el PO amplía la muestra |

La ficha completa de cada aplicación, con lo que le atribuye el informe y su veredicto,
está en el **Anexo A**.

**Conclusión para #828:**

1. El criterio 6 (probar con una app real) se hace con **KOReader** (gratis y con PSE),
   **Panels** (si se dispone de licencia) o **Chunky**. **Mihon y YACReader no pueden**
   validarlo y conviene corregir su mención en la tarjeta cuando el PO la revise.
2. **Versión de PSE:** Panels declara PSE 1.0/1.1; Komga sirve PSE 1.2. La versión a
   implementar la fija #828 leyendo la especificación publicada; conviene implementar la
   variante más compatible y probar con la app real antes de marcar PASS.
3. **Ningún cliente de la muestra exige OPDS 2.0/PAWG**; OPDS 1.2 de catálogo + PSE cubre a
   Panels, Chunky, TritonPanels y KOReader. No hay que abrir una segunda API.
4. **Autenticación:** los clientes se configuran con la URL del servidor y credenciales;
   ZascArr ya sirve Basic en `/opds` igual que en `/api` (spec de C5). Sobre HTTP viaja en
   claro: solo vale en LAN de confianza o con proxy TLS (ADR 0004). **Que cada app concreta
   envíe la credencial en la primera petición de página es NOT RUN** y se comprueba en el
   criterio 6 de #828.

### 5.2 Lo que PSE resuelve y lo que no

- **Resuelve:** leer página a página en una app madura de tablet/móvil sin descargar el
  archivo entero, reutilizando `services/lector.py::pagina`; el feed puede anunciar el
  número de páginas y la última leída.
- **No resuelve:** devolver el progreso a ZascArr. No se encontró un protocolo OPDS estándar
  de escritura de progreso; Panels, Chunky, TritonPanels, Mihon y KOReader sincronizan
  contra **API de Komga/Kavita**, no contra OPDS. Si se quiere progreso compartido, la vía
  sería imitar esa API o reabrir WK5, y ninguna de las dos está autorizada aquí.
- **No resuelve:** leer CBR que no estén preparados en la caché de LEC4 sin espera; #828 ya
  propone anunciar solo lo servible sin espera (decisión del PO pendiente).

### 5.3 Decisión de producto que deja abierta

Dos silos de progreso: leer en el lector propio y leer en Panels con PSE no comparte la
página actual. Opciones: (a) aceptar el límite y decirlo en la interfaz; (b) no ofrecer PSE
y seguir con el lector propio; (c) abrir una historia nueva de API de progreso compatible
con Komga/Kavita. **No se decide aquí**; queda para el PO cuando #828 se refine.

---

## 6. Relación con C5, WK5 y B20 (estado, no reapertura)

- **C5 (#160):** el OPDS de catálogo está implementado (`api/opds.py`); la decisión «solo
  catálogo, no contenido» queda **superada** por LEC5 (decisión del PO, 2026-11-14; #822 y
  #828). Las notas antiguas del backlog que rechazaban OPDS-PSE («lo que no se roba») y la
  fila C5 de `docs/BACKLOG.md` están desactualizadas: hay que corregirlas al cerrar LEC5.
- **WK5 (spike #343; fila WK5 del backlog):** el spike decidió **descartar la integración
  automática por ahora** con condiciones (identidad segura por B20+ruta/hash, progreso
  representativo, opt-in con AuthKey, solo lectura, derivación de estado documentada, versión
  mínima fijada, sin telemetría). B20 ya está fusionado, así que la primera condición está
  materialmente cumplida, pero **WK5 no se reabre por esta ficha**. Nuevo dato a tener en
  cuenta cuando se revise: LEC5 **no** sustituye a WK5, porque PSE no devuelve progreso.
- **B20 (#149):** exportación a Kavita fusionada (pendiente de uso real). TritonPanels
  (carpeta/SMB) y CDisplayEx (local) podrían leer la carpeta exportada; YACReader usa su
  propio servidor/biblioteca y Panels exige un servidor OPDS. El camino soportado y
  documentado sigue siendo Kavita; no se promete lo demás.
- **La frontera «el lector es Kavita»** que aparece en fichas anteriores (Whakoom, Metron)
  quedó **cambiada el 2026-11-14**: ahora ZascArr tiene lector propio y Kavita sigue siendo
  el lector de referencia para quien ya lo usa. Este documento no reescribe esas fichas;
  solo deja constancia de que la premisa cambió.

---

## 7. IGUALAR, MEJORAR, candidatas y descartes

### 7.1 IGUALAR (mínimo competitivo del lector)

Ya hecho o en la historia en curso: página a página; doble página y ajustes de tamaño;
sentido de lectura; teclado, táctil y pantalla completa; continuar donde lo dejé; leer CBR
(LEC4, fusionada); y, cuando LEC5 esté, ofrecer las páginas por PSE a una app real.

### 7.2 MEJORAR (con evidencia, no con opinión)

1. **«El siguiente» con la numeración de ZascArr**, no con `sort_order`: el mercado identifica
   el siguiente álbum, pero aquí hay packs, decimales y anuales; #826 midió que `sort_order`
   no es fiable (0/18 issues) y ya fijó la regla (grapa+1, packs al mayor cubierto, «te
   falta» solo si se sabe, si no `SIN_SIGUIENTE`).
2. **Una sola verdad de progreso por número** (lector, botón manual y filtro de Biblioteca)
   frente a apps que guardan el progreso en el dispositivo.
3. **No recodificar imágenes** y no analizar la biblioteca entera al escanear: la ficha
   BL-LEC lo midió (0,7–2 ms por página de CBZ en la Pi) y esta ficha no propone nada que
   fuerce lo contrario.

### 7.3 Matriz: no aplica a esta ficha

§13 pide matriz ponderada para nivel 2. Aquí **no hay una decisión entre implementaciones
que puntuar**: el servido de páginas ya se decidió en BL-LEC (su matriz §9 elige caché de
RAR, opción B) y el producto ya decidió lector propio + PSE. Puntuar 12 apps contra los
criterios de ZascArr sería una nota comercial, no una decisión. **Cualquier historia que
salga de aquí y toque servido, seguridad o modelo de datos (p. ej. filtros en servidor o
marcadores) se abre con su propia ficha de nivel 2 y su matriz**; esta no vale como
aprobación.

### 7.4 Candidatas (propuestas, sin aprobar)

| # | Candidata | Tamaño | Qué la justifica | Condiciones para admitirla |
|---|---|---|---|---|
| 1 | **Filtros de imagen del lector** (brillo, contraste, sepia, invertir) | S | Aparece en cinco apps del informe; se resuelve con `filter` CSS en cliente, **coste 0 en la Pi** | Solo en `lector.js`/CSS, sin recodificar ni servir otra imagen; ajuste por dispositivo (`localStorage` con `try/catch`) y siempre reversible; contraste y `prefers-contrast` respetados; sin un control más en la pantalla que rompa el presupuesto de texto; decisión del PO |
| 2 | **Actualizar #828** con la lista corregida de clientes (KOReader/Panels/Chunky; Mihon y YACReader fuera) | — | Evita un criterio 6 imposible de cumplir | No es historia: es una revisión de la tarjeta cuando el PO la refine |
| 3 | **Decir el límite de progreso de PSE** en la documentación/ajustes del OPDS | S (docs) | Evita prometer sync que no existe | No es código; va con la documentación de LEC5 |
| 4 | **Decidir en LEC3 si el lector marca «Leído» al llegar al final** | S | Es la diferencia más clara frente al mercado; ya se anticipó en la ficha BL-LEC (L8) pero no está implementado | Decisión de producto en LEC3, con caso de prueba; si se adopta, debe decirse en la interfaz y no pisar una lectura ya marcada a mano |
| 5 | **Lectura inmersiva** (sin marco, chrome auto-oculto, flechas superpuestas en PC y gesto en táctil) | M | **Petición del PO (2026-11-17)**, no del informe: hoy el lector va enmarcado; el deslizar ya existe (LEC2) y las flechas superpuestas no | Solo en la pantalla de lectura; fullscreen con fallback inmersivo donde la API no existe; flechas solo con puntero fino; salida siempre disponible (`Esc`/Volver) y aviso legal en Opciones; sin zoom propio ni panel a panel; decisión del PO |
| 6 | **Nada más.** El resto de §4 se queda como está o descartado | — | No hay hueco medido | Volver solo con evidencia nueva y ficha propia |

Estas candidatas se convierten en historias en la épica propuesta
[`epica-BL-LECUX-lector.md`](epica-BL-LECUX-lector.md), que no autoriza nada por sí sola.

### 7.5 Lo que no vuelve sin un motivo nuevo

Zoom propio, navegación por viñetas, modo webtoon, recorte de márgenes, marcadores de
página, estadísticas de lectura, PDF/EPUB/CB7, IA de reescalado o colorización, multiusuario,
listas públicas, reseñas, recomendaciones, telemetría, OPDS 2.0 y descarga del archivo
entero por OPDS. Cada uno tiene su motivo arriba; el motivo caduca con la ficha.

---

## 8. Invariantes que filtran cualquier candidata

1. **Pi compartida:** 512 MiB, un worker, sin Redis. Nada de recodificar ni analizar los
   5.640 archivos al vuelo; los filtros, si se hacen, son de cliente.
2. **Sin SPA ni build; un solo JS** (`lector.js`, ADR 0021), sin dependencias ni CDN. Cualquier
   crecimiento fuera del lector exige ADR nueva.
3. **El lector no escribe en la biblioteca** ni en los CBZ; el progreso va a `reading_progress`
   y la caché de RAR a su volumen, nunca a la SD (D-L3).
4. **Autenticación:** la misma de `/ui` y la Basic de `/opds`; Basic sobre HTTP solo en LAN de
   confianza o con proxy TLS (ADR 0004). No se añaden exenciones.
5. **Sin telemetría, sin red externa y sin hotlinking.** Las fuentes de metadatos siguen
   apagadas por defecto (ADR 0013); el lector no consulta ninguna.
6. **Español llano y sistema de diseño:** textos ≥14 px, sin jerga (`sort_order`, `PSE`,
   `token` no llegan al coleccionista), textos de la pantalla del lector ya aprobados y
   ampliables sin salirse del presupuesto de §6 de `CLAUDE.md`.
7. **Unidades del dominio:** la fuente de verdad es la numeración y los archivos de ZascArr;
   ninguna app externa manda sobre el catálogo.

---

## 9. Casos de prueba antes de implementar (para las candidatas)

- **Filtros de imagen:** sin JS el lector sigue funcionando; el filtro no cambia el archivo
  ni el `ETag`; se recuerda por dispositivo y se puede volver a «Sin filtro»; con
  `prefers-contrast: more` no empeora la legibilidad; una imagen con fondo blanco no pierde
  detalle por el filtro; no hay petición nueva al servidor.
- **LEC5 (cuando toque):** servidor OPDS 1.2 con un cliente real (KOReader/Panels/Chunky);
  una página fuera de rango responde 404 sin traza; sin credenciales, 401; el XML no lleva
  rutas ni descargas; misma imagen y mismo `ETag` que `/ui`; un número con páginas webp/avif
  no anuncia PSE; probar la numeración 0/1 con una sola función y su test.
- **LEC3 (referencia):** acabar un pack del 5 al 7 ofrece el 8; un archivo sin grapa no
  inventa siguiente; «te falta» solo si la serie tiene total conocido; «Añadir a Deseados»
  respeta la puerta legal (403 sin aceptación).

---

## 10. Límites, NOT RUN y caducidad

### 10.1 NOT RUN

- Ejecutar cualquier cliente (Panels, Chunky, KOReader, TritonPanels, Mihon, CDisplayEx,
  YACReader, Perfect Viewer, ComicScreen, KMReader, OpenComic): **no se abrieron apps ni
  servidores**; todo lo funcional es documentación.
- Precios exactos de Panels+ y TritonPanels; alcance de Kavita+ *Progress Sync*; causa raíz
  de la incompatibilidad Chunky ↔ Komga 1.4.0+; versión, licencia y PSE de Perfect Viewer y
  ComicScreen; conexiones de CDisplayEx Pro; PSE de OpenComic.
- Comportamiento en vivo de ZascArr con un cliente PSE: depende de LEC5, que no está
  implementado.
- Zoom/gestos en dispositivo real, lector de pantalla y navegador real de las candidatas:
  no se han probado; la verificación es de la historia que las implemente.

### 10.2 Caducidad

**~60 días (2027-01-16)**, o antes si cambian el ADR 0001, el ADR 0015, la **ADR 0021
(JavaScript propio del lector)**, la decisión D-L1–D-L4 de #822, C5 o WK5. Las versiones de
las apps y de Kavita/Komga también caducan la ficha.

### 10.3 Barrera legal

Esta ficha toma **ideas y patrones**, no código. Licencias verificadas: YACReader,
OpenComic y Kavita **GPL-3.0**; Komga **MIT**; Mihon **Apache-2.0**; KMReader **MIT**;
ZascArr es GPL-3.0. Compartir código con los GPL-3.0 sería compatible en licencia, pero
exigiría cumplir sus obligaciones; antes de reutilizar cualquier implementación hay que leer
el fichero concreto y sus avisos. Los nombres de apps y sus capturas no se usan como
material de la interfaz.

### 10.4 Deudas de documentación detectadas (no corregidas aquí)

- La fila **C3** de `docs/BACKLOG.md` sigue diciendo «reading_progress ya está en el modelo;
  falta exponerlo + UI», cuando BL-C3 está implementado y fusionado. La fila **C5** sigue
  diciendo «solo catálogo» cuando el PO ya la superó con LEC5. Y **no hay fila BL-LEC** en
  el backlog: el seguimiento vive en #822–#828 y en la ficha BL-LEC.
- La lista de «Descartado» del backlog incluye «siguiente número» y «estadísticas de
  lectura»; LEC3 reabre de facto el primero. Al cerrar LEC3 hay que reconciliar la lista con
  su motivo nuevo.
- La **ADR 0021** cita la ruta `/ui/series/{id}/numero/{issue_id}/leer`, pero el código sirve
  `/ui/leer/{file_id}`; manda el código. Se corrige en la PR que toque el lector, no aquí.
- Las fichas antiguas (Whakoom, Metron) dicen «lector = Kavita»; es una premisa anterior al
  2026-11-14. No se reescriben por esta ficha, pero no deben citarse como estado vigente.

---

## 11. Trazabilidad

- Épica **#822** (BL-LEC) y subhistorias **#823** (LEC0), **#824** (LEC1), **#825** (LEC2),
  **#826** (LEC3), **#827** (LEC4, fusionada el 2026-11-17 en la PR #1056) y **#828** (LEC5).
- **Anexo A**: fichas de las 13 aplicaciones del benchmark (12 del informe más KOReader), con
  su papel, lo verificado y el veredicto.
- Ficha de servido y decisiones de implementación:
  [`benchmark-BL-LEC-lector.md`](benchmark-BL-LEC-lector.md) (matriz §9, medición §12,
  decisiones D-L1–D-L4 §11).
- ADR 0001 (UI con HTMX), ADR 0004 (exposición de red), ADR 0012 (credenciales), ADR 0013
  (fuentes apagadas por defecto), ADR 0015 (lector de RAR con `unar`) y **ADR 0021
  (JavaScript propio del lector)**.
- C5 ([`especificacion-BL-C5-opds.md`](especificacion-BL-C5-opds.md)), WK5
  ([`spike-kavita-343.md`](spike-kavita-343.md)), B20
  ([`B20-exportacion-kavita.md`](B20-exportacion-kavita.md)).
- **Pendiente cuando el PO la acepte:** enlazarla desde #822/#828 (el tablero no se toca
  desde este documento). Por su alcance, va en una **PR solo de documentos** antes de abrir
  la siguiente historia de lector (regla de §13).
- **Anexo B — features del lector para la biblioteca:** cinco candidatas publicadas como
  [#1076](https://github.com/juanajok/zascarr/issues/1076) (agrupación) e
  [#1077](https://github.com/juanajok/zascarr/issues/1077)–[#1081](https://github.com/juanajok/zascarr/issues/1081)
  (historias), en Backlog; las aplazadas y bloqueadas quedan documentadas en el anexo.
- **Historias derivadas:** la épica [`epica-BL-LECUX-lector.md`](epica-BL-LECUX-lector.md)
  recoge las candidatas de §7.4 y los huecos de acabado del lector; está **publicada para
  triaje** como [#1067](https://github.com/juanajok/zascarr/issues/1067) con las historias
  [#1068](https://github.com/juanajok/zascarr/issues/1068)–[#1073](https://github.com/juanajok/zascarr/issues/1073)
  (estado Backlog), y sigue **sin aprobar**: el PO decide prioridad y D-LUX.
- Fuentes externas verificadas el 2026-11-17: [releases de Kavita](https://github.com/Kareadita/Kavita/releases/tag/v0.9.1.4)
  y [su wiki de OPDS](https://wiki.kavitareader.com/guides/features/opds/); [Komga 1.30.1](https://github.com/gotson/komga/releases/tag/1.30.1),
  [sus guías de OPDS](https://komga.org/docs/guides/opds), [Chunky](https://komga.org/docs/guides/chunky/),
  [Mihon](https://komga.org/docs/guides/mihon), [KOReader](https://komga.org/docs/guides/koreader) y
  [KMReader](https://komga.org/docs/guides/kmreader/); [OPDS en Panels](https://panels.app/opds-client);
  [TritonPanels](https://tritonpanels.tritonapps.com); [YACReader 10.5.1](https://github.com/YACReader/yacreader/releases/tag/10.5.1)
  y [su issue #98](https://github.com/YACReader/yacreader/issues/98); [OpenComic 2.0.0](https://github.com/ollm/OpenComic/releases/tag/v2.0.0)
  y [su IA local](https://opencomic.app/docs/guides/ai/); [CDisplayEx](https://www.cdisplayex.com/).

---

## Anexo A — Aplicaciones del benchmark

El informe del PO agrupaba las aplicaciones en «lectores», «gestores de biblioteca» y
«servidores y ecosistemas». Varias hacen dos cosas a la vez (YACReader es lector y gestor;
Kavita y Komga son gestores y servidores), así que aquí van una a una, con el papel que
cumplen y el veredicto de esta ficha. **No se reproduce** la tabla cualitativa del
informe (lectura/biblioteca/metadatos/servidor/sincronización): no se pudo verificar y la
decisión de ZascArr se toma por idea (§4), no por nota de aplicación.

### A.1 Matriz de aplicaciones

| Aplicación | Papel principal | OPDS catálogo | OPDS-PSE | Sync de progreso | Veredicto para ZascArr |
|---|---|---|---|---|---|
| **CDisplayEx** | Lector Android/Windows | ❌ | — | Solo API de Kavita (`NOT RUN`) | **Descartar** como app; su idea de «siguiente» está en LEC3 |
| **Chunky** | Lector iPad | ✅ | ✅ 1.0 | ❌ | **Adoptar** como cliente de prueba de LEC5 (previo pago) |
| **ComicScreen** | Lector/explorador Android | `NOT RUN` | `NOT RUN` | — | **Descartar** |
| **KMReader** | Cliente de Komga (Apple) | Solo Komga | — | Solo Komga | **Descartar** para ZascArr; referencia de cliente de servidor |
| **Kavita** | Gestor + servidor + lector web | ✅ | ✅ (OPDS-PS) | Vía API de Kavita | **Construir sobre lo propio / Adaptar** como referencia; no se integra |
| **KOReader** | Lector multiplataforma | ✅ | ✅ | Por API dedicada, no por OPDS | **Adoptar** como cliente de prueba de LEC5 (gratis) |
| **Komga** | Gestor + servidor | ✅ 1.2 | ✅ (PSE 1.2) | Vía API de Komga | **Adoptar** como referencia de contrato; **Descartar** integrarlo |
| **Mihon** | Lector de manga Android | ❌ nativo | ❌ | Por capítulo, vía API | **Descartar** (no valida PSE) |
| **OpenComic** | Lector de escritorio | `NOT RUN` | `NOT RUN` | — | **Descartar** como app; **Adaptar** la idea de filtros |
| **Panels** | Lector Apple | ✅ 1.x | ✅ 1.0/1.1 | Solo API de Komga/Kavita | **Adoptar** como referencia de UX y cliente de prueba |
| **Perfect Viewer** | Lector Android | El informe dice ✅; `NOT RUN` | `NOT RUN` | — | **Descartar** como app; **Adaptar** la idea de filtros |
| **TritonPanels** | Cliente Komga/Kavita (iOS/Android) | ✅ | ❌ | API nativa de Komga/Kavita | **Descartar** para PSE; referencia si se abre API de progreso |
| **YACReader** | Gestor + lector + servidor propio | ❌ (#98) | ❌ | Contra su propio servidor | **Construir sobre lo propio** como referencia; **Descartar** integración |

### A.2 Fichas de aplicación

#### CDisplayEx

- **Qué es.** Lector de Android y Windows, propietario y vivo (Android 1.3.96, 2026-09-12).
- **Lo que le atribuye el informe.** Lectura rápida de CBZ/CBR/PDF, agrupación por series,
  «siguiente álbum», carpetas de red, OneDrive/Dropbox/Komga/Kavita/Mega en Pro, modo
  nocturno y compatibilidad con S-Pen.
- **Comprobado.** Sigue vivo y **no ofrece OPDS**; conexión a Kavita por API. El resto de
  conexiones cloud/Komga/Mega y el sync: **NOT RUN**.
- **Para ZascArr.** La idea «al acabar, seguir con el siguiente álbum» ya está en LEC3
  (#826) con la numeración propia; no hay nada más que copiar.
- **Veredicto.** **Descartar** como aplicación de referencia.

#### Chunky

- **Qué es.** Lector de iPad, propietario; el OPDS exige compra dentro de la app (3,99 $
  según la documentación de Komga).
- **Lo que le atribuye el informe.** Reescalado inteligente, corrección de contraste y
  color, biblioteca autoorganizada y descargas en la nube.
- **Comprobado.** OPDS de catálogo y **PSE 1.0**; **no sincroniza progreso**. La
  incompatibilidad documentada es de **Komga 1.4.0+**, no de Chunky (§2.3).
- **Para ZascArr.** Cliente válido para el criterio 6 de LEC5; su «biblioteca
  autoorganizada» no aporta, porque la biblioteca es de ZascArr.
- **Veredicto.** **Adoptar** como cliente de prueba de LEC5.

#### ComicScreen

- **Qué es.** Lector y explorador de archivos de Android, con publicidad y compras dentro
  de la app.
- **Lo que le atribuye el informe.** ZIP/RAR/CBZ/CBR/PDF, USB OTG, SMB/FTP, miniaturas,
  doble página horizontal, recorte de márgenes y teclas físicas.
- **Comprobado.** Sigue vivo en Play; versión, licencia, precio, OPDS y PSE: **NOT RUN**.
- **Para ZascArr.** El acceso a archivos locales no aplica a un servidor; lo que aporta
  (recorte, teclas) no justifica nada nuevo.
- **Veredicto.** **Descartar**.

#### KMReader

- **Qué es.** Cliente nativo de **Komga** para iOS 17+/iPadOS 17+/macOS 14+/tvOS 17+, MIT.
- **Lo que le atribuye el informe.** Varios servidores Komga, descargas en segundo plano,
  colecciones offline, búsqueda avanzada, lector DIVINA y EPUB nativo.
- **Comprobado.** Existe, con esas plataformas y relación exclusiva con Komga.
- **Para ZascArr.** No aplica salvo que se imitara la API de Komga (fuera de alcance); su
  lista de funciones sirve como barra de UX para un cliente de servidor.
- **Veredicto.** **Descartar** para ZascArr; referencia de cliente de servidor.

#### Kavita

- **Qué es.** Gestor + servidor + lector web; GPL-3.0; 0.9.1.4 (2026-09-02); el spike de
  WK5 midió contra 0.9.0.2 en la Pi.
- **Lo que le atribuye el informe.** Bibliotecas por tipo de contenido, indexación,
  ComicInfo, metadatos, búsqueda, filtros, colecciones, listas, valoraciones, progreso,
  lectura web, anotaciones, usuarios/permisos y OPDS; Kavita+ añade extras de pago.
- **Comprobado.** OPDS por usuario con AuthKey y **OPDS-PS**; API REST con OpenAPI; Panels,
  TritonPanels, Mihon y KOReader sincronizan por API. El alcance de Kavita+ es **NOT RUN**.
- **Para ZascArr.** Referencia de biblioteca y servidor (ya usada en fichas anteriores);
  leer en Kavita sigue siendo una opción del usuario, no la vía propia; el sync es WK5 y
  sigue descartado por ahora.
- **Veredicto.** **Construir sobre lo propio / Adaptar** como referencia; no se integra.

#### KOReader

- **Qué es.** Lector multiplataforma (e-readers, Android y escritorio), libre; **no estaba
  en el informe del PO** y se añadió al verificar los clientes OPDS-PSE.
- **Lo que le atribuye el informe.** Nada: no está en el informe.
- **Comprobado.** OPDS y **PSE** (Komga lo lista como cliente); el progreso se sincroniza
  por API dedicada, no por OPDS.
- **Para ZascArr.** Es el único cliente **gratis** verificado con OPDS y PSE: la primera
  opción para el criterio 6 de #828.
- **Veredicto.** **Adoptar** como cliente de prueba de LEC5.

#### Komga

- **Qué es.** Gestor + servidor; MIT; 1.30.1 (2026-11-10).
- **Lo que le atribuye el informe.** Bibliotecas, series, colecciones y listas; indexación
  de CBZ/CBR/PDF/EPUB; edición de metadatos; ComicInfo; lector web; estado de lectura; OPDS
  y clientes de terceros; gestión centralizada.
- **Comprobado.** OPDS 1.2 (PSE 1.2) y OPDS 2.0; API REST; sus guías de cliente son la
  mejor referencia de compatibilidad.
- **Para ZascArr.** Referencia de arquitectura servidor-cliente y de PSE (ya estudiada en la
  ficha BL-LEC §4); no se integra.
- **Veredicto.** **Adoptar** como referencia de contrato; **Descartar** integrarlo.

#### Mihon

- **Qué es.** Lector de manga para Android, Apache-2.0.
- **Lo que le atribuye el informe.** Lectura manga, seguimiento con AniList/MyAnimeList,
  categorías, copias de seguridad y lectores configurables.
- **Comprobado.** **Sin OPDS nativo**; usa extensión de Komga o API de Kavita; sync por
  capítulo.
- **Para ZascArr.** No puede validar PSE; sus funciones son de ecosistema manga y no
  encajan en una tebeoteca CBZ/CBR.
- **Veredicto.** **Descartar**.

#### OpenComic

- **Qué es.** Lector de escritorio (Windows/macOS/Linux), GPL-3.0, 2.0.0 (2026-11-14).
- **Lo que le atribuye el informe.** CBZ/CBR/CB7/CBT/ZIP/RAR/7Z/PDF/EPUB, doble página,
  Guided View, manga/webtoon, SMB/FTP/SFTP/SSH/WebDAV/S3, OPDS, pestañas, marcadores, lupa,
  filtros de imagen, colorización, tracking AniList/MyAnimeList y mandos.
- **Comprobado.** **IA local nativa** (modelos propios y de terceros descargados, sin
  servicio en la nube); OPDS según el informe y PSE: **NOT RUN**; la colorización concreta:
  **NOT RUN**.
- **Para ZascArr.** Es la barra más alta de funciones de escritorio, pero su IA y su coste
  no caben en la Pi; se toma la idea de filtros (§7.4) y se descarta el resto.
- **Veredicto.** **Descartar** como app; **Adaptar** la idea de filtros.

#### Panels

- **Qué es.** Lector Apple (iPhone/iPad/Mac), propietario; el OPDS requiere Panels+ o
  compra dentro de la app.
- **Lo que le atribuye el informe.** Interfaz cuidada, bibliotecas, iCloud/Dropbox/OneDrive,
  CBZ/CBR/CB7/PDF/EPUB, OPDS/Komga/Kavita, lectura guiada, manga RTL, temas, Face ID, modo
  incógnito y filtros de escaneo (ruido, nitidez, moiré, recorte de bordes).
- **Comprobado.** OPDS 1.x y **PSE 1.0/1.1**; sync solo por API de Komga/Kavita; **no hay
  Android comprometido**.
- **Para ZascArr.** Referencia principal de UX de lector y cliente prioritario (con coste)
  para LEC5; sus filtros alimentan la candidata de §7.4.
- **Veredicto.** **Adoptar** como referencia de UX y cliente de prueba; no se copia la
  interfaz.

#### Perfect Viewer

- **Qué es.** Lector de Android, cerrado y veterano.
- **Lo que le atribuye el informe.** Formatos varios, SMB/FTP/SFTP/OPDS, plugins de nube,
  modos de lectura, LTR/RTL, doble página, biblioteca tipo estantería, favoritos, caché de
  páginas, recorte, brillo/contraste/gamma, lupa y Chromecast.
- **Comprobado.** Vivo en Play; versión, licencia, precio, OPDS y PSE: **NOT RUN**.
- **Para ZascArr.** Solo ideas sueltas (filtros de imagen, caché de páginas); no sirve para
  validar LEC5 sin una prueba real.
- **Veredicto.** **Descartar** como app; **Adaptar** la idea de filtros.

#### TritonPanels

- **Qué es.** Cliente de Komga/Kavita para iOS 17+/Android 7+, de suscripción (14 días de
  prueba).
- **Lo que le atribuye el informe.** Conexión directa a Komga/Kavita con sync bidireccional,
  OPDS/Calibre, Google Drive/Dropbox/OneDrive, SMB y local, offline, panel a panel, modos,
  manga RTL, filtros, marcadores/notas y estadísticas.
- **Comprobado.** OPDS de catálogo sí y **sin PSE**; el sync bidireccional es solo por API
  nativa; por OPDS genérico el progreso se queda en el dispositivo.
- **Para ZascArr.** Valida el catálogo OPDS, no el streaming; su sync exigiría imitar la API
  de Komga/Kavita (fuera de alcance).
- **Veredicto.** **Descartar** para PSE; referencia si algún día se abre una API de progreso.

#### YACReader

- **Qué es.** Gestor + lector de escritorio (Win/macOS/Linux), apps iOS/Android y servidor
  Docker propio; GPL-3.0; 10.5.1 (2026-11-13).
- **Lo que le atribuye el informe.** Biblioteca visual, Comic Vine, ComicInfo, buscador,
  listas, seguimiento, edición masiva, automatización, lector avanzado, mejora de escaneos,
  sync entre dispositivos y servidor NAS.
- **Comprobado.** Su sync es contra **su propio servidor**; la WebUI trae un lector web «muy
  básico» desde 10.2.0; **sin OPDS** (*feature request* #98 abierto desde 2019).
- **Para ZascArr.** Referencia de gestión de biblioteca (ya cubierta por fichas anteriores);
  no es cliente OPDS ni sirve para LEC5, y su modelo de sync no aplica.
- **Veredicto.** **Construir sobre lo propio** como referencia; **Descartar** su
  integración.

---

## Anexo B — Features del lector con valor para la biblioteca

> **Pregunta del PO (2026-11-17):** ¿qué funciones de los lectores y gestores del benchmark
> sirven para **gestionar la biblioteca** —catálogo, estado de lectura, organización— y no
> solo para leer?
> **Método:** revisión del código en `main` `4b64637e` (sin ejecutar apps ni tocar la Pi) y
> las fichas de la épica BL-LEC. No es una historia: es una extensión del benchmark.
> **Resultado:** **5 candidatas** (3 sin migración; 2 con decisión de PO), **2 aplazadas** y
> **2 que no son del lector**. Tarjetas publicadas: agrupación
> [#1076](https://github.com/juanajok/zascarr/issues/1076) e historias
> [#1077](https://github.com/juanajok/zascarr/issues/1077)–[#1081](https://github.com/juanajok/zascarr/issues/1081),
> en el tablero con estado **Backlog**.

### B.1 Lo que ya está cubierto (no se reabre)

| Función del lector/gestor | Dónde está en ZascArr |
|---|---|
| Bloqueo de campos para que el enriquecimiento no pise lo editado (Kavita) | `locked_fields` en `Series`, `Creator` e `Issue`; lo respetan ComicInfo y la consolidación |
| Progreso de lectura por serie en la tarjeta | barra «% leído · X de Y» en `_rejilla_biblioteca.html` |
| Filtros de leído/leyendo y favoritos | `web/library.py` y `_filtros_panel_campos.html` |
| Colecciones de series y sagas | BL-D6 y C4; las tablas de **listas de lectura** existen pero no se usan (B.3.4) |
| ComicInfo, metadatos y procedencia | B6, ADR 0013 y B22 |
| «Continuar leyendo» | Inicio (CUR5) y botón «Continuar» en la ficha |

### B.2 Candidatas

| # | Feature | De dónde | Uso en la biblioteca | Estado hoy | Coste | Veredicto |
|---|---|---|---|---|---|---|
| 1 | Filtrar y ordenar por puntuación | Kavita/Komga | «mejores valorados», «sin valorar» | la puntuación 1–5 existe; la biblioteca no la expone | S, sin migración | **Adoptar** → [#1077](https://github.com/juanajok/zascarr/issues/1077) |
| 2 | Archivo preferido por número | nace de LEC1, no del informe | elegir qué archivo abre «Leer» en números con ediciones | `archivo_por_defecto`: progreso o el primero por nombre | S, sin migración (JSONB) | **Adoptar** → [#1078](https://github.com/juanajok/zascarr/issues/1078) |
| 3 | Páginas reales del archivo | Panels/Chunky/OpenComic muestran páginas | porcentaje de lectura y `PageCount` correctos | el lector calcula `total_paginas`; no lo persiste | S, sin migración | **Adoptar** → [#1079](https://github.com/juanajok/zascarr/issues/1079) |
| 4 | Listas de lectura | YACReader/Komga/Kavita | listas curadas que cruzan series; alimentan el «siguiente» de LEC3 | `reading_lists` existe desde la migración 0001 y está **sin uso** | M, sin migración | **Adaptar** (decisión PO) → [#1080](https://github.com/juanajok/zascarr/issues/1080) |
| 5 | Filtrar y ordenar por última lectura | lectores con «continuar» | retomar lo empezado y ordenar por actividad | no hay `last_read_at`; `started_at` no se actualiza | M, **con migración** | **Adaptar** (decisión PO) → [#1081](https://github.com/juanajok/zascarr/issues/1081) |
| 6 | Vistas guardadas / filtros guardados | Kavita (*smart filters*) | repetir consultas en una biblioteca grande | los filtros viven solo en la URL | M | **Aplazar** |
| 7 | Marcar leído en lote | gestores | poner al día el estado sin ir número a número | BL-C3 solo uno a uno | S/M | **Aplazar** |
| 8 | Progreso desde Kavita | Kavita (WK5) | no marcar dos veces lo leído | spike #343 descartado con condiciones; LEC5 no devuelve progreso | L | **No ahora** |
| 9 | Progreso/estado de un pack | — (no es del lector) | números cubiertos por un archivo | `covered_issue_ids` se inicializa vacío; B22 abierta | — | **Bloqueado por B22** |

### B.3 Detalle por candidata

#### B.3.1 Puntuación ([#1077](https://github.com/juanajok/zascarr/issues/1077))

- **Problema.** La puntuación 1–5 por número existe (`reading_progress.rating`, BL-C3), pero
  los filtros no la incluyen y el orden de `web/library.py` solo ofrece título, año y
  añadidas. No se puede consultar «mejores valorados» ni «sin valorar».
- **Propuesta.** Filtro «Puntuación» a nivel de serie (la serie entra si algún número
  cumple), con opciones «Todas / Con valoración / Sin valorar / 4–5»; orden «Mejor valoradas»
  por máximo de la serie, con `NULL` al final. URL canónica, chips y recuento como BL-IT01.
- **Coste y límites.** S, sin migración; una consulta agregada, sin N+1.
- **Decisión PO.** Semántica del filtro (máximo por serie propuesto) y set de opciones.

#### B.3.2 Archivo preferido ([#1078](https://github.com/juanajok/zascarr/issues/1078))

- **Problema.** `services/lector.py::archivo_por_defecto` elige el archivo del progreso o el
  primero por nombre. En un número con varias ediciones no hay forma de decir «para leer,
  este».
- **Propuesta.** Marcar un archivo legible como «Archivo para leer» en la ficha; guardarlo en
  `Issue.metadata_["lector_archivo"]` (JSONB, sin migración); prioridad preferido → progreso
  → primero, con fallback si desaparece.
- **Coste y límites.** S; no duplica el progreso ni escribe en la biblioteca.
- **Decisión PO.** JSONB (propuesto) frente a columna; ubicación del control.

#### B.3.3 Páginas reales ([#1079](https://github.com/juanajok/zascarr/issues/1079))

- **Problema.** `Issue.page_count` viene de ComicInfo, fuente o tagger y puede faltar o no
  coincidir con el archivo; el lector calcula `total_paginas` al abrir pero no lo guarda.
- **Propuesta.** Al guardar progreso (el `POST` que ya existe, nunca un `GET`), rellenar
  `Issue.page_count` si es `NULL`, con `metadata_["page_count_origen"]="lector"`. No pisar un
  valor existente; con varios archivos de distinto total, no escribir.
- **Coste y límites.** S; sin migración; no recorre la biblioteca entera.
- **Decisión PO.** Rellenar huecos (propuesto) frente a sobrescribir.

#### B.3.4 Listas de lectura ([#1080](https://github.com/juanajok/zascarr/issues/1080))

- **Problema.** `reading_lists` y `reading_list_items` existen desde la migración 0001 y no
  se usan en ninguna ruta. YACReader/Komga/Kavita ofrecen listas; ZascArr tiene colecciones
  de series (BL-D6) y sagas (C4), pero no una lista curada de números que cruce series.
- **Propuesta.** CRUD de listas e ítems, añadir desde la ficha del número, reordenar con
  `position`, progreso leído/total; entrada de navegación a decidir.
- **Coste y límites.** M, sin migración. **No es una cola de lectura** (descartada en el
  backlog): es una lista curada.
- **Decisión PO.** Alcance, navegación, relación con colecciones/sagas y si LEC3 usará el
  «siguiente de la lista».

#### B.3.5 Última lectura ([#1081](https://github.com/juanajok/zascarr/issues/1081))

- **Problema.** `ReadingProgress` tiene `started_at` y `completed_at`, pero no una fecha de
  última actividad; «continuar leyendo» usa `started_at`, que no refleja el avance.
- **Propuesta.** Migración aditiva `reading_progress.last_read_at`, actualizada al guardar
  progreso y al marcar estado; orden «Leídas recientemente» en Biblioteca; relleno inicial
  desde `started_at`/`completed_at` o `NULL` (decisión PO).
- **Coste y límites.** M con migración; no es historial ni estadísticas.
- **Decisión PO.** Aceptar la migración y su política de relleno.

### B.4 Aplazado, bloqueado y descartado

- **Vistas guardadas** (Kavita *smart filters*): útiles cuando la biblioteca crezca, pero hoy
  los filtros de BL-IT01 cubren el caso; sin tarjeta hasta que el PO lo pida.
- **Marcar leído en lote**: útil para poner al día el estado, pero no nace del benchmark y
  exige decidir la semántica de «anteriores»; sin tarjeta.
- **WK5 (progreso desde Kavita)**: sigue descartado con condiciones (spike #343); B20 está
  fusionado pero sin uso real, y OPDS-PSE no devuelve progreso. No es una historia nueva.
- **Progreso de un pack**: no es una feature de lector; `File.covered_issue_ids` se inicializa
  vacío y no tiene procedencia. Queda bloqueado por **B22** (modelo de coberturas).
- **Descartado de raíz**: estadísticas e historial de lectura, anotaciones y subrayados,
  búsqueda OCR dentro del cómic (coste imposible en la Pi), cola de lectura separada de
  Deseados y sincronización de anotaciones con apps. Ya estaban fuera en §7.5 y en el
  backlog.

### B.5 Límites

- No se ha ejecutado ninguna app ni se ha medido uso real: las conclusiones son de código y
  del benchmark, no de una prueba en vivo.
- Las tarjetas son **propuestas en Backlog**; el PO decide prioridad, alcance y migraciones.
- Caducidad: la misma de esta ficha (~60 días, 2027-01-16), o antes si cambia el modelo de
  lectura (LEC3/LECUX2/B22).

---

**Autor:** Lead de la sesión de agentes, a partir del informe aportado por el PO y de la
verificación documental indicada. **Insumo, no aprobación:** decide el PO.
