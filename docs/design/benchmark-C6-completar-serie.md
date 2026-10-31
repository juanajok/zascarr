# Ficha de benchmarking — C6: completar una serie

> Ficha de **nivel 2** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13).
> **Historia:** #152 (BL-C6) · **Fecha:** 2026-10-30 · **SHA contrastado:** `d43b1f7d` (`origin/main`).
> Desde `2dd2d1d` (primer contraste) hay 23 commits; ninguno cambia D8, el ciclo de búsqueda ni la
> ficha de serie en los ficheros citados aquí (solo avisos de disco y portadas), y se han
> actualizado los números de línea. **Caduca:** ~60 días, o antes si cambia D8, la historia o
> una referencia. Esta ficha es insumo: no autoriza implementar; decide el PO.

## Decisiones del PO que fijan el problema (2026-10-30)

1. «Completar» es una **política permanente de la serie** (cambia la política guardada, como D8), no un comando puntual.
2. El ritmo es un **límite de seguridad (rate limit), no una cadencia**: 2 ítems por hora, en **ventana deslizante**, contados **por ítems** (cada ítem puede suponer hasta dos peticiones externas: indexador y foro, que no cuentan aparte).
3. Lo que genera la política tiene **prioridad 8**, detrás de lo pedido a mano (5).
4. La **puerta legal** se exige **solo para activar** la política (nunca para desactivarla), en el manejador de `cambiar_politica`; el ciclo **conserva** además su comprobación actual (`is_acknowledged` antes de generar y de buscar): son dos barreras. Dictamen de seguridad: recomendado, no bloquea.
5. La cota de tiempo se muestra **en días, redondeada hacia abajo** (redondear hacia arriba haría falsa una cota inferior).
6. El motivo de las series no calculables sigue la **variante V-B**: la frase lleva entre paréntesis el nombre público de la fuente («viene de AniList», «viene de Tebeosfera», «viene de GCD», «viene del propio archivo», «alta a mano», «sin fuente») y el valor interno solo aparece en un `<details>` plegado, justo después del párrafo del veredicto.
7. El selector **sigue ofreciendo «completar»** en series no calculables, con el motivo visible.

## Historia / problema observado

La historia pedía «un botón en cada serie que detecte los números que me faltan y los ponga todos en búsqueda». **D8 (cerrada el 2026-09-30) ya hace gran parte**: la ficha de serie tiene el selector «Buscar los números que me faltan» y el ciclo genera desde los huecos. Lo que falta es explicar la política, estimar el tiempo con honestidad, formular el límite de ritmo y decir por qué no se puede en series sin huecos calculables.

## Comportamiento actual (contrastado en `d43b1f7d`; leído en código, no ejecutado)

| Pieza | Hoy | Dónde |
|---|---|---|
| Huecos con regla de fiabilidad (`computable`) | Sí. Solo cuenta si `total_issues > 0` y la fuente es Comic Vine (`UNIDAD_DE_GRAPA`) | `services/series.py::huecos_de_serie`, `:129` |
| Predicado único «qué quiere la política ahora» | Sí | `services/politica.py::querer_de_serie` (`:91`) |
| Selector en la ficha: «No buscar nada por mi cuenta» / «Buscar los números que me faltan»; «Se guarda al elegir» | Sí | `web/series.py:66, 145`, `_politica_serie.html` |
| Política permanente | Sí: se reevalúa en cada ciclo | `orchestrator.py::_series_para_sincronizar` (`:609`) |
| Generación | Hasta 25 por ciclo, repartida entre series | `config.py:168`, `orchestrator.py::_generar_lo_que_falta` |
| **Búsqueda: ritmo** | Cada ciclo busca `limit` ítems; el ciclo corre cada `scan_interval_minutes` (60) y `limit` es `max_concurrent_downloads` (2), un ajuste que **no se usa en ningún otro sitio** | `config.py:155, 157`, `main.py:264`, `orchestrator.py:137-157` |
| Cooldown por ítem | 6 h | `config.py:162` |
| Orden de la cola | `priority` y luego `added_at`; lo generado entra con `priority=5` | `orchestrator.py:155, 714` |
| Retirada | Atómica; solo `WANTED`/`FAILED` de origen política. Lo que ya está `SEARCHING`/`DOWNLOADING` no se retira | `politica.py::stmt_retirada` (`:145`) |
| Cierre «descargado → en la biblioteca» | Sí | `orchestrator.py::check_completions` (`:744`) |
| Puerta legal | El ciclo la comprueba (`is_acknowledged`). `cambiar_politica` no lleva `require_legal_acknowledgment` | `orchestrator.py:137+`, `web/series.py:145` |
| Veredicto de la ficha | Dice cuántos faltan y el tope de **generación** (25); no el ritmo de búsqueda ni cuánto tardará | `_politica_serie.html` |
| Series no calculables | La ficha dice «No sabemos cuáles faltan: {motivo}», con el identificador interno de la fuente, y el selector sigue ofreciendo la política | `series_detail.html:16-27`, `huecos_de_serie` |

## Medición en la instalación (Pi), 2026-10-30

Lectura agregada de solo lectura, solo recuentos, sin títulos ni rutas; **aportada por el equipo, no ejecutada por quien redacta la ficha**.

| Dato | Valor |
|---|---|
| Series | 19 |
| Con `total_issues > 0` | **1** (fuente `gcd`, no computable) |
| **Computables** (`total_issues > 0` y `comic_vine`) | **0** |
| Por fuente | tebeosfera 11 (american 6, tebeo 3, franco_belgian 1, manga 1) · comic_vine 6 (american 5, franco_belgian 1; **ninguna con total**) · manual 1 · gcd 1 (con total) |
| Política | ninguno 15 · faltantes 4 |
| Las 4 con `faltantes` | **ninguna es computable**: hoy «completar» no genera nada en esta instalación |

**Límites:** una sola instalación, probablemente no toda la biblioteca real; no se cruzó la política con la fuente de cada serie; el valor por defecto de `config.py` (2 ítems por ciclo, ciclo de 60 min) no se ha comprobado en la Pi.

**Conclusiones:**
1. **El problema real no es solo la unidad.** 18 de 19 series no tienen total. Acreditar la unidad de Tebeosfera (11 series, la mayoría) no bastaría: sigue sin haber número total. La historia aparte de «series no calculables» debe empezar por **de dónde sale el total** (cobertura del enriquecedor) y después por la unidad por fuente y tradición. Hay que medir, además, si Tebeosfera ofrece total.
2. **El efecto diferido (O-2) no es hipotético.** Las 4 series con `faltantes` están hoy inertes y hay 6 series de Comic Vine sin total. Si el enriquecedor les asigna uno, el predicado pasa a ser computable y el ciclo empezará a generar números sin que nadie lo espere. Recomendación: avisarlo al activar la política en una serie no calculable y decidir con UX si el selector debe ofrecerla ahí.
3. **El selector ofrece hoy una opción inerte** en el 100 % de las series de la instalación: refuerza el requisito de explicar el motivo.

## Referencias consultadas (versión/commit, a 2026-10-30)

| Referencia | Versión / commit | Licencia | Estado |
|---|---|---|---|
| Sonarr | `43d500c0` (etiqueta `v6.4.4.10685`) | GPL-3.0 | activo |
| Kapowarr | `c191dda6` (`V1.3.2`) | GPL-3.0 | activo |
| Mylar3 | `cdc94a44` (`v0.8.3`) | GPL-3.0 o posterior | casi inactivo (último commit 2025-08-17) |
| Comicarr | `7f1e8791` (`v0.50.1`) | GPL-3.0 o posterior | activo, joven |
| Omnibus | `6055d6e` (`v1.4.9`) | GPL-3.0 | activo, joven |
| Jellyfin | `f62045f5` (`v12.4`) | GPL-2.0 | activo |
| Kodi | `af9ff93d` | GPL-2.0 o posterior | activo |
| ComiXed | `cd31240` (`v4.0.0`) | GPL-3.0 | activo |
| Comic Library Utilities | `abd29d2` (`v7.0`) | GPL-3.0 | activo |
| Tranga | `7986e3c` (`1.5`) | GPL-3.0 | activo |
| Suwayomi | `6b481e8` | MPL-2.0 | activo |
| Kaizoku | `fc86b7d` | MIT | **archivado** (2025-02-03) |

No examinados: Radarr, Kavita, Komga y Codex. Inspirarse en un patrón no es copiar código (barrera legal del procedimiento); el fork `yann-denis/comic-utils` está parado desde 2025-11-05, por eso se examinó el original.

## Cómo lo resuelve cada una

- **Sonarr.** Separa el *estado monitorizado* (persistente) de la *orden de buscar* (puntual). `MonitorTypes`: `All`, `Future`, `Missing`, `Existing`, `None` (`Tv/MonitoringOptions.cs:13-32`); **`Missing` equivale a la política `faltantes` de D8**. Busca monitorizados sin fichero y ya emitidos (`SeriesSearchService.cs`). Confirma con recuento (`en.json:2171-2172`); la búsqueda de faltantes carga sin tope (`EpisodeSearchService.cs:140`, `PageSize = 1000000`).
- **Kapowarr.** Unidad volumen/número, como ZascArr. «Auto Search» por volumen sobre los **números abiertos** (monitorizados y sin fichero, `get_open_issues()`); un volumen no monitorizado no busca (≈ `ninguno`). Con packs elige la combinación que cubre más números (`choose_downloads`).
- **Comicarr.** Vista previa → confirmar de «buscar todos los que faltan» (`app/search/bulk.py`: token de un solo uso, 15 min, huella de la selección). Pasadas acotadas (`search/backlog.py`: presupuesto de elementos y de tiempo; **una pasada que solapa con otra se salta en vez de apilarse**). Pantalla de incidencias con acciones `retry`, `search_again`, `import`, `stop_wanting` (`app/attention/`).
- **Omnibus.** «Request Missing» (puntual). Estado de la serie con palabras y consecuencia («Monitored» frente a «In Library», `README.md:453-454`). **Prioridades de cola en tres niveles** (`src/lib/job-priority.ts`: petición individual 1, orden masiva 5, automatismo 10). Excluye lo cubierto por un recopilatorio poseído (`Covers`, editable). Aparca los números sin fecha (`AWAITING_RELEASE`).
- **Mylar3.** Estado por número y marcado masivo por selección (`webserve.py::markissues`); `forceSearch` aparte. Sin recuento ni tope visibles.
- **Jellyfin.** Solo muestra huecos (episodios virtuales); separa `ImportMissingEpisodes` de `ImportUnairedEpisodes`; opt-in por biblioteca y por usuario. No encontré búsqueda ni descarga.
- **Kodi, ComiXed.** Sin huecos ni adquisición en el código examinado. **CLU:** agrupa huecos consecutivos en rangos (`#003–#010`). **Tranga:** tope `MaxConcurrentDownloads − en curso` (README: «Built for AMD64», ARM no garantizado). **Suwayomi:** ajustes `autoDownloadNewChaptersLimit` y `maxSourcesInParallel` (solo vistos en ajustes y pruebas). **Kaizoku:** archivado.

*«No lo encontré» no equivale a «no existe».* Quejas de usuarios (solo títulos de issues, salvo la primera): Sonarr [8071](https://github.com/Sonarr/Sonarr/issues/8071) (confirmación excesiva con pocos elementos; leído), Mylar3 [1515](https://github.com/mylar3/mylar3/issues/1515) («Skipped» se reinicia al refrescar), Kapowarr [216](https://github.com/Casvt/Kapowarr/issues/216) (una descarga atascada bloquea la cola).

## Supuestos de su modelo que NO valen en ZascArr

Episodio/temporada ≠ grapa/tomo · catálogo único con total acreditado (aquí 18 de 19 series no lo tienen) · usuario técnico que entiende «Wanted» · Redis y varios procesos (Omnibus: Node + Rust + BullMQ, choca con ADR-0011) · acciones puntuales con confirmación (la política de ZascArr se deshace al momento).

## Matriz ponderada (nivel 2; 0–5; cada celda mide lo que cuesta y rinde incorporar el patrón a ZascArr)

Pesos por defecto (suman 100): encaje con el flujo del Coleccionista 25 · coste en Pi 20 · seguridad, legalidad y licencia 20 · cobertura del requisito core 15 · adaptabilidad 10 · mantenimiento 5 · lock-in 5. Al ser «completar» una política y no una orden, bajan Encaje y Cobertura de los patrones de acción puntual.

| Criterio (peso) | Sonarr | Kapowarr | Mylar3 | Jellyfin | Kodi | Comicarr | Omnibus | Construir sobre lo propio (D8) |
|---|---|---|---|---|---|---|---|---|
| Encaje (25) | 3: queda el vocabulario de monitorización | 3: queda el predicado de «abiertos» | 2: jerga, marcado por selección | 3: huecos visibles, sin acción | 0 | 3: quedan pasadas acotadas y «dejar de querer» | 3: queda el estado en llano | 5: reutiliza ficha, textos y estados |
| Coste en Pi (20) | 3 | 3 | 3 | 2: depende de TMDb | 0 | 4: presupuesto y salto si solapa | 3: stack no adoptable | 5: sin dependencias nuevas |
| Legal/licencia (20) | 3: GPL-3.0; no modela aviso legal | 4: GPL-3.0 | 4: GPL-3.0+ | 2: GPL-2.0 | 3: GPL-2.0+ | 4: GPL-3.0+ | 4: GPL-3.0 | 4: puerta legal al activar, a dictaminar |
| Cobertura (15) | 4: `Missing` equivale a D8 | 4: mismo predicado | 3 | 1: solo visualiza | 0 | 3: lo suyo era preview/confirm puntual | 4: prioridades y estados útiles | 4: faltan nombre, tiempo, motivo y límite formulado |
| Adaptabilidad (10) | 3 | 5: misma unidad | 3 | 2 | 0 | 4 | 3: `Covers` sería un campo nuevo | 5 |
| Mantenimiento (5) | 5 | 4 | 2 | 5 | 5 | 4 | 4 | 3 |
| Lock-in (5) | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| **Total /100** | **67** | **74** | **60** | **48** | **22** | **73** | **70** | **91** |

Las referencias quedan muy juntas (67–74) y son juicios: no es un ranking entre aplicaciones, solo la distancia con la opción propia.

## Resultado por idea (propuesta; decide el PO)

| Idea | Resultado | Motivo |
|---|---|---|
| Vocabulario de monitorización (Sonarr `Missing`/`Future`/`All`) | **Construir sobre lo propio** | D8 ya lo implementa; `futuros` y `todos` siguen reservados |
| Predicado de «abierto» (Kapowarr: monitorizado y sin fichero) | **Construir sobre lo propio** | Coincide con `querer_de_serie` |
| Límite como presupuesto por pasada que se salta si solapa (Comicarr) | **Adaptar** | Aquí: 2 ítems/hora, ventana deslizante, por ítems, ajuste propio |
| Estado de la serie con consecuencia en una frase (Omnibus) | **Adaptar** | Nombre «completar» + frase: permanente, límite, lo iniciado termina |
| Prioridades por niveles (Omnibus 1/5/10) | **Adaptar** | Prioridad 8 para lo generado, detrás de lo manual (5) |
| Cota inferior de tiempo en días, honesta | **Mejorar** | Ninguna referencia examinada la da (no encontrado); evidencia: el ritmo actual es de 2 ítems por hora |
| Motivo en llano de series no calculables | **Mejorar** | Todas asumen catálogo con total; aquí 18 de 19 series no lo tienen |
| Cobertura por recopilatorio (Omnibus `Covers`) | **Adaptar**, historia aparte | Toca el modelo de datos; hoy un ómnibus no cubre el hueco de la grapa (regla de C2) |
| Rangos en listas largas (CLU) | **Adaptar** (opcional) | Barato, sin tocar datos |
| Vista previa y confirmación (Comicarr, Sonarr) | **Descartar** para C6 | Su acción no se deshace; la política de D8 sí |
| Orden puntual «buscar ahora» (Sonarr, Kapowarr, Omnibus) | **Descartar** | Decisión del PO: política permanente |
| Futuros separados de faltantes (Jellyfin, Sonarr `Future`) | **Descartar** por ahora | `futuros` sigue reservado en D8 |
| Marcado masivo por selección (Mylar3); Kodi, ComiXed, Tranga, Suwayomi, Kaizoku, Radarr | **Descartar** para C6 | Otra unidad, sin huecos, archivada o sin examinar |

**Veredicto de conjunto: construir sobre lo propio (D8).** Lo que falta es pulido, no un mecanismo nuevo; sin tabla ni dependencia nueva para lo esencial (a verificar al especificar). **Sobrecoste asumido:** «completar» para series sin total o con cobertura por recopilatorio es otra historia (modelo de datos y cobertura del enriquecedor).

## IGUALAR (mínimo competitivo)
1. La política se calcula con el mismo predicado que genera y retira; la ficha no recalcula por su cuenta. *(Ya se cumple.)*
2. El estado de la serie se dice con palabras y su consecuencia en una frase.
3. Lo ya poseído y lo pedido a mano no se vuelve a pedir. *(Ya se cumple.)*
4. Lo lanzado queda visible por número con estado y motivo. *(Ya se cumple.)*
5. Límite de ritmo y cooldown respetados siempre.
6. «Cumplido» = el fichero entró en la biblioteca. *(Ya se cumple.)*

## MEJORAR (ordenado por oportunidad; con evidencia arriba)
1. **Nombre y explicación de la política.** Hoy no aparece «completar» y «se para al momento» promete de más: un ítem `SEARCHING`/`DOWNLOADING` no se retira.
2. **Cota de tiempo honesta**, en días hacia abajo. Con 2 ítems por hora, 40 pendientes son ≥ 20 h (menos de un día) y 100 son ≥ 50 h (2 días); nunca «tardará».
3. **Límite de ritmo propio**, desacoplado del ajuste de descargas, en ventana deslizante y por ítems (hoy es un lote por ciclo ligado al intervalo del bucle).
4. **Series no calculables**: motivo en llano (V-B) y decisión sobre el selector y el aviso del efecto diferido. La historia aparte empieza por el origen del total.
5. **Prioridad 8** para lo generado.
6. **Cobertura por recopilatorio** y **rangos en listas largas**: historias aparte u opcionales.

## Requisitos propuestos (EARS; semilla para la especificación)
- **FR-1 (ubicuo).** El sistema aplicará la política «completar» (la política `faltantes`) con el predicado `querer_de_serie`, sin cálculo paralelo.
- **FR-2 (ubicuo).** La ficha de la serie presentará la política con un nombre y una explicación en español llano: permanente hasta que se cambie, con un límite de ritmo, y lo ya iniciado termina. *(Texto final de UX en la especificación.)*
- **FR-3 (ubicuo, límite).** El sistema no iniciará más de 2 ítems por hora, en ventana deslizante, contando todas las series con política activa. Cada ítem puede suponer hasta dos peticiones externas, que no cuentan aparte. El límite es un techo: el sistema no está obligado a iniciar 2 ítems por hora ni a buscar con una cadencia concreta. El valor será un ajuste propio, distinto del de descargas simultáneas.
- **FR-4 (estado).** Mientras haya números pendientes de la política, la ficha mostrará cuántos hay y una cota inferior en días, redondeada hacia abajo («no antes de N días»; si sale menos de un día, lo dirá), indicando que puede tardar más o que algún número puede no encontrarse. La cota cuenta las pendientes de buscar (huecos menos lo ya en descarga) de **todas** las series con política activa.
- **FR-5 (estado).** Mientras la serie no sea computable, la ficha dirá en español llano por qué, sin el valor interno de la fuente a la vista (variante V-B: nombre público entre paréntesis en la frase; valor interno solo en un `<details>` plegado tras el párrafo del veredicto, una vez por página y solo con una fuente válida). Con la política en «ninguno» en una serie no calculable, el veredicto añadirá que «completar» tampoco podría buscar nada por ahora.
- **FR-6 (evento).** Al activar la política en una serie no computable, la ficha avisará de que se activará sola si luego se conoce el total. El selector sigue ofreciendo «completar» en esas series, con el motivo visible.
- **FR-7 (no deseado).** Al intentar **activar** la política sin el aviso legal aceptado, el sistema no la activará, dejará el fragmento de la política sin cambios, mostrará el aviso con un enlace a la pantalla legal y responderá con éxito HTTP. Desactivarla nunca exigirá el aviso. El ciclo conserva además su comprobación (dos barreras).
- **FR-8 (ubicuo).** Lo que genere la política tendrá prioridad 8, detrás de las peticiones hechas a mano (5).
- **FR-9 (evento).** Al dejar la política, el sistema retirará lo no iniciado y la ficha dirá cuántos números se retiraron y que lo ya iniciado termina. *(La retirada ya existe; falta el texto de lo iniciado.)*

## Invariantes de ZascArr
No mentir (si no es computable, decirlo; si es una cota, decirlo) · no borrar (retirar conserva el registro) · coste Pi (límite de ritmo y cooldown) · aviso legal · español llano sin identificadores internos.

## Casos de prueba antes de implementar
Propuestos: límite de 2 ítems por hora en ventana deslizante (incluidos los ítems con dos peticiones externas) · el límite no fuerza una búsqueda cuando no hay pendientes · prioridad 8 frente a un alta manual posterior (5) · cota en días redondeada hacia abajo (casos 40 y 100 pendientes) · serie no computable: texto sin identificador de fuente y aviso de activación diferida · activar sin aviso legal · retirada que respeta lo iniciado.

## NOT RUN / no verificado
- Nada ejecutado: ni la suite, ni las aplicaciones de referencia, ni la ficha renderizada en un navegador. El texto de la ficha de serie se leyó en las plantillas.
- La medición de la Pi la aportó el equipo y no se cruzó la política con la fuente de cada serie; el valor por defecto de `config.py` no está comprobado en la Pi.
- Los textos de la variante V-B y la puerta legal vienen de decisiones del PO y de la especificación; no se han visto renderizados.
- El efecto diferido y la sobrepromesa de «se para al momento» son deducciones del código, no pruebas de comportamiento.
- Radarr, Kavita, Komga y Codex sin examinar. Suwayomi: solo nombres de ajustes. ComiXed y Kodi: búsquedas por texto sin coincidencias.
- Debility map incompleto (títulos de issues, salvo Sonarr 8071); madurez, seguridad y rendimiento de Comicarr y Omnibus sin auditar.
- Licencia de Jellyfin («solo» o «o posterior») sin confirmar; licencias leídas de `LICENSE` y cabeceras.
- No comprobado si `/ui/wishlist` distingue el origen (política/manual).
