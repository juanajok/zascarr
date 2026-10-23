# Registro incremental de la biblioteca (#326)

> Estado: **implementado en una PR, pendiente de revisión**. Parte del refinamiento v1 de #326 (2026-10-23). Las decisiones marcadas «por defecto»
> las tomó el implementador porque el refinamiento las dejaba abiertas; **están por ratificar** y se pueden cambiar sin tocar el resto.

## 1. Problema local (CLAUDE.md §13)

- **Historia:** BL-R8 / #326 — quien deja un tebeo en su biblioteca espera que ZascArr lo vea.
- **Caso real:** #297 encontró 252 ficheros del disco sin fila; el hallazgo de #307 (`contrato-307-formato-por-contenido.md` §12.4) probó que, tras el registro
  inicial, **nada** registra los archivos nuevos de la biblioteca (el importador solo recorre las descargas; el marcador `_library_adoption_done` cierra la
  puerta de `LibraryAdopter`).
- **Hoy:** `adopt()` ya es idempotente por ruta, con un savepoint por archivo, lotes y segundo plano. Lo que impide usarlo es la **puerta** (`puede_registrar`,
  estado `HECHA`), no el adoptador.
- **Deseado:** una acción manual y explícita que enseñe lo nuevo, pida confirmación y registre solo eso, sin repetir el onboarding.

## 2. Referencias (no verificadas en vivo)

El texto de la tarjeta cita el «Rescan» de Sonarr y el escaneo de Kavita como expectativa del coleccionista. **No se han consultado en esta
implementación ni se infiere de su UI cómo funcionan por dentro** (§13). Decisión: **adaptar solo el patrón de producto** (una acción manual de búsqueda
+ confirmación), con implementación propia sobre `LibraryAdopter`. No se copia código de Kapowarr/Mylar3 (GPL-3.0).

## 3. Qué se hizo

| Pieza | Cambio |
|---|---|
| `LibraryAdopter.ofrece_registro_incremental()` | Solo cuando el registro inicial ya consta (marcador). Antes de eso se ofrece el registro completo, como siempre. No lee el disco. |
| `LibraryAdopter.inventario()` | Añade `carpeta_accesible`, `rutas_nuevas` y `huella` (resumen de las rutas nuevas enseñadas). Sigue sin abrir ningún archivo. |
| `LibraryAdopter.adopt(alcance=…)` | Con `alcance` solo trata esas rutas; no toca el marcador; guarda el informe con `kind = "registro_incremental"` (el de la adopción inicial, que usa Inicio, no se pisa). |
| Ambigüedad | Solo en incremental: si el contenido coincide con **varias** filas desaparecidas, no se reenlaza ninguna ni se crea fila: se informa (`ambiguous`). El importador y el registro inicial siguen reenlazando la más antigua, como siempre. |
| `registro_biblioteca.iniciar(…, alcance)` | La misma exclusión (una ejecución a la vez) para el inicial y el incremental. |
| `GET /ui/auditoria/nuevos` | Busca (solo lectura: nombres y rutas). |
| `POST /ui/auditoria/registrar-nuevos` | Registra **solo** las rutas que la persona vio: lleva la `huella`; si la carpeta ya no la da, no registra nada y enseña la lista actual. |

Sin migración, sin dependencias nuevas, sin red, sin automatismo (un test comprueba que solo la pantalla lanza el registro).

## 4. Reglas

1. **Nuevo = ruta sin fila** (en `COMIC_EXTS`: `.cbz .cbr .cb7 .pdf .epub`). Una ruta con fila —incluida una descartada o de una serie retirada— no es nueva y no
   se toca; **no se reactiva ningún descarte**.
2. **El inventario no lee contenido.** El hash solo se calcula al confirmar, y solo para las rutas confirmadas.
3. **Alcance confirmado.** Lo que aparece después de revisar no se cuela; lo que desaparece o ya estaba registrado se cuenta aparte (`ya_no_pendientes`).
4. **Al registrar**, cada archivo acaba en UNA categoría: ficha nueva (con serie sugerida o sin identificar → «Por revisar»), repetido de otro presente (no se añade,
   no se toca ninguna copia), reenlace de una fila desaparecida (misma fila, vínculo e historial conservados), ambiguo (no se toca nada), error, de otra ejecución.
5. **Nunca se vincula por el nombre de la carpeta** y no se crean series: es el mismo emparejamiento del adoptador (`_triage_and_match`), que no mira carpetas.
6. **Carpeta ilegible:** `carpeta_accesible = False` → no se ofrece registrar y no se da nada por nuevo ni por perdido. Este flujo **nunca** marca filas como desaparecidas.
7. **Resultado honesto:** «mirados» ≠ «añadidos»; con errores no se anuncia éxito; un commit incierto queda «por comprobar» (mecanismo existente de `_confirmar_lote`).
8. **Formatos (#307):** los archivos nuevos se triarán con el mismo punto de decisión; lo no utilizable queda registrado/avisado como hoy (no se amplía el universo).

## 5. Decisiones por defecto (a ratificar)

| # | Decisión | Por qué |
|---|---|---|
| a | **Punto de entrada: la pantalla de Auditoría**, donde ya vive el registro. #232 («Comprobar el disco») no está implementada. Cuando lo esté, «Buscar archivos nuevos» pasa a ser su continuación. | Evita esperar a #232 sin crear una acción que la duplique. |
| b | **Ignorados / retirados (#303): ninguna regla de reaparición.** Una fila nunca vuelve a ser «nueva». Un archivo con contenido ya conocido se trata por contenido (repetido o reenlace), sin reactivar descartes. | No hay un concepto de «ignorar» que inferir; no se borran decisiones por inferencia. |
| c | **Hash solo al confirmar**; lote existente de 25; sin tope nuevo. | El coste de leer el USB no está medido (§7). |
| d | **Informe con las categorías de §4.4** (sin categoría «no utilizables» propia: remite a «Revisar mi biblioteca», que ya las enseña con su causa). | No duplicar la auditoría. |

## 6. Límites conocidos (no resueltos)

- **Una copia idéntica de un archivo registrado vuelve a salir como «nueva» en cada búsqueda** (su ruta no tiene fila y su contenido no se registra dos veces). Cada
  vez se informa como repetida. Cerrarlo exige una política de copias (BL-DUP) o una marca de «ignorada» (#303); aquí no se inventa.
- **Exclusión solo dentro del proceso** (`--workers 1`). Entre procesos, la unicidad de `files.file_path` evita la fila doble **por ruta**; **por contenido no hay
  restricción única** en la base.
- **Un recorrido parcial** (una subcarpeta ilegible) no se detecta: `rglob`/`stat` saltan lo que no pueden leer. Como solo se actúa sobre lo visto, no fabrica altas
  ni bajas falsas, pero puede no ver algo.
- **Un contenido distinto en una ruta ya registrada** (archivo sustituido) no se detecta: es otro problema, no una alta.
- **Los formatos fuera de `COMIC_EXTS`** (`.rar`, `.tar`…) no se cuentan aquí: los enseña «Revisar mi biblioteca».

## 7. Pruebas y lo que NO se ha ejecutado

- `tests/test_registro_incremental_pg.py` (Postgres y ficheros reales): inventario sin leer ni escribir; huella; carpeta inaccesible; registrar solo lo nuevo
  conservando lo existente (ids, metadata, originales intactos, marcador y informe inicial sin tocar); repetir; alcance confirmado; copia idéntica (también repetida);
  archivo movido; ambigüedad (y que el registro inicial no cambia); fallo sin tocar el marcador; pantalla; huella obsoleta; dos confirmaciones a la vez; exclusión
  compartida; que solo la pantalla lanza el registro.
- `tests/test_registro_incremental.py` (sin BD): huella, cuentas del estado y textos de la pantalla.
- **Medición sintética LOCAL (no la Pi)** — `scripts/medicion/medir_registro_incremental.py`: 1.300 `.cbz` de 12 imágenes pequeñas (100 ya registrados + 1.200 nuevos), x86, Python 3.14,
  Postgres local, ficheros en caché de disco. Buscar (solo rutas): **0,02 s**. Registrar los 1.200: **8,6–8,8 s** (≈ 7 ms/archivo, 5,7 s de CPU), pico de memoria del proceso **83 MiB**, 0 errores. Segunda búsqueda: 0 nuevos.
  Sirve para comprobar que el coste crece de forma lineal y acotada; **no** predice la Pi ni el USB (los archivos reales pesan decenas de MB y el disco no está en caché).
- **NOT RUN:** coste en la Pi con >1000 archivos (criterio 9 de #326) y con el disco USB real; memoria y E/S en la Pi; ejecución sobre la biblioteca real.
