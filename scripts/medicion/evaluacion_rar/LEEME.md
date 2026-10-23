# Evaluación del lector RAR/CBR en la Pi (spike #308) — cómo se ejecuta

**Qué es:** medir si herramientas como `unar`, `bsdtar` y `unrar` (y `rarfile`) pueden leer el contenido de tus RAR/CBR dentro del presupuesto de la Pi. Protocolo: `docs/design/protocolo-evaluacion-lector-rar.md`. **No cambia ZascArr, ni su imagen, ni tu biblioteca.**

**Autorizado por el PO en el chat de la sesión (2026-10-22), con sus palabras: «acepto un paso con red en un contenedor desechable. Las muestras a tu criterio. Me sirven los umbrales».** Umbrales: ≤ 256 MiB de memoria, ≤ 5 s la primera página, cualquier muerte por memoria es FAIL. Los pasos 1 a 4 se siguen ejecutando **de uno en uno, y el 3 pide escribir SI**.

**Garantías**
- La biblioteca **no se monta** en ningún contenedor. Las muestras se **copian** con `cp` (el original no se toca) a `~/eval-rar/muestras`, con el hash comprobado.
- El contenedor de medición corre **sin red**, con **512 MiB sin swap**, sistema de ficheros de solo lectura, muestras en solo lectura y un directorio temporal de 128 MiB.
- Nada se instala en el sistema de la Pi: solo se construye una imagen desechable (`zascarr-eval-rar:local`) a partir de la imagen de ZascArr que ya tienes (sin modificarla ni parar ningún servicio), y se retira al final. El paso 4 retira **solo esa imagen** y, si lo pides, las copias: **no hace ninguna limpieza general de Docker** (la caché de construcción de BuildKit puede quedar; no se toca).

## Pasos (en la Pi, como `pi`; cada uno por separado)
0. `bash paso0-clasificar.sh` — **solo lectura**. Dice el formato de los 21 `.rar`, el `.tar`, los 12 sin extensión y unos `.cbr` típicos. Pásame el resumen y `~/eval-rar/salida/clasificacion.tsv`.
1. `bash paso1-copiar-muestras.sh` — copia las muestras de `muestras.txt` (revísala antes: son las que elegí) y verifica los hashes. Comprueba que hay espacio libre (al menos el doble).
2. `bash paso2-preparar-imagen.sh` — **con red**: construye la imagen de evaluación (instala `unar`, `libarchive-tools`, `unrar` solo para comparar, y `rarfile` de PyPI). Para no instalar `unrar`: `CON_UNRAR=0 bash paso2-preparar-imagen.sh`. Anota versiones y licencias en `salida/herramientas.txt`.
3. `bash paso3-medir.sh` — **sin red**. Pide escribir `SI`. Tarda entre 15 y 40 minutos. Antes de lanzarlo: sin descargas ni importaciones en curso. Opcional: `DROP_CACHES=1 bash paso3-medir.sh` vacía la caché de disco (pide `sudo`) para medir «en frío». Modo rápido: `REPS=1 bash paso3-medir.sh`.
4. `bash paso4-limpiar.sh` — retira las imágenes de evaluación. Para borrar también las copias (solo las `m01…`/`s01…` que crearon estos pasos; sin `rm -rf`): `BORRAR_MUESTRAS=si bash paso4-limpiar.sh`.

## Qué pasarme
`salida/resumen.md`, `salida/entorno.txt`, `salida/herramientas.txt` y las últimas líneas de `salida/banco.log`. Son nombres de ficheros, tiempos y memoria; nada del `.env` ni de la base.

## Reglas
Un fallo detiene el proceso: no reintentes ni arregles sobre la marcha. No lo ejecutes mientras haya descargas en curso. Una celda que no se pueda medir queda **NOT RUN** (por ejemplo, RAR sólido si ninguna muestra lo es, o un RAR cifrado: no hay con qué crearlo).


## Segunda tanda (cierra los NOT RUN de `docs/design/evaluacion-lector-rar-2026-10-23.md`)
**No cambia ZascArr, su imagen ni tu biblioteca.** Cada paso se ejecuta de uno en uno; los que tocan algo piden escribir `SI`. Un fallo detiene el proceso: no reintentes ni arregles sobre la marcha.

5. `bash paso5-censo-y-muestras.sh` — **A) solo lectura:** lee los primeros 4 KiB de cada `.cbr`/`.rar`/sin extensión de la biblioteca y cuenta cuántos son RAR4/RAR5, **sólidos** o **cifrados**. **B)** propone por regla fija 2 sólidos (el mayor hasta 300 MB y uno mediano), hasta 2 cifrados y 24 `.cbr` típicos; si escribes `SI`, los **copia** (`cp`) como `s01…` con el hash comprobado. Pásame la salida y `salida/censo-cabeceras.tsv`.
6. `bash paso6-medir2.sh` — **sin red**. Prueba corta antes: `SOLO=m02 MODOS=integridad,corrupto bash paso6-medir2.sh`. Mide: la página es de verdad la del archivo (tamaño + CRC del listado + `Image.load()`), copias **dañadas** (truncada, cabecera cortada, un byte cambiado, 4 KiB a cero), topes desde fuera (tamaño de fichero, memoria, tiempo), cifrados y `ComicInfo.xml`. Los daños se aplican a copias dentro del contenedor.
7. `bash paso7-frio.sh` — **sin red, pide sudo** (solo escribe en `/proc/sys/vm/drop_caches`). Vacía la caché antes de cada muestra y mide en frío. Las copias están en el disco del sistema; el USB de la biblioteca no se toca.
8. `bash paso8-imagen-solo-unar.sh` — **con red** (unos MB de Debian): construye una imagen desechable con **solo** `unar` y anota cuánto cuesta frente a la imagen de ZascArr, con el desglose por paquete.

Qué pasarme: `salida/resumen2.md`, `salida/resultados2.jsonl`, `salida/banco2.log`, `salida/entorno2.txt`, `salida/frio.md`, `salida/solo-unar.txt`, `salida/censo-cabeceras.tsv` y `salida/muestras2.txt`. Son nombres de ficheros, tiempos y memoria; nada del `.env` ni de la base.

**Qué NO cubre, y se queda NOT RUN:** una bomba de descompresión real (no hay con qué crearla), un RAR cifrado si el censo no encuentra ninguno, y la lectura en frío desde el disco USB de la biblioteca.
