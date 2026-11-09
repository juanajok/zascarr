# Refinamiento de la épica BL-CNV (#476) — CBR a CBZ y ComicInfo

> **Estado:** propuesta de refinamiento para el PO. **No implementa código, no crea migraciones, no
> ejecuta conversiones ni mediciones, no toca la biblioteca, la Pi ni el tablero.** Recomendar no es
> decidir: las casillas de §9 las marca el PO.
> **Base:** `origin/main` = **`ecc52347488b7ec042cf818b77bf8a818a23c995`** (2026-11-09), que incluye la
> ficha de benchmark fusionada en #486. El código de BL-CNV no cambió entre el merge del benchmark
> (`a7038d8`) y este SHA (solo entró un arreglo ajeno de Comic Vine), así que las citas `fichero:línea`
> valen para ambos. Leído en el worktree aislado `.squad/wt-cnv-spec`, rama `docs/bl-cnv-refinamiento`.
> **Insumos:** issue #476 (feature) y sus hijas #477/#478/#479/#480/#481/#482/#488;
> `docs/design/benchmark-BL-CNV-cbr-a-cbz-y-comicinfo.md` (en `main`), `benchmark-B6-comicinfo.md`,
> `evaluacion-lector-rar-2026-10-23.md` (+ nota de #528), `contrato-307-formato-por-contenido.md`,
> `utils/lector_rar.py`, `utils/portada_rar.py`, `core/comicinfo_write.py`, `utils/cbz.py`,
> `services/tagger.py`, `utils/espacio.py`, `utils/bloqueo_archivo.py`, `docker-compose.yml` y los
> modelos `File`/`Issue`. **Método:** lectura de código y documentos; **sin pruebas ejecutadas, sin
> fuentes reales, sin Pi y sin abrir conversiones**.

> **Enmienda del PO (2026-11-09):** en #488 **no se bloquea** por «compartido» o «no se sabe».
> Se muestra una advertencia clara y la persona decide continuar mediante una **confirmación explícita**;
> sin esa confirmación no se escribe, con ella sí. En B6/CLI será una advertencia + opción explícita.
> Donde el resto de este documento diga «no se escribe / no se convierte» por compartido, léase
> «advertencia + confirmación; sin confirmación no se escribe». No hay bypass silencioso.

> **Cierre de #477 (2026-11-09):** la medición con `unar` 1.10.8 confirma los FAIL (pico de 512 MiB en
> CBR de 215,8/296,6 MiB y 3/24 extracciones fallidas). El streaming por índice se descartó (no baja el
> pico, multiplica el tiempo y trunca con `rc=0`). **Decisión PO: #478 queda acotada a CBR ≤150 MiB**;
> los mayores se bloquean con motivo, sin conversión, hasta otra fase. Los fallos de `unar` también se
> bloquean con motivo. Evidencia: PR #561.

---

## 1. Problema local, cifras y frontera

### 1.1 Problema y cifras (ficha #486, ya en `main`)

El coleccionista tiene **4.891 CBR (202,1 GiB)** frente a **746 CBZ (26,8 GiB)** en el disco de la
biblioteca; ZascArr solo escribe `ComicInfo.xml` dentro de CBZ (B6: «CBR nunca se parchea»), así que
mejorar metadatos no llega a la mayoría. El benchmark fija el orden: **convertir primero, etiquetar
después**, con conversión propia sobre B6 (sin recomprimir, verificada, original apartado y
reversible), no una copia de Kapowarr/ComicTagger. Datos y referencias están en la ficha; este
documento no los repite salvo lo necesario para los contratos.

### 1.2 Qué existe hoy en el código (verificado en `a7038d8`)

| Hecho | Evidencia | Consecuencia |
|---|---|---|
| El lector de RAR ya está en la imagen: base trixie, `unar`/`lsar` 1.10.8, flag `-json-skip-solid-information`, salida acotada, un solo lector por proceso, RSS ≤128 MiB, topes de 1000 entradas/500 MiB declarados. | `Dockerfile:27-34`; `utils/lector_rar.py:42-61,318-400`; `docker-compose.yml:144` (`LECTOR_RAR_ENABLED`) | #478 reutiliza el lector; no añade dependencia. |
| **No hay conversión** de formato ni escritura de RAR. B6 reescribe **solo CBZ** y **solo por CLI**; recompresión con `ZIP_DEFLATED` (no `ZIP_STORED`). | `services/tagger.py:1-18,392-410`; `utils/cbz.py:137-181` (`ZIP_DEFLATED` en `:176`); `scripts/etiquetar.sh` | #478 necesita un escritor nuevo de copia sin recomprimir; B6 no vale tal cual. |
| B6 ya tiene plan por campo, token implícito de contexto, manifiesto SHA256 por entrada, temporal con `mkstemp`, `testzip`, `fsync`, `os.replace`, doble advisory lock por `File.id` y reconciliación si falla el commit. | `core/comicinfo_write.py:32-38,73-135`; `utils/cbz.py:104-260`; `services/tagger.py:67-76,154-226,352-386,486-560` | #478 y #480 deben **reutilizar el patrón**, no inventar otro. |
| El `File` tiene `issue_id`, `file_path`, `file_format`, `file_size_bytes`, `file_mtime_ns`, `sha256_hash`, `original_sha256`, `metadata_source` y `metadata_` JSONB. | `models/__init__.py:556-604` | La conversión actualiza la **misma fila**, sin migración; `original_sha256` y `metadata_` son el sitio del historial. |
| El formato se decide por **contenido** (#307): `firma_de` y `tratamiento(ext, firma)`; `.cbr` con firma ZIP se lee como ZIP; `file_format` sigue siendo la extensión declarada. | `core/formato_contenedor.py:161-185`; contrato `contrato-307-formato-por-contenido.md` §3-§4 | D5 (`.cbr` que es ZIP) usa este punto único; #478 actualiza `file_format`+`metadata.formato_contenido` al renombrar. |
| El modelo de archivos no tiene conversión, ni estado de «original apartado», ni tabla de operaciones de conversión. | `models/__init__.py:556-604`; grep de `conversion`/`quarantine` en `src/` | #478 puede usar JSONB + un diario en disco; una tabla propia sería migración y decisión aparte. |
| `File.original_sha256` existe y el dedupe busca por `sha256_hash` **o** `original_sha256`. | `models:574-581`; ficha `benchmark-integridad-hash-dedupe` | La conversión debe fijar `original_sha256` (hash del RAR original) para no romper el dedupe. #446. |
| `#109` (M6) y `#233` (relación confirmada) ya están implementados: procedencia por campo, `locked_fields` y relación archivo→publicación protegida. | `services/procedencia.py`; `services/tagger.py:67-76`; `services/discrepancias.py`; `services/archivos_por_numero.py:51-81` | La conversión **no toca** la relación ni `locked_fields`; el cambio es de bytes/ruta, no de identidad editorial. |
| El contenedor de la app no es `read_only`; la biblioteca y las descargas van montadas **rw**; el límite es 512 MiB y 256 pids. `unar` está en la etapa `runtime`. | `docker-compose.yml:164-186`; `Dockerfile:27-34` | La conversión corre **dentro del contenedor** con el usuario de servicio; no usa socket Docker ni root. |

### 1.3 Frontera con las historias vecinas

| Historia | Qué se reutiliza | Qué **no** entra en BL-CNV |
|---|---|---|
| **#418 / BL-PORT3** (lector de RAR) | `utils/lector_rar.py` (listar/extraer por índice, topes, CRC, un lector, RSS), `unar` en la imagen, `LECTOR_RAR_ENABLED`, ADR 0015 | Cambiar el lector, añadir `unrar`/`rarfile`, o prometer RAR5 sólido (limitación conocida de `unar` 1.10.8; `evaluacion-lector-rar-2026-10-23.md:131`). |
| **#308 / #307** (formato por contenido) | `firma_de`, `tratamiento`, `clasificar_zip`, `metadata.formato_contenido` | Cambiar la matriz de tratamiento o usar la extensión como verdad; D5 solo materializa el caso `.cbr`-ZIP. |
| **B6** (ComicInfo) | Plan por campo, precedencia, `locked_fields`, `comicinfo_propio`, temporal+`os.replace`, manifiesto, reconciliación | Escribir ComicInfo en RAR, reutilizar `ZIP_DEFLATED` para convertir, o crear un segundo plan. |
| **#446 / BL-INF** (integridad y dedupe) | `original_sha256`, manifesto de hashes, idempotencia y reconciliación | Cambiar el contrato de dedupe o borrar el hash original. |
| **#109 / #233** (M6 y relación confirmada) | `metadata_` como procedencia durable, `locked_fields`, relación `File.issue_id` intacta | Aplicar metadatos, fusionar series, cambiar `metadata_source` o la relación; el guardián #488 solo **bloquea**. |
| **#447** (ficha de número, en curso) | La lista de archivos por número ya existe en la ficha de serie (`series_detail.html:133-152`, `archivos_por_numero.py:51-81`) | Inventar una ficha nueva sin coordinarla con #447; #478/#480 ponen sus acciones en la lista existente y se mueven a la ficha de número cuando #447 esté. |

---

## 2. D1–D5: cómo se materializan en contratos

Las cinco decisiones están **aceptadas por el PO** en la ficha §11; aquí se convierten en obligaciones
verificables, sin reabrir su sentido.

### D1 · Acción explícita con su propia garantía

- La conversión es **una acción pedida por la persona**, con vista previa y confirmación; **no** ocurre
  al importar, al descargar ni en un ciclo de fondo (D4).
- La garantía que se ve **junto al botón y en la confirmación** es propia de la conversión:
  «Tu original queda apartado en ZascArr y puedes deshacerlo. El resto de la biblioteca no se toca.»
  La promesa general «no se mueve ni se renombra nada» **se mantiene para todo lo demás**; la
  excepción se dice aquí, no se esconde.
- Una conversión fallida deja **el original en su ruta** y limpia temporales; una conversión con
  resultado incierto nunca se anuncia como éxito (§6.8).

### D2 · Original apartado, «Vaciar» separado y por tandas

- **Dónde:** `library_path/.zascarr/originales/<file_id>/<operacion_id>/<nombre-original>` (misma
  unidad de disco que el archivo; `os.replace`, sin copiar). `library_path` es `config.py:129`.
- **Qué se aparta:** el `.cbr` original (o el `.cbr`-ZIP en D5 no se aparta porque sus bytes no
  cambian; ver §2.5). El `.cbz` convertido **no** se copia: ocupa el destino final.
- **«Vaciar»** es una acción aparte, con confirmación explícita y **por tandas** (tope de lote, p. ej.
  ≤100 archivos o 2 GiB por tanda, configurable en el contrato de #478): solo borra bajo
  `.zascarr/originales/`, informa de cuánto libera y nunca toca la biblioteca. Mientras el original
  esté apartado, «Deshacer» está disponible; tras vaciarlo, no (se dice en la ficha).
- **Requisito transversal:** `.zascarr/` se excluye de los recorridos de biblioteca
  (`utils/fs.py::recorrer_comics`/`listar_comics`, rescan #BL-R9, auditoría y registro incremental).
  Sin esa exclusión, los originales apartados se registrarían como archivos nuevos y el diseño sería
  inválido. Es una dependencia que el PO debe aceptar (P11) y que se implementa en el mismo corte de
  #478 o en un corte previo mínimo.

### D3 · Archivos compartidos: guardián único y advertencia con decisión

- **Regla:** si el archivo puede estar compartido por Transmission o aMule, ZascArr **avisa** en la
  vista previa con la causa y ofrece continuar mediante una **confirmación explícita**. Sin esa
  confirmación no se escribe; con ella, la persona decide y la escritura sigue. No se ofrece quitar el
  torrent ni dejar de compartir, ni hay bypass silencioso.
- **Alcance:** toda escritura de bytes, no solo convertir: también B6 (el comando `etiquetar.sh
  --apply` y #480), porque reescribir un CBZ cambia su hash y rompe la siembra. Hoy `tagger.py` **no
  lo comprueba** (ficha §11.1); #488 lo cierra.
- **Un único servicio** responde «¿se comparte?»; conversión y etiquetado lo consumen; **sin socket
  Docker ni root** (§5).
- **Desconocido:** si no hay ninguna fuente de información (ni carpetas declaradas ni cliente
  disponible), o si una fuente habilitada falla o no se puede traducir una ruta, el resultado es
  `no_se_sabe`; se advierte y se pide la misma confirmación explícita, explicando cómo declarar las
  carpetas.
- **Riesgo aceptado (ficha §11.1):** hasta que #488 esté fusionada, el comando de B6 puede tocar un
  archivo compartido. No se añade un parche provisional; #488 es requisito de #478 y #480.

### D4 · Sin conversión automática al descargar

- No hay conversión en el importador, en el ciclo de descargas, en el rescan ni en un botón
  «convertir todo automáticamente». Solo acciones explícitas (una en #478; lote pedido en #479).
- El estado de una conversión no se dispara por una descarga nueva ni por un fichero que aparezca; si
  el PO quiere automatizar más adelante, será otra decisión con evidencia de #477/#479.

### D5 · `.cbr` que ya es ZIP: renombrar sin tocar contenido

- Se decide por **contenido**, no por extensión: `firma_de(path)` ZIP y `clasificar_zip` (clase
  `TEBEO`) en `core/formato_contenedor.py:161-240`. Si no es ZIP-TEBEO, va por la vía normal o se
  bloquea con su motivo.
- Se **renombra** `.cbr` → `.cbz` en el mismo directorio con `os.replace` (mismo inodo; **no** se
  copia ni se recomprime), se verifica que el hash del contenido no cambió, y se actualiza la misma
  fila (`file_format`, `file_path`, `file_name`, `metadata.formato_contenido`). No hay original
  apartado porque los bytes son idénticos; el historial y el «deshacer» se guardan en `metadata_`.
- Si existe el `.cbz` destino, se bloquea (I5: no se sobrescribe una copia homónima).
- Un archivo compartido tampoco se renombra (D3).

---

## 3. Reparto, orden y puertas

### 3.1 Orden recomendado

`#477 (medición) ∥ #488 (guardián)` **como puertas** → `#478 (una conversión)` → `#480 (ComicInfo
mínimo)` → después, según las cifras: `#479 (lote)`, `#481 (campos nuevos)`, `#482 (varias fuentes)`.

- **#477** es la puerta de **producto y riesgo**: cifras de coste/espacio/convertibilidad y de
  archivos compartidos; puede recomendar repriorizar #478/#479 o parar. No escribe en la biblioteca.
- **#488** es la puerta de **seguridad de datos**: sin guardián no se convierte ni se escribe
  ComicInfo en la biblioteca. Bloquea #478 y #480.
- **#478** da el mínimo útil de `#476` (un CBR→CBZ y su deshacer); **#480** da el mínimo de ComicInfo
  sobre CBZ (incluidos los ya convertidos) y no depende de #478 en código, pero sí comparte #488 y
  conviene después para que la primera conversión no quede sin metadatos.
- **#479, #481 y #482** no se comprometen: su prioridad y talla se ajustan con las cifras de #477 y
  con las dependencias de #448/#109.

### 3.2 Qué escribe cada historia

| Historia | Qué escribe | Qué **no** escribe | Depende de | Talla propuesta / PR |
|---|---|---|---|---|
| **#477 BL-CNV0** | Nada en la biblioteca; solo copias, contenedor desechable y evidencia (documento/JSON) | Ni BD, ni archivos de la biblioteca, ni configuración | Autorización del PO para copiar/consultar clientes (P5) | **S** (una PR de medición + evidencia) |
| **#488 BL-CNV6** | Servicio y ajuste de carpetas declaradas; solo bloquea a otros (no escribe archivos) | Ni archivos, ni torrents, ni configuración de los clientes | Ninguna bloqueante; aMule/NOT RUN de #477 puede limitar una fuente | **M** (servicio + UI de ajuste + pruebas + guardián en tagger) |
| **#478 BL-CNV1** | Temporal en la misma carpeta, `.cbz` destino, original movido a `.zascarr/originales`, misma fila `File`, diario/JSONB, entrada de historial; «Deshacer» y «Vaciar» | Otros archivos, otras filas, `locked_fields`, `metadata_source`, relación/`issue_id`, `Issue`, fuentes | **#477 y #488**; #418 (lector); B6 (patrón); P11 (exclusión `.zascarr`) | **L** (8) — servicio + UI + pruebas reales de disco |
| **#480 BL-CNV3** | `ComicInfo.xml` dentro de CBZ con el plan de B6 (misma fila, `comicinfo_propio`, hash/tamaño) | CBR (se remite a #478), archivos compartidos, red, campos fuera del mapa B6 | **#488**; B6; P#447 para la ubicación final de la UI | **M** (5) |
| **#479 BL-CNV2** | Nada nuevo por archivo: reutiliza #478 | Nada automático; archivos compartidos se saltan | #478, #488, cifras #477 | **M** (5) |
| **#481 BL-CNV4** | Amplía el mapa de campos de B6 (`Writer`…, `Genre`, `PageCount`) | `LanguageISO` inferido, campos sin dato | #480; #448 (autores en BD) | **M** (5) |
| **#482 BL-CNV5** | Propuestas campo a campo desde fuentes, luego plan #480 | Aplicación automática; fuentes apagadas; sin confirmación | #480, #481, #109, cobertura #449 | **XL** (13, probable partición al refinar) |

**No se crean tarjetas hijas en este encargo**; el Lead decide el tablero. Las dependencias de §3.1
son técnicas, no un compromiso de sprint.

---

## 4. Contrato técnico de #477 (medición en copias)

### 4.1 Garantías

- **Nunca** se monta la biblioteca en el contenedor de medición: las muestras se copian con `cp` y se
  verifica su `sha256` contra el original; la biblioteca solo se **lee** para el censo y los recuentos.
- Contenedor desechable: `--network none --read-only --memory=512m --memory-swap=512m --cpus=2
  --pids-limit 128 --cap-drop ALL`, usuario no root, trabajo en un volumen/tmpfs acotado; sin socket
  Docker, sin `--privileged`. Mismo patrón que `scripts/medicion/evaluacion_rar/LEEME.md`.
- Ninguna medición escribe en la BD ni en la biblioteca; las consultas de censo son **solo lectura**
  (transacción `READ ONLY`).

### 4.2 Censo (solo recuentos)

Sobre los CBR **registrados** (`File.file_format='cbr'`, `is_missing=false`; lectura de BD) y, como
dato de contraste, sobre el disco (solo `find`/cabeceras, como la ficha):
RAR4/RAR5, sólidos, cifrados, multivolumen, anidados/paquete, dañados/ilegibles y `.cbr` que son ZIP.
La clasificación de sólidos/cifrados/multivolumen se hace en el **script de medición** con `lsar -j`
(campo de sólido incluido) y no con el lector de la app (que omite la información de sólidos por el
flag #528); una muestra que no se pueda clasificar queda **NOT RUN**, nunca se estima.

### 4.3 Muestra

- Semilla fija y reproducible; **≥24 CBR** si existen: 20 al azar estratificados por tamaño (pequeño/
  mediano/grande) + todos los sólidos, cifrados y ZIP-disfrazados encontrados (hasta 10), y al menos
  un paquete si lo hay. Si hay menos de 24, todos. Se documenta la regla exacta y el listado por
  **id/hash**, nunca por ruta ni nombre del coleccionista.
- Copias con hash verificado; no se modifica ninguna copia original; los daños (si se prueban) se
  aplican a **otra copia** dentro del contenedor.

### 4.4 Métricas por muestra (3 repeticiones: primera, mediana, máximo)

| Métrica | Cómo |
|---|---|
| Tiempo de listar, extraer, escribir ZIP_STORED, verificar, publicar (simulado) y total | reloj monótono por fase; proceso nuevo por operación |
| Pico de memoria (RSS) | `RUSAGE_CHILDREN` + `memory.peak`/`memory.events` del cgroup; muertes por OOM contadas |
| Espacio temporal máximo | tamaño del directorio de trabajo vigilado; libre antes/después |
| Tamaño CBR → CBZ | bytes de entrada/salida y diferencia (%), con el manifiesto |
| Integridad | mismas entradas (nombres, tamaños, CRC32), `testzip`, SHA256 del contenido por entrada |
| Resultado | `ok`/`fallo` con motivo de dominio (`cifrado`, `multivolumen`, `paquete`, `dañado`, `demasiado_grande`, `tiempo`, `herramienta_ausente`) |
| Archivos compartidos | recuento de registrados en torrents de Transmission y compartidos de aMule; **agregados**, sin rutas (autorización expresa del PO para esa tanda) |
| Kavita | prueba en instancia desechable: importar copia CBR, marcar progreso, sustituir por CBZ convertido, rescanear; ¿progreso conservado? ¿duplicado? versión de Kavita anotada |
| Vulnerabilidades de `unar`/GNUstep | versión, CVEs y fuentes consultadas; PASS/FAIL/NOT RUN |

### 4.5 Evidencia y umbrales de decisión

- Formato: tabla de resumen + `docs/design/benchmark-BL-CNV-datos.md` (o JSON versionado) con
  entorno (modelo de Pi, kernel, RAM, disco, versión de `unar`/Python), comandos y celdas
  PASS/FAIL/NOT RUN; **sin rutas ni nombres** de la biblioteca. La ficha de benchmark §12 se actualiza
  en la misma PR.
- **Umbrales provisionales para recomendar seguir/parar:** pico de memoria del contenedor ≤ 256 MiB;
  conversión mediana de un CBR típico (≤100 MB) ≤ 60 s; ninguna muerte por OOM; espacio temporal
  ≤ 1,5× el tamaño del original; si más del 80 % de los CBR registrados se comparten, recomendar
  repriorizar #478/#479 (decisión del PO, no automática).

### EARS y AC de #477

- **CUANDO** se ejecute la medición, el sistema **no** modificará la biblioteca ni la BD: solo copias y
  lecturas.
- **SI** una celda no se puede medir (sin muestra, herramienta ausente, cliente apagado), **ENTONCES**
  queda NOT RUN, nunca un valor estimado.
- **CUANDO** termine, la ficha tendrá censo, coste, tamaño, integridad, Kavita, archivos compartidos y
  vulnerabilidades, con PASS/FAIL/NOT RUN separados.
- **AC-CNV0-1** censo completo con cifras y porcentajes; **AC-CNV0-2** muestra reproducible y copias
  con hash verificado; **AC-CNV0-3** tiempo/RSS/espacio por fase y total; **AC-CNV0-4** integridad
  (entradas, CRC, `testzip`, SHA); **AC-CNV0-5** CBR→CBZ y diferencia de tamaño; **AC-CNV0-6** Kavita
  (progreso/duplicados) en instancia de prueba; **AC-CNV0-7** recuento agregado de compartidos y qué
  expone `amuleweb`; **AC-CNV0-8** revisión de vulnerabilidades de `unar`/GNUstep.

---

## 5. Contrato técnico de #488 (guardián de compartidos)

### 5.1 Servicio único

- Módulo de servicio (p. ej. `services/compartidos.py`) con una sola puerta:
  `async def estado_de_comparticion(path: Path) -> Decision` y una variante por lote para #479.
- `Decision` es un valor cerrado: `no_compartido`, `compartido(causa)`, `no_se_sabe(causa)`, con
  `causa` en español llano y una lista de fuentes consultadas (sin rutas en logs/UI más allá de lo
  necesario). **Nunca devuelve «no compartido» por defecto.**
- Consumidores obligatorios: vista previa de #478, ejecución de #478 antes de publicar, vista previa y
  escritura de #480, y `TaggerService` (CLI `scripts/etiquetar.sh --apply` incluido). Un solo punto;
  ningún camino alternativo puede saltárselo.

### 5.2 Fuentes y traducción de rutas

1. **Carpetas declaradas en Ajustes** («carpetas que comparten tus programas de descargas»): raíces
   conocidas del contenedor (`library_path`, `downloads_path`, `amule_incoming_dir`;
   `config.py:104-134`) mediante casillas, o una lista validada de rutas absolutas. Se guardan en
   `runtime_settings` (patrón `RuntimeSettingsService`, `services/runtime_settings.py:30-58,99-176`),
   sin migración. No se aceptan rutas relativas ni con `..`.
2. **Transmission** (si `transmission_enabled`): `torrent-get` con `downloadDir` y `files` (el cliente
   ya los pide en `services/transmission.py:51-69`), ampliado para devolver **todos** los torrents
   sembrados, no solo los de una carpeta. Traducción host→contenedor con pares conocidos
   (`host_library_dir`→`library_path`, `transmission_download_dir`→`downloads_path`;
   `config.py:104,129-134`). Una ruta de torrent cuyo origen no se sepa traducir ⇒ `no_se_sabe`.
3. **aMule** (si `amule_enabled`): lo que exponga `amuleweb` de sus compartidos (hoy el cliente solo
   lee la página principal, `services/amule.py:65-86`; **NOT RUN** qué expone). Si no se puede
   determinar, `no_se_sabe`; las carpetas declaradas son la vía segura para cubrirlo.

### 5.3 Semántica (fallo cerrado)

- `compartido` si alguna fuente lo afirma (coincidencia por ruta real; resolución de symlinks con
  `realpath`, comparación por raíz, no por prefijo de texto).
- `no_se_sabe` si: no hay ninguna fuente disponible (ni declaradas ni clientes encendidos), una fuente
  encendida falla, o una ruta no se puede traducir. **Se trata como bloqueo de escritura.**
- `no_compartido` solo si todas las fuentes disponibles respondieron y ninguna lo afirma.
- **Frescura:** la vista previa puede usar una instantánea; **antes de publicar** (renombrar/mover/
  reemplazar) se vuelve a consultar. La ventana entre esa comprobación y `os.replace` es un riesgo
  residual aceptado y declarado (el cliente puede añadir un torrent después); no se elimina.
- Sin caché entre operaciones (solo la instantánea de una operación), sin persistir rutas, sin
  modificar clientes ni torrents.

### 5.4 Ajustes y mensajes

- Sección «Archivos compartidos» con casillas de las raíces conocidas y texto llano: «Marca las
  carpetas que comparten tus programas de descargas. Si ZascArr no sabe si un archivo se comparte, no
  lo toca.»
- En vista previa: «No se toca: lo comparte Transmission» / «…aMule» / «No podemos saber si se
  comparte; no se toca. Declara las carpetas en Ajustes.» Sin acción para quitar el torrent.
- Sin socket Docker, sin root, sin credenciales en URLs/logs.

### 5.5 Pruebas

- Dobles de `TransmissionClient`/`AMuleClient`: torrent en la biblioteca, en descargas, en incoming,
  ruta desconocida, cliente caído, integración apagada, sin fuentes, carpeta declarada.
- Regresión de B6: `TaggerService` con archivo compartido ⇒ `bloqueado` sin escritura (también en CLI);
  y con `no_se_sabe` ⇒ `bloqueado`. #478 con los mismos casos. Postgres real para la fila intacta,
  disco simulado para el no-efecto.

### EARS y AC de #488

- **CUANDO** conversion o etiquetado vayan a escribir, consultarán **el mismo** servicio.
- **SI** un archivo está en una carpeta compartida o un torrent/compartido de un cliente encendido,
  **ENTONCES** no se escribe y se dice la causa.
- **SI** no hay información o una fuente falla, **ENTONCES** no se escribe y se explica cómo declarar.
- **MIENTRAS** el archivo se comparte, ZascArr no quita el torrent ni deja de compartir.
- **AC-CNV6-1** servicio único usado por #478/#480/B6; **AC-CNV6-2** carpetas declaradas; **AC-CNV6-3**
  Transmission (rutas traducidas); **AC-CNV6-4** aMule (lo que exponga; NOT RUN hasta #477);
  **AC-CNV6-5** fallo cerrado (cliente caído/ruta desconocida/sin fuentes); **AC-CNV6-6** vista previa
  con el texto y sin acciones sobre el cliente; **AC-CNV6-7** pruebas con dobles + regresión B6 + sin
  Docker socket/root.

---

## 6. Contrato técnico de #478 (una conversión)

### 6.1 Vista previa (solo lectura)

- Entrada: `file_id` de un archivo con `issue_id` (se muestra en la lista de archivos de la ficha de
  serie, `series_detail.html:131-150`; cuando #447 fusione la ficha de número, se reutiliza allí).
- Muestra: nombre antes → después (`.cbr`→`.cbz`), tamaño de entrada y estimación de salida (suma del
  listado RAR), espacio libre/necesario, método (`recomprimir` o `renombrar ZIP` en D5), y la garantía
  de D1 junto a la acción.
- Motivos de bloqueo en español llano: no es CBR, ya existe un `.cbz` homónimo, falta espacio, archivo
  compartido/«no se sabe», cifrado, multivolumen, paquete/anidado, dañado, demasiado grande, RAR5
  sólido no extraíble por `unar` (limitación conocida), lector apagado/herramienta ausente, archivo
  ausente, serie/número inexistente, sin permiso.
- **Cero escrituras**: ni BD, ni ficheros, ni temporal persistente. Emite un token firmado (HMAC, TTL
  15 min) con `file_id`, ruta, `stat` (tamaño+mtime), hash, método, operación nueva; la confirmación
  solo reenvía ese token.

### 6.2 Ejecución (un solo trabajo a la vez)

- Un **trabajo en proceso** (single worker, `asyncio.to_thread` para E/S; `unar` por subproceso) con
  semáforo de 1: otra conversión espera o se rechaza con aviso; no hay cola externa ni Redis.
- Locks: `bloquear_archivo(db, file_id)` (metadata/relación, mismo orden global que tagger/rescan,
  `utils/bloqueo_archivo.py`) + el lock de bytes por `File.id` del tagger
  (`services/tagger.py:154-226`, misma clave compartida) durante leer→publicar; y `pg_try_advisory_lock`
  del **cerrojo de ciclo** (`services/comprobacion_disco.py:31`, el mismo que rescan e importador: `rescan_biblioteca.py:76-96`) justo para la ventana publicar+mover+commit,
  para que el rescan no vea el destino a medias. Si el cerrojo está ocupado, se aborta sin escribir y
  se pide reintentar.
- Fases y límites:
  1. validar token/estado; comprobar `estado_de_comparticion` y `lector_rar.disponible()`/switch.
  2. `lector_rar.listar` (≤1000 entradas, ≤500 MiB declarados, timeout); rechazar cifrado,
     multivolumen, paquete (contenedores anidados), nombres inseguros (absolutos/`..`), directorios no
     representables y entradas > tope de conversión (32 MiB) con motivo.
  3. comprobar espacio: `utils/espacio.comprobar_espacio` con la suma descomprimida + margen (tope por entrada `MAX_ENTRADA_LEIDA`, 32 MiB,
     `core/formato_contenedor.py:59`); y `st_dev` del destino y de `.zascarr` iguales (si no, «otro disco», no se convierte).
  4. crear temporal **en el mismo directorio** con `mkstemp` (`ZIP_STORED`, sin recomprimir), copiando
     entrada por entrada con `lector_rar.leer_entrada` (bytes por entrada acotados; jamás el archivo
     entero en memoria) y **manteniendo el orden y los nombres**.
  5. verificar el temporal: manifiesto `(nombre, tamaño, CRC32, SHA256)` de cada entrada no-directorio
     calculado al leer el RAR; leer el ZIP nuevo una vez y comparar nombres/tamaños/CRC/SHA; el
     `zipfile` valida el CRC al leer (equivalente a `testzip` para las entradas leídas); comprobar que
     hay **como mucho un** `ComicInfo.xml` (si el original ya trae más de uno: bloquear, no inventar).
  6. `fsync` del temporal y del directorio; **re-consultar** el guardián de compartidos; `os.replace`
     temporal→destino (atómico); `fsync` del directorio.
  7. mover el original a `.zascarr/originales/<file_id>/<operacion_id>/<nombre>` con `os.replace`
     (misma unidad; nunca copia).
  8. actualizar la **misma fila `File`** y hacer `commit` **corto al final** (nunca con la sesión
     abierta durante la copia).
- Nada de `docker`, socket Docker, root ni modificar los clientes P2P.

### 6.3 Verificación y manifiesto

- No se publica «sin excepción»: la verificación es un criterio, no un extra. El manifiesto incluye
  nombre, tamaño, CRC32 y SHA256 por entrada; la comparación es por **conjunto** (mismas entradas, sin
  extras), y el orden de escritura es el del listado (mejor lectura en lectores).
- Un fallo de verificación **no publica nada** y deja el original intacto y el temporal limpio.

### 6.4 Publicación, original apartado, diario y reconciliación

- **Diario de operación** escrito de forma atómica en la carpeta de cuarentena de la operación
  (`.../<operacion_id>/journal.json`): versión, `operacion_id`, `file_id`, paso (`construido`,
  `publicado`, `apartado`, `confirmado`), identidad del original (ruta, nombre, tamaño, SHA256,
  mtime, `st_dev/ino`), destino (ruta, nombre, tamaño, SHA256, mtime) y manifiesto. Es el testigo de
  recuperación; no guarda rutas en logs.
- **Estados de caída y reparación** (misma doctrina que B6):
  - caída antes de publicar: no hay destino; se borra diario/temporal y el original sigue intacto.
  - `publicado` y caída antes de apartar: existen `.cbz` destino y `.cbr` original; la reconciliación
    termina el apartado y la BD, o si el destino no coincide con el diario, lo mueve a cuarentena y
    conserva el original.
  - `apartado` y caída antes del `commit`: la reconciliación actualiza la fila (ruta, formato, hash,
    tamaño, mtime) y deja el estado `convertido`.
  - `commit` fallido después de publicar/apartar: se relee el disco y el diario, no se anuncia éxito y
    se repara en la siguiente pasada o con «Comprobar resultado».
- La reconciliación corre al arrancar y cuando la UI de la ficha/estado lo pide; no crea filas nuevas
  ni trata el destino como duplicado.

### 6.5 Efectos en la fila y deshacer / vaciar

- **Misma fila**: `file_path` (destino `.cbz`), `file_name`, `file_format=CBZ`, `sha256_hash` del nuevo
  CBZ, `file_size_bytes`, `file_mtime_ns`; `original_sha256` = SHA256 del RAR original si era `NULL`
  (no se pisa si ya consta, #446); `metadata_["conversion"]` = `{version, estado, operacion_id, fecha,
  metodo ("recomprimir"|"renombrar_zip"), original:{...}, destino:{...}, verificacion:{...},
  historial:[...]}`; se limpia `metadata_["comicinfo_estado"]` (describía los bytes viejos) y, si el
  origen era RAR, no hay `comicinfo_propio` que conservar. **No** se tocan `issue_id`, `metadata_source`,
  `locked_fields`, `review_dismissed` ni ninguna otra relación.
- **Deshacer** (misma fila, token firmado nuevo): verificar que el destino no cambió desde la conversión
  (hash/tamaño/mtime), que el original está en cuarentena y el guardián dice `no_compartido`; mover el
  `.cbz` a la cuarentena de la operación (no se borra), mover el `.cbr` a su ruta original (si está
  ocupada, abortar sin tocar), restaurar ruta/nombre/formato/hash/tamaño/mtime/original_sha256 y
  metadata; historial `deshecho`. Si el `.cbr` ya se vació, no hay deshacer y se dice.
- **Vaciar** (D2): solo bajo `.zascarr/originales/`, confirmación explícita, por tandas; cuenta y
  bytes liberados; no toca la biblioteca; tras vaciar, el estado pasa a `purgado` y el deshacer deja
  de estar disponible.
- **D5 (renombrar ZIP)**: mismo flujo sin recompresión ni original apartado (bytes idénticos); destino
  `.cbz`; `file_format=CBZ`; `sha256_hash`/`size`/`mtime` no cambian (se verifican); `formato_contenido`
  se actualiza a `{firma:"zip", clase:"tebeo"}`; el diario y `metadata.conversion` guardan la ruta
  original; deshacer renombra de vuelta y restaura la fila. Si el destino existe: bloqueo. Si el
  guardián dice compartido/`no_se_sabe`: bloqueo.

### 6.6 Límites, errores, idempotencia y resultado incierto

- **Límites:** un trabajo a la vez; **tamaño del CBR ≤150 MiB** (decisión PO tras #477; los mayores se
  bloquean con motivo); ≤1000 entradas/≤500 MiB declarados (lector); entrada individual ≤32 MiB;
  memoria del proceso dentro de 512 MiB (pico medido por #477); espacio necesario =
  descomprimido + margen (`utils/espacio.py`); cuarentena en la misma unidad; tope de lote de «Vaciar».
- **Errores** (códigos de dominio, textos en español llano): `archivo_ausente`, `no_es_cbr`,
  `ya_existe_cbz`, `sin_espacio`, `otro_disco`, `compartido`, `no_se_sabe`, `cifrado`, `multivolumen`,
  `paquete`, `demasiado_grande`, `ilegible`, `herramienta_ausente`, `lector_desactivado`,
  `nombre_no_seguro`, `comicinfo_duplicado`, `propuesta_desactualizada`, `conflicto_de_bloqueo`,
  `resultado_incierto`, `cancelado`.
- **Idempotencia:** repetir el mismo token devuelve el mismo resultado (diario + `metadata.conversion`),
  sin reconvertir; un token caducado con diario permite reanudar/releer, sin diario no hay cambios
  (mismo contrato que retirada 2d). Un segundo envío simultáneo se serializa por el lock y devuelve
  `ya_convertido` o espera.
- **Resultado incierto:** cualquier fallo tras pedir el `commit` no se anuncia como éxito: 503/estado
  `resultado_incierto` con «Comprobar el resultado», que relee diario + fila. Reintentar el mismo token
  no duplica.
- **Sin efectos colaterales:** no se tocan otros archivos, `Issue`, `Series`, `Wishlist`, lecturas,
  deseados ni los clientes P2P.

### 6.7 Rutas y UI (HTMX)

- `GET /ui/series/{series_id}/archivos/{file_id}/convertir` → fragmento de vista previa
  (`_conversion_previa.html`), `POST …/convertir` (token) → fragmento de resultado/estado,
  `POST …/convertir/deshacer`, y `GET/POST /ui/ajustes/originales` para «Vaciar» (lista, cuánto ocupa,
  tandas). Sin JSON en `/ui`; fallos recuperables con 200 + `ui.aviso`; `hx-post` con `hx-disabled-elt`;
  sin JS nuevo; la página sin HTMX también funciona con formularios reales.
- Estados de UI: en curso (progreso/polling o aviso de espera), convertido (nombre nuevo, enlace a
  deshacer), bloqueado con motivo, error con acción. El trabajo puede tardar: se muestra «Convirtiendo…»
  y no se bloquea la pantalla; una conversión ya en marcha se dice, no se duplica.

### EARS y AC de #478

- **CUANDO** la persona pide convertir un CBR desde la ficha, ve antes el antes→después, el espacio y la
  garantía, y solo con su confirmación se escribe.
- **SI** el archivo se comparte, no se sabe si se comparte, es cifrado/paquete/dañado/grande, ya hay un
  CBZ homónimo o falta espacio, **ENTONCES** no se toca nada y se dice el motivo.
- **CUANDO** se convierte, cada entrada se copia tal cual (`ZIP_STORED`), se verifica y se publica de
  forma atómica en la misma carpeta; el original queda apartado en `.zascarr` y la misma fila se
  actualiza.
- **SI** algo falla a mitad, **ENTONCES** el original sigue intacto, el temporal se limpia y no se
  anuncia éxito; si el `commit` es incierto, se puede comprobar/reanudar sin duplicar.
- **DONDE** el `.cbr` es un ZIP, se renombra sin recomprimir y con el mismo contrato de vista previa,
  deshacer y guardián.
- **AC-CNV1-1** vista previa con datos y garantía; **AC-CNV1-2** no recomprime; **AC-CNV1-3**
  verificación (manifiesto+CRC) antes de publicar; **AC-CNV1-4** misma fila (ruta/formato/hash/tamaño),
  sin tocar relación ni `locked_fields`; **AC-CNV1-5** original apartado y deshacer completo;
  **AC-CNV1-6** motivos de bloqueo en llano; **AC-CNV1-7** `.cbr`-ZIP renombrado sin tocar bytes;
  **AC-CNV1-8** idempotencia, resultado incierto y reconciliación; **AC-CNV1-9** guardián #488 en
  preview y antes de publicar; **AC-CNV1-10** pruebas con fixtures RAR4/RAR5/sólido, `unar` falso para
  fallos y Postgres real para la fila.

---

## 7. #480 y siguientes

### #480 BL-CNV3 · ComicInfo desde la ficha

- Reutiliza **el mismo plan por campo de B6** (`core/comicinfo_write.py`, `services/tagger.py`); no
  crea un segundo plan. La vista previa devuelve el plan y un **token firmado** con la identidad del
  archivo (`file_id`, ruta, tamaño, mtime, SHA256) y la huella del plan (deseados + bloqueados +
  `comicinfo_propio`). «Guardar» envía **solo el token**; el servicio verifica stat/hash/plan, aplica
  **ese** plan (sin volver a planificar ni consultar red) y fusiona el XML conservando lo desconocido.
- Si no hay `ComicInfo.xml`, se crea con lo que haya; sin dato no se inventa nada. Lo manual y
  `locked_fields` no se pisan. Sin red. Si el archivo cambió desde la vista: plan caducado, no se
  escribe. `resultado_incierto`/reconciliación con el patrón B6.
- **Un CBR muestra «Conviértelo primero»** con enlace a #478, no un error. **Un archivo compartido no
  se reescribe**: la vista previa lo dice y no hay botón (guardián #488, también en el CLI de B6).
- EARS/AC-CNV3: AC-CNV3-1 plan idéntico a B6; AC-CNV3-2 token+huella y caducidad; AC-CNV3-3 crear XML;
  AC-CNV3-4 sin red; AC-CNV3-5 manual/`locked_fields` intactos; AC-CNV3-6 compartido bloqueado;
  AC-CNV3-7 CBR remite a #478; AC-CNV3-8 pruebas FakeSession + Postgres real + navegador real (NOT RUN
  hasta implementar).

### #479 BL-CNV2 · lote

Reutiliza #478 por archivo (un solo servicio); vista previa agregada (cuántos sí/no y por qué, espacio
total), tope por tanda, parada, informe que cuadra y archivos compartidos saltados. Depende de #478 y
#488; su tamaño real depende de #477.

### #481 BL-CNV4 · campos nuevos de ComicInfo

Amplía `CAMPOS_GESTIONADOS` (`comicinfo_write.py:36-38`) y el mapa `_LOCK_DE`
(`services/tagger.py:67-76`) con `Writer`, `Penciller`, `Inker`, `Colorist`, `Letterer`, `CoverArtist`,
`Editor`, `Translator`, `Genre`, `PageCount`, desde `issue_creators` y el número; misma precedencia,
listas sin duplicados, `LanguageISO` sigue sin inferirse. Depende de #448 (autores en la BD) y #480.

### #482 BL-CNV5 · varias fuentes, campo a campo

Propuestas por campo con procedencia visible (patrón #128/#109), fuentes encendidas y elegidas por
tradición (ADR 0002), cortesía compartida, nada se aplica sin confirmación y lo elegido pasa por el plan
de #480. XL; probable partición al refinar; depende de #480/#481/#109/#449.

---

## 8. Riesgos, pruebas futuras y NOT RUN

### 8.1 Riesgos

| ID | Riesgo | Prob./impacto | Mitigación |
|---|---|---|---|
| R1 | La conversión rompe un torrent en siembra | Alta/alta | #488 antes de #478/#480; advertencia + confirmación explícita; re-consulta antes de publicar; riesgo residual declarado y decidido por la persona |
| R2 | `.zascarr/` dentro de la biblioteca lo registra el rescan/registro como archivos nuevos | Media/alta | Exclusión explícita en `recorrer_comics`/rescan/auditoría (P11); prueba de regresión |
| R3 | Espacio insuficiente en el disco USB (original + temporal) | Media/alta | `comprobar_espacio` con suma descomprimida + margen; aborta antes; cifras de #477; «Vaciar» por tandas |
| R4 | 202 GiB de originales apartados duplican la colección | Media/media | Cuarentena solo hasta «Vaciar»; aviso de espacio; #477 mide; topes en #479 |
| R5 | RAR5 sólido no extraíble por `unar` 1.10.8 | Media/media | Se bloquea con motivo; #477 mide cuántos hay; decisión PO (P7) |
| R6 | El `commit` falla tras publicar | Baja/media | Diario + reconciliación + «Comprobar resultado»; nunca éxito sin leer |
| R7 | Un rescan/otra escritura ve el destino a medias | Baja/alta | Locks por `File.id` en el orden global + cerrojo de ciclo en la ventana de publicación |
| R8 | El guardián no ve un torrent añadido justo después de comprobar | Baja/media | Re-consulta antes de publicar; ventana residual declarada; no se promete inmunidad absoluta |
| R9 | aMule no expone compartidos por `amuleweb` | Media/media | Carpetas declaradas como vía segura; `no_se_sabe` si no consta; #477 lo verifica |
| R10 | La conversión no mejora el espacio (ZIP_STORED ≥ CBR) | Media/baja | #477 mide tamaño; se informa en la vista previa; no se promete ahorro |
| R11 | UI bloqueada por un trabajo largo | Media/baja | Trabajo en proceso con estado/polling; no duplicar; aviso de espera |
| R12 | Se rompe el dedupe (#446) por cambiar `sha256_hash` | Baja/media | `original_sha256` = hash del RAR si no consta; pruebas de dedupe existentes |

### 8.2 Pruebas futuras (definidas; no implementadas)

| Criterio | Prueba |
|---|---|
| #477 censo/muestra/métricas | `scripts/medicion/evaluacion_rar/` adaptado (banco de conversión) + evidencia en `docs/design/benchmark-BL-CNV-datos.md`; sin CI (requiere Pi y copias) |
| #488 guardián | `tests/test_compartidos.py` con dobles de Transmission/aMule y carpetas; `tests/test_tagger_compartido.py` (regresión B6) |
| #478 conversión | `tests/test_conversion_cbr.py` (puro: manifiesto, nombres), `tests/test_conversion_pg.py` (Postgres real: misma fila, deshacer, reconciliación) y fixtures RAR4/RAR5/sólido de `tests/fixtures/rar/`; `unar` falso para fallos; disco real o simulado |
| #478 UI | `tests/test_web_conversion.py` (vista previa, token, resultado, bloqueos) + composición HTMX como en `test_web_nombre_y_foco.py` |
| #480 | `tests/test_web_comicinfo.py` + `tests/test_tagger_plan_token.py`; regresión de `tests/test_enriquecimiento_plan.py`/B6 |
| #481/#482 | pruebas de precedencia y fusión por campo; `#109` y #128 reutilizados |
| Todas | PASS/FAIL/NOT RUN separados; CI ligada al SHA exacto; `docs/BACKLOG.md` al cerrar; navegador real donde haya pantalla |

### 8.3 NOT RUN (no medido, no inferido)

- Tiempo, memoria, espacio y tamaño de conversión en la Pi; RAR sólidos grandes; RAR5 sólido (limitación
  conocida de `unar` 1.10.8); ficheros dañados/cifrados reales; lectura en frío desde el USB.
- Cuántos archivos se comparten y qué expone `amuleweb`; comportamiento de Transmission con archivos de
  la biblioteca; Kavita con cambio de extensión (progreso/duplicados).
- Revisión de vulnerabilidades de `unar`/GNUstep (pendiente desde #308).
- Navegador real de la UI de #478/#480; accesibilidad y Pi.
- Benchmark de referencias de #477/#488: la ficha BL-CNV ya existe; no se rehace aquí.

---

## 9. Decisiones abiertas del PO (hechos vs propuestas) y caducidad

**Hechos (verificados en `a7038d8`):** no existe conversión; B6 solo CBZ y solo CLI; `unar` está en la
imagen con los topes de `lector_rar.py`; `.zascarr` no está excluido hoy de los recorridos; D2 no tiene
carpeta ni «Vaciar» implementados; `tagger.py` no consulta si un archivo se comparte; `File` tiene los
campos de hash/ruta necesarios; la cuarentena puede vivir en JSONB + diario sin migración.

**Propuestas que decide el PO:**

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| P1 | ¿Se exige declarar carpetas compartidas para habilitar conversión/ComicInfo? | (a) sí, bloqueo; (b) aviso y decisión de la persona | **(b)** (enmienda PO 2026-11-09): si no consta, `no_se_sabe` + advertencia + confirmación |
| P2 | «Vaciar» la cuarentena | (a) borrar definitivo con confirmación y tandas; (b) mover a papelera del sistema | **(a)**, sin depender del escritorio; solo bajo `.zascarr` |
| P3 | Deshacer: qué pasa con el `.cbz` generado | (a) moverlo a la cuarentena de la operación; (b) borrarlo | **(a)** (no borrar nada sin confirmación específica) |
| P4 | ¿Migración/tabla de operaciones de conversión? | (a) no: JSONB+diario; (b) tabla nueva + migración | **(a)**; si #479 necesita consultas masivas, se decide entonces (ADR y migración aparte) |
| P5 | ¿Autoriza la medición de #477 en la Pi (copias, consultas de solo lectura a Transmission/aMule y Kavita de prueba)? | (a) sí; (b) solo copias/disco, sin clientes | **(a)** con las garantías de §4; sin ella, celdas NOT RUN y #478 no se compromete |
| P6 | aMule sin API de compartidos: ¿vale «carpetas declaradas» como fuente principal? | (a) sí, y `no_se_sabe` si no consta; (b) explorar `amuleweb` y bloquear hasta tenerlo | **(a)** primero; `amuleweb` se mide en #477 |
| P7 | Si #477 mide muchos RAR5 sólidos no extraíbles: ¿se acepta el bloqueo por archivo o se busca lector alternativo? | (a) bloquear con motivo; (b) abrir otra evaluación de lector | **(a)**; (b) solo con cifras y decisión aparte |
| P8 | Ubicación de la UI: lista de archivos de la ficha de serie ahora y ficha de número cuando #447 esté | (a) sí; (b) esperar a #447 | **(a)**, reutilizando la lista existente |
| P9 | ¿ADR nuevo para la escritura de conversión (original apartado, publicación atómica, guardián)? | (a) sí, ADR 0016; (b) contrato solo en esta spec | **(a)**: es una escritura nueva sobre el archivo del coleccionista |
| P10 | Umbrales de #477 para repriorizar #478/#479 (p. ej. si >80 % compartido) | los de §4.5 u otros | Acordarlos **antes** de medir; no cambiarlos al ver los datos |
| P11 | Aceptar la exclusión de `.zascarr/` en el recorrido de biblioteca (toca BL-R9/#326) | (a) sí; (b) montar la cuarentena fuera de la biblioteca (otro volumen, más instalación) | **(a)**: una regla y su prueba; (b) si el PO prefiere no tocar el recorrido |

**Bloqueos para pasar a «Lista para desarrollar»:** #477 con autorización y evidencia (P5/P10); #488
refinada y aceptada (puede implementarse antes, sin depender de #477 salvo aMule); #478 no empieza sin
#477 y #488; #480 no empieza sin #488; #481 depende de #448; #482 se refina aparte. #479/#481/#482 no
se comprometen hasta las cifras.

**Caducidad:** la de la ficha (~2027-01-06, o antes si cambia #418, B6, el contrato de #307 o la
decisión sobre `unar`). Este documento no autoriza código, conversiones, migraciones, fuentes reales,
Pi ni despliegue; no mueve el tablero.
