# Informe de validación en la Raspberry Pi — MVP «vincular series ya existentes»

> Ejecución del guion `docs/design/guion-validacion-pi-mvp.md` (plantilla del §11). Sin nombres de archivo ni
> rutas reales de ninguna biblioteca: todo el contenido de prueba es sintético.

```
Fecha:               2026-10-13 / 2026-10-14
Quién:               operador de la Pi, con asistencia de Claude
Commit desplegado:   a5369ef (merge de #191 sobre 075470e, que incluye #187)
Equipo (V-00):       Raspberry Pi 5 Model B Rev 1.1 · 4 GB RAM (1578 MB disponibles al empezar)
                     NVMe 235 GB · kernel 6.18 aarch64 · Docker 29.9.0 · Compose 5.6.0
Pila:                aislada (sí), proyecto `zascarr-val`, 127.0.0.1:18000
Biblioteca:          sintética · 321 archivos (320 numerados + 1 sin número)
Umbral D8 (V-50):    confirmar 100 archivos en < 30 s, sin errores ni 503, memoria bajo el tope
Resumen:             PASS 36 · FAIL 0 · NOT RUN 2 · datos 3
FAIL de seguridad:   ninguno (V-40…V-43 en PASS)
Producción tocada:   por el guion, no (V-43 idéntica). Antes del guion, en la misma sesión, sí: ver «Contexto».
```

## Resultados

| ID | Resultado | Evidencia |
|---|---|---|
| V-00 | dato | equipo y recursos de arriba; 55,4 °C al empezar |
| V-01 | PASS | 1578 MB disponibles (mínimo 1024) |
| V-02 | PASS | Compose 5.6.0 (mínimo 2.24) |
| V-03 | PASS | el commit contiene #187 |
| V-04 | dato | producción antes: `files\|issues\|series` = `1339\|0\|6` |
| V-05 | PASS | puerto 18000 libre |
| V-10 | PASS | `database=ok`, cuatro fuentes `disabled`; `degraded` esperado |
| V-11 | PASS | 85 / 54 / 4,7 MiB frente a 512 / 512 / 128 MiB, topes ya aplicados |
| V-12 | PASS | «Se han mirado 321 tebeos… Tu biblioteca está limpia» |
| V-13 | PASS | `grupos=1`, 321 archivos. **El tiempo de adopción no es una medición válida** (ya estaba escaneado) |
| V-14 | PASS | manifiesto idéntico tras adoptar |
| V-15 | PASS | ninguna mención a fuentes en el log |
| V-16 | PASS | 0 errores desde el último arranque; el error previo es el de arrancar antes de migrar (guion §10, hallazgo 2) |
| V-17 | PASS | alta por API devuelve UUID (título «Prueba API», distinto a propósito) |
| V-17b | PASS | alta por la interfaz con carpeta: «creada», serie vacía, sin vincular |
| V-17c | PASS | alta por Descubrir sin carpeta: «no hay ninguna vinculación pendiente» |
| V-20 | PASS | carpeta con 321 registros y enlace «Elegir la serie de esta carpeta» |
| V-21 | PASS | «no ha consultado ninguna fuente»; al buscar, «No hay ninguna fuente activa» |
| V-22 | PASS | 100 archivos «Sin marcar», «archivos 1–100» |
| V-23 | PASS | «Lote preparado: 3 archivos»; «Escrito por ti (el nombre decía 3)» |
| V-24 | PASS | página 2 con «Trabajo guardado en otras páginas»; al volver se recupera |
| V-25 | PASS | «Hecho… 3 vinculados», nada movido ni renombrado |
| V-26 | PASS | recargar no cambia nada (316 pendientes antes y después) |
| V-27 | PASS | «Vinculación parcial», «Esto NO está completo», «Cambió (tamaño o fecha) mientras revisabas» |
| V-28 | PASS | «Revisar de nuevo»: vista nueva, sin lote; el archivo vuelve a ser marcable y se vincula |
| V-29 | PASS | `Sin numero.cbz` no marcable hasta escribir un número |
| V-30 | PASS | tras `docker kill`+`start`, mismo token → `repetida:true`, mismo `operacion_id` y totales |
| V-31 | PASS | dos confirmaciones a la vez: una `false` y otra `true`; pendientes −2 exactos |
| V-32 | PASS | tras 16 min: `410 token_caducado`, `puede_haberse_aplicado=false`, sin cambios |
| V-33 | PASS | dump íntegro; recuentos `311\|311\|8\|3` antes y después de `dropdb`+restaurar |
| V-34 | PASS | tras restaurar, el mismo token devuelve el mismo informe |
| V-35 | NOT RUN | reinicio de la Pi no realizado: corta producción; pendiente de decisión |
| V-36 | NOT RUN | disco casi lleno: opcional y no recomendable en una Pi con producción |
| V-40 | PASS | solo `Flash 310` cambió tras adoptar (+2 bytes, edición deliberada de V-27); 321 ficheros, 3 directorios |
| V-41 | PASS | solo `127.0.0.1:18000` y el 5432 de producción; ningún 6379 |
| V-42 | PASS | 0 líneas de aviso o error con ruta o nombre de archivo (24 avisos en total) |
| V-43 | PASS | producción `1339\|0\|6`, contenedores sanos y sin reinicios, health `healthy` |
| V-50 | PASS | 3 rondas de 100: confirmar **0,29 / 0,30 / 0,30 s**; `vinculados_todos`; 100 vinculados |
| V-51 | PASS | `memory.peak`: db 118 MiB, cache 8 MiB, orquestador 137 MiB; `max 0`, `oom 0`, `oom_kill 0` |
| V-52 | PASS (cualitativo) | cuatro páginas recorridas sin esperas anormales; **sin tiempos instrumentados** |
| V-53 | dato parcial | carga 0,09–0,16 y RAM 1599 → 1584 MB; fue con la Pi en reposo, **no bajo carga** |

## Desviaciones respecto al guion

- **321 archivos y no 121**, para poder repetir D8 tres veces y paginar (el propio guion lo prevé). Los oráculos de V-12 y
  V-13 pasan a 321.
- **Redis sin `ports: !override []`** en el override: tras #191 ya no publica nada.
- **V-17 con título distinto** al de V-17b, para que el alta por la interfaz no se cruzara con una serie ya creada.
- **V-27 usa `Flash 310`**, no `Flash 010`: este último ya se había vinculado en las rondas de V-50.
- **V-30, V-33 y V-34 encadenados** en un script, dentro de los 15 minutos de vida del token.
- **V-51 se midió con `memory.peak` del cgroup**, no con muestreo de `docker stats`: el muestreador no llegó a tomar
  ninguna muestra porque toda la medición duró ~1 s.
- **El oráculo de V-40 («idéntico») se adaptó**: la edición deliberada de V-27 cambia un fichero. No se guardó la lista del
  manifiesto inicial, solo su hash; se comprobó por fecha de modificación posterior a la adopción, recuento y tamaños.
- **V-23 y V-25 con una herramienta de automatización que truncaba decimales** (`3.5` → `3`). Se aisló: la API conserva
  `5.5` y tecleando de verdad el resultado es «número 5.5». No es un defecto del producto.

## Contexto: lo que se hizo en la Pi antes del guion

Para poder ejecutarlo hubo que arreglar la propia Pi, y conviene que quede registrado porque cambia lo que significa
«producción intacta»:

1. **`update.sh`** llevó producción de `497e925` a `075470e` (migraciones 0018 y 0019) y luego a `a5369ef`.
2. **Cgroup de memoria activado** (`cgroup_enable=memory cgroup_memory=1` en `cmdline.txt`) y contenedores recreados:
   hasta entonces los topes del compose se descartaban en silencio.
3. **Redis en bucle de OOM** al aplicarse el tope de 128M, por un `dump.rdb` de ~160 MB ajeno a ZascArr (7510 claves con
   prefijo `pcp`; que sea Performance Co-Pilot se **infiere** del prefijo, no se verificó). Se despublicó el puerto
   (#191) y el dump quedó apartado como `dump.rdb.ajeno`.

## Hallazgos

| # | Hallazgo | Estado |
|---|---|---|
| 1 | Raspberry Pi OS arranca con el controlador de memoria desactivado; Docker descarta los límites de `deploy.resources` sin avisar | Resuelto en esa Pi. **Pendiente:** que el instalador lo detecte y avise |
| 2 | Redis publicado en `127.0.0.1:6379` fue adoptado por otro proceso del equipo | Resuelto: #191 fusionada y desplegada; #192 documenta el cierre |
| 3 | `redis` y `arq` figuran en las dependencias sin ningún uso; el compose da 128M a un Redis que ZascArr no usa | **Decisión pendiente (b):** retirar Redis, con ADR |
| 4 | `CLAUDE.md` §4 y `services/comic_vine.py` describen un uso de Redis que el código no tiene | Pendiente, junto con (3) |
| 5 | `update.sh` solo hace `up -d zascarr`, que arrastra a Redis por `depends_on`: un dump heredado vuelve a causar el bucle | Anotado en el BACKLOG; se aparta el dump antes de actualizar |
| 6 | La ficha de la serie «En tu biblioteca» no lista números no enteros (p. ej. 5.5): lo vinculado existe pero no se ve | Regla C2 del código; **candidato a backlog de UX**, no un defecto |
| 7 | Arrancar la pila antes de migrar registra un error con traceback (`db_unavailable_at_startup`) | Esperado y documentado; ruidoso para un operador |

## Lo que esta validación NO demuestra

- **Que 100 archivos en menos de 30 s valga para una Pi 4 con tarjeta SD.** Se midió en una Pi 5 con NVMe; el ensayo en
  x86 dio prácticamente lo mismo, así que el margen (~100×) no es extrapolable.
- **El comportamiento bajo carga real** (V-53): Kavita, Transmission y Prowlarr no estaban activos durante la medición.
- **Un reinicio de la Pi con la pila creada** (V-35) ni el disco lleno (V-36).
- **Crear la serie desde una candidata de fuente**, fuentes reales, ni el ensayo completo de `backup.sh`/`rollback.sh`
  de producción. Siguen NOT RUN, como avisaba el guion.
- **Lectores de pantalla ni móvil físico.**

## Decisión que se pide

1. ¿Se acepta el MVP «vincular series ya existentes» como validado **en una Pi 5 con NVMe**, con el umbral de 30 s?
2. ¿Se retira Redis del stack (3 y 4)? Requiere ADR.
3. ¿Se hace V-35 (reinicio) o queda NOT RUN?
4. ¿Qué se hace con `dump.rdb.ajeno` (160 MB)?
5. ¿Se añade al instalador la detección del cgroup de memoria (1)?
