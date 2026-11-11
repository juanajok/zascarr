# Censo de anuales en la biblioteca real — 2026-11-11

> **Solo lectura.** Ejecutado en la Raspberry Pi del PO, dentro del contenedor
> `zascarr-orquestador`, con `scripts/medicion/censo_anuales.py`. La conexión
> abrió `BEGIN TRANSACTION READ ONLY`; no se creó, modificó ni movió nada. La
> salida seudonimizada por defecto no se conserva aquí; este informe solo lleva
> agregados y títulos de cómics, no rutas ni nombres de archivo personales.

## Entorno

| | |
|---|---|
| Fecha | 2026-11-11 |
| Equipo | `raspberrypi` (Raspberry Pi 4/5), contenedor `zascarr-orquestador` |
| Biblioteca | `/media/library` (55 de los 55 anuales sin Issue) |
| Esquema | el desplegado en la Pi; no se migró nada |
| Herramienta | `scripts/medicion/censo_anuales.py` de la rama `feat/annuales-fase0` |
| Garantía | transacción `READ ONLY`; 0 escrituras |

## Resultado

| Métrica | Valor |
|---|---:|
| Series en el catálogo | 29 |
| Series con título anual | **0** |
| Archivos con `Annual`/`Anual` en el nombre | **80** |
| … sin `Issue` | **55** |
| … enlazados a una serie **no** anual | **25** |
| … enlazados a una serie anual | **0** |
| Duplicados exactos por SHA-256 entre esos 80 | **0** |

Los 55 sin Issue están todos en `/media/library` y ninguno está marcado como
desaparecido: son archivos presentes, registrados, que el catálogo no ha sabido
clasificar. No son descargas pendientes.

## Los 25 enlaces a la serie madre

| Serie actual | Archivos | Observación |
|---|---:|---|
| `Batman Vol 1` | 15 | Incluye un **pack** `Batman #647-650 y anual 25`; el resto son anuales 11–28 |
| `Batman: Shadow of the Bat` | 4 | Anuales 01–04 enlazados a los años 1993–1996 |
| `Green Lantern` | 3 | Dos `Green Lantern Annual` y un `Green Lantern Corps Annual` |
| `ANIMAL MAN` | 2 | Anuales 01–02 enlazados a `ANIMAL MAN #1` y `#2` |
| `JSA` | 1 | `JSA Annual 01` enlazado a `JSA #1` |
| **Total** | **25** | |

Casos que muestran el mecanismo, no solo el recuento:

- `Animal Man Annual #01` → `ANIMAL MAN #1`; `Animal Man Annual #02` → `ANIMAL MAN #2`.
- `Batman Anual #28` → `Batman Vol 1 #28`.
- `Batman Anual #23` → `Batman Vol 1 #2A3`; el resto de Batman quedó con `A11`, `A12`…
- `Shadow_..._Annual_01...` → `Batman: Shadow of the Bat #1993`; el año se tomó
  como número de la grapa.
- `Green Lantern Annual #01` y `Green Lantern Corps Annual #01` comparten el
  mismo `Green Lantern #1`.
- `JSA Annual 01` → `JSA #1`.

## Los 55 sin Issue

Están en la biblioteca y son anuales de, entre otras, `Batman Anual` (20
archivos), `Superman Batman Anual` (10), `Flash Annual`/`The Flash Annual` (8),
`Injustice` (5), `Detective Comics Annual` (3), `Action Comics Annual` (2),
`Aquaman Annual` (2), `Batwoman Anual` (2), `Earth 2 Annual` (2),
`Teen Titans Annual` (2) y varias más. Hay dos variantes del mismo
`Superman/Batman Anual` con dominio de blog en el nombre, pero **no** son
duplicados exactos por hash: son copias/escaneos distintos y el backfill no
puede fusionarlas por nombre.

Dos nombres no son un anual puro y hay que tratarlos como pack o caso mixto:

- `Batman #647-650 y anual 25` (ya enlazado; es un pack).
- `Injustice ... #25 - Anual` y `51 JLD #34B-Anual2` (sin Issue; mezclan un
  número regular y una marca anual). El censo los cuenta porque llevan
  `Anual`, pero no deben convertirse en un Issue anual sin revisión.

## Lectura

1. **No hay una sola serie anual en el catálogo.** Los 80 archivos están
   repartidos entre «enlazado al padre» (25) y «sin Issue» (55); no existe el
   espacio propio que propone la fase 1.
2. **Los 25 enlaces no son un problema teórico:** Animal Man, Batman, Green
   Lantern y JSA están ocupando el número de la grapa; los huecos de la serie
   madre pueden estar ocultando esos anuales como si fueran grapas.
3. **Los 55 sin Issue son la deuda principal:** están en la biblioteca, no en
   descargas, y hoy no se pueden ver como anuales ni completar su línea.
4. **El parser tenía un segundo fallo, ya corregido en la rama:** en nombres
   con un año suelto (`Shadow_..._Annual_01_..._1993`) se tomaba `1993` como
   número. Ahora el número pegado a `Annual`/`Anual` gana; se prueba en
   `tests/test_naming_core.py`.
5. **El nombre no basta para crear la serie anual.** `Batman Anual` y
   `Batman Annual`, `Flash Annual` y `The Flash Annual`, `Shadow Of The Bat
   Annual` y `Batman: Shadow of the Bat Annual` son variantes de la misma
   línea; la fuente (Comic Vine/GCD/Metron) o una confirmación humana deben
   decidir el título canónico y el padre.

## Siguiente fase

La decisión A sigue siendo la adecuada, pero el backfill no es un
`UPDATE` masivo:

1. Crear las series anuales con `kind=annual` y `parent_series_id` (migración
   aditiva; aún no autorizada).
2. Proponer, no aplicar: agrupar los 80 archivos por línea anual, normalizar
   `Anual`/`Annual` y `The Flash`/`Flash`, y resolver las variantes de padre
   con la fuente.
3. Separar los packs (`Batman #647-650 y anual 25`, `Injustice #25 - Anual`,
   `51 JLD #34B-Anual2`) antes de enlazar.
4. Los 25 enlaces actuales se revisan uno a uno; no se mueven en silencio.
5. Solo después, crear Issues anuales y mover los archivos con vista previa y
   confirmación, conservando los 55 sin Issue si no hay serie/padre fiable.

**Nada de esto se ha ejecutado en la Pi.** El censo es solo lectura y la fase 1
necesita autorización explícita para crear el esquema y proponer el backfill.
