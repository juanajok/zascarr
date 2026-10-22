# Protocolo de evaluación de un lector de RAR/CBR (refinamiento de #308)

> **Estado: PROTOCOLO PARA REVISIÓN; no se ha ejecutado nada.** Documento de diseño del spike #308, derivado de `docs/design/benchmark-formatos-contenedor.md` (opción C y §8). **No es código de producto, no instala nada en la Pi ni en la imagen de ZascArr, y no toca la biblioteca.** Cada ejecución de §5 necesita autorización expresa del PO, por pasos. Una medición en un PC **no** se presentará como medición en la Pi.

## 1. Pregunta y decisión que debe permitir
**¿Puede ZascArr leer el contenido de un `.cbr`/RAR (listar, sacar la primera página, leer ComicInfo si existe) de forma segura y dentro del presupuesto de la Pi?** Una oportunidad potencial para los 1234 `.cbr` del disco, **no** una promesa de portadas ni de metadatos: depende del contenido de cada fichero y del lector.

Resultado esperado: una ficha con tabla **PASS / FAIL / NOT RUN** y una recomendación entre **adoptar** (con qué herramienta y límites), **descartar** o **seguir investigando**. No decide la implementación.

## 2. Alcance y límites
- **Sí:** RAR/CBR (v2.0, v4, v5; normal y sólido) con herramientas candidatas; operaciones de **lectura**.
- **No:** 7z, TAR, ficheros sin extensión (cada uno, si procede, su tarjeta; el ZIP por contenido es #307), ni conversión, renombrado o movimiento de ningún original, ni implementación.
- La biblioteca real **no se monta en ningún contenedor de prueba**; solo se usan **copias** (§3).

## 3. Muestras
Se prueban **copias** hechas con `cp` (solo lectura sobre el original) en un directorio de pruebas fuera de la biblioteca (p. ej. `/tmp/muestras-rar`), verificando después `sha256sum` de cada copia frente al original. Candidatas del censo de la Pi (#297; los nombres son los del PO):

| Muestra | Qué es (según `file(1)`) | Tamaño | Por qué |
|---|---|---|---|
| S1 `Graphic Novels/Hard Boiled` | RAR v2.0 | 35 MB | formato antiguo |
| S2 `Graphic Novels/Batman DK2` | RAR v4 | 20 MB | caso normal pequeño |
| S3 `Graphic Novels/Carlos Gimenez/Paracuellos` | **RAR v5** | 67 MB | único RAR5 conocido (es una **copia** de un archivo ya registrado) |
| S4 `Graphic Novels/Tillie Walden` | RAR v4 | 173 MB | el mayor RAR v4: prueba de memoria |
| S5 un volumen de `Manga/One Piece/…` | por determinar (`file` + modo sólido) | por determinar | los 21 `.rar` sin inspeccionar |
| S6 un `.cbr` ya registrado y presente en la base | por determinar | por determinar | el caso típico (1234 en el disco) |

**Antes** de elegir, el PO ejecuta una clasificación de solo lectura (`file -b` y, con la herramienta que haya, el modo sólido: p. ej. `unrar lt` o `7z l -slt`) sobre los 21 `.rar`, los 9 RAR sin extensión y algunos `.cbr`, para saber cuáles son sólidos y cuántos son v5. **Si no hay ninguna muestra sólida real, el caso «sólido» se marca NOT RUN**, no se simula con 7z.

## 4. Herramientas candidatas (a evaluar; licencia y redistribución por separado)
Se evalúan **dentro de un contenedor desechable basado en la misma imagen que ZascArr** (`python:3.11-slim-bookworm`), sin tocar la imagen de producción:

| Candidata | Origen (Debian bookworm) | Notas que hay que **verificar**, no suponer |
|---|---|---|
| `unar` / `lsar` | `main`, 1.10.7+ds1+really1.10.1-2 (**paquete `arm64` disponible**: 1.10.7+ds1+really1.10.1-2+b2, 1,2 MB de descarga) | soporte de RAR5, sólido, memoria; tamaño del paquete y sus dependencias |
| `bsdtar` (`libarchive-tools`) | `main`, 3.6.2-1+deb12u5 (paquete `arm64` disponible: 268 kB instalado) | la propia documentación de `rarfile` dice que su soporte de RAR es «muy limitado»: confirmar con las muestras |
| `unrar` | **`non-free`**, 1:6.2.6-1+deb12u1 (paquete `arm64` disponible, 131 kB de descarga) | solo como referencia de comparación; su licencia y redistribución se revisan aparte antes de plantear incluirlo en una imagen |
| `rarfile` (Python) | PyPI | necesita una herramienta de las anteriores como motor; revisar su licencia y qué hace por sí solo (la lectura de datos sin comprimir) |

Para cada candidata se anota: **paquete exacto y versión, sección/licencia, tamaño instalado y dependencias, y quién la distribuye**. La decisión de licencia es del PO.

## 5. Operaciones, medición y límites de seguridad
**Operaciones por muestra y herramienta:** (1) listar entradas (nombres y recuento); (2) clasificar **tebeo frente a paquete** (¿hay entradas con extensión de contenedor?, idea adaptada de Kapowarr); (3) sacar **solo la primera** y la **última** página a la salida estándar (nunca extraer toda la muestra) y comprobar que **Pillow la decodifica**; (4) leer `ComicInfo.xml` si existe; (5) comportamiento ante un RAR corrupto y uno cifrado (mensaje claro, sin colgarse); (6) si la herramienta indica «sólido», anotarlo.

**Aislamiento (todo obligatorio):**
- Contenedor con `--network none` durante las pruebas (la red solo se usa en un paso previo y aparte para instalar paquetes; ese paso necesita autorización).
- Muestras montadas **solo lectura** (`:ro`); ninguna ruta de la biblioteca; sistema de ficheros `--read-only` con un `tmpfs` de tamaño acotado para trabajo.
- Límites del contenedor que **replican el presupuesto de producción**: `--memory=512m --memory-swap=512m`, CPU acotada, y cada operación bajo `timeout 60`.
- Sin extracción a disco: salida a la salida estándar o `/dev/null`; si una herramienta exige extraer, a un `tmpfs` con tope y sin rutas del propio archivo (sin `..` ni rutas absolutas).
- Registro de cada operación: tiempo, **pico de memoria** (`/usr/bin/time -f '%e %M'`), código de salida y si hubo muerte por falta de memoria (OOM) del contenedor.

**Se interrumpe** una ejecución si supera los 60 s, si el contenedor muere por memoria o si una herramienta intenta escribir fuera del `tmpfs`. Esas interrupciones son **FAIL** con su causa.

## 6. Dónde se mide
| Entorno | Para qué | Se presenta como |
|---|---|---|
| PC del PO o de desarrollo | iterar el procedimiento | «medido en PC» (no sustituye a la Pi) |
| **Pi del PO** (**aarch64**, confirmado por el PO el 2026-10-22 con `uname -m`; versión de Docker por anotar: `docker version`) | **las cifras que cuentan** | «medido en la Pi» |

Si algo solo se midió en PC, la tabla final lo dice así y el criterio de coste en Pi queda **NOT RUN**.

## 7. Criterios de decisión (PROPUESTOS; el PO los confirma antes de medir)
| Criterio | Umbral propuesto para «adoptar» |
|---|---|
| Compatibilidad | Lista y saca una página decodificable en **todas** las muestras RAR v4 y, si hay muestra, RAR5; para RAR5 sin soporte, mensaje claro y causa y acción documentadas (no un error) |
| Memoria en la Pi | Pico **≤ 256 MiB** (la mitad del presupuesto de 512 MiB) en las muestras no sólidas; **cualquier** muerte por memoria es FAIL; el caso sólido, si existe, se anota aparte |
| Tiempo | Primera página **≤ 5 s** por muestra de hasta ~200 MB en la Pi |
| Seguridad | Ninguna escritura fuera del `tmpfs`; topes de entradas/tamaño definidos y probados; fichero corrupto o cifrado → fallo controlado |
| Licencia y redistribución | Paquete en Debian `main` **o** aceptación expresa del PO tras revisar la licencia concreta |
| Dependencia | Coste en tamaño de imagen y en superficie de ataque aceptado por el PO (CLAUDE.md §2: «sin dependencias nuevas sin justificación») |

Resultado: **adoptar** (todos), **descartar** (algún FAIL de seguridad, memoria o licencia sin solución) o **seguir investigando** (NOT RUN en un criterio clave).

## 8. Salida
Una ficha `docs/design/evaluacion-lector-rar-<fecha>.md` con: muestras (formato, tamaño, sólido o no, origen), herramientas (paquete, versión, licencia), la tabla **muestra × herramienta × operación** con tiempo/pico/resultado, un **PASS / FAIL / NOT RUN** por criterio de §7, el entorno de cada cifra (PC o Pi) y la recomendación. Sin datos sensibles: nombres de ficheros del PO solo los imprescindibles, nada de rutas internas ni del `.env`.

## 9. Pasos y autorizaciones (todos del PO, por separado; nada se hace hasta entonces)
1. **Clasificar** los RAR y elegir las muestras (solo lectura).
2. **Copiar** las muestras elegidas a un directorio de pruebas y verificar hashes.
3. **Preparar el contenedor de pruebas** (paso con red: descarga de paquetes; fuera de la imagen de ZascArr).
4. **Ejecutar** las operaciones (§5) en la Pi y, opcionalmente, en el PC.
5. **Retirar** el contenedor y el directorio de pruebas.

## 10. Preguntas abiertas para el PO
- **Respondida:** la Pi es **aarch64** (2026-10-22). Consecuencia: el contenedor de pruebas debe ser `arm64`, los tres paquetes candidatos existen para `arm64` en bookworm, y las cifras de un PC `x86_64` son aún menos comparables; los binarios `rar` que lleva Kapowarr en su repositorio son una referencia de diseño, no algo utilizable aquí.
- ¿Versión de Docker de la Pi? ¿Está ya la imagen base `python:3.11-slim-bookworm` (arm64) en la Pi?
- ¿Se acepta un paso con red en un contenedor desechable para instalar `unar` y `libarchive-tools` (unos pocos MB) y, aparte, `unrar` solo como comparación?
- ¿Qué muestras prefiere el PO (§3) y si hay alguna que **no** quiera copiar?
- ¿Umbrales de §7 conformes?

## 11. Qué NO se hace aquí
Implementar nada en ZascArr; añadir dependencias a la imagen; abrir, renombrar, mover, convertir o borrar originales; montar la biblioteca; ampliar a 7z, TAR o formatos sin extensión; presentar una cifra de PC como cifra de la Pi.
