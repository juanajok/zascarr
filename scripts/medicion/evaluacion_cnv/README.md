# BL-CNV0 — medición de conversión CBR→CBZ en la Pi

Kit mínimo de la medición de #477. **No es código de producción**. Todo lo que escribe vive en `~/eval-cnv` (fuera de la biblioteca); los contenedores de conversión solo montan las copias en lectura.

## Orden de ejecución (en la Pi, como `pi`)

1. Exportar los CBR registrados desde la BD (solo lectura):
   ```sh
   docker exec -e PGPASSWORD=... zascarr-db psql -U ... -d ... -Atc \
     "select file_path from files where lower(file_path) like '%.cbr' order by file_path" \
     > ~/eval-cnv/cbr-registrados.txt
   sed 's#^/media/library/##' ~/eval-cnv/cbr-registrados.txt > ~/eval-cnv/list.txt
   ```
2. `censo-cabeceras.tsv`: cabeceras RAR4/RAR5/sólido/cifrado/ZIP (se apoya en
   `evaluacion_rar/censo_cabeceras_rar.py`).
3. `censo_lsar.py`: contenedor desechable con la biblioteca en solo lectura y `list.txt`;
   cuenta listables, no listables, anidados y volúmenes. Sin red, root read-only, 512 MiB.
4. `seleccionar_muestra.py`: regla fija; copia 26 muestras, comprueba SHA-256 original=copia.
5. `medir_muestras.sh`: un contenedor desechable **por copia**, `--network none --read-only`,
   512 MiB sin swap; el temporal va a `~/eval-cnv/trabajo` (disco, fuera de la biblioteca): `unar` + `zipfile(ZIP_STORED)`, manifiesto y `testzip`.
6. Prototipo de memoria baja (opcional): `convertir_streaming.py` / `medir_streaming.sh` usan
   `unar -o - -i <archivo> <índice>` y escriben el ZIP_STORED en streaming. Se midió y **no es
   viable**: mucho tiempo en sólidos y sin bajar el pico de 512 MiB; ver §4ter del informe.
7. Contraste: Transmission/aMule/Kavita y vulnerabilidades de `unar`.

Los scripts no montan la biblioteca en ningún contenedor de conversión. Las
rutas y nombres de la muestra no se publican; solo los identificadores `m01…`.

## Umbrales

Están en `docs/design/benchmark-BL-CNV-datos.md` §3 y se fijaron antes de la pasada de
conversión: P10/P90/máximo de tiempo y memoria, espacio temporal, ratio CBZ/CBR y
verificación al 100 %. Un OOM o una extracción fallida es FAIL de esa copia.
