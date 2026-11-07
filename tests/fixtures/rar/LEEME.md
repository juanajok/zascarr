# Fixtures de RAR (#418, BL-PORT3)

Cuatro RAR mínimos para las pruebas con `unar` real (`tests/test_lector_rar_real.py`). **Se crean a mano**
con el `rar` oficial (no es software libre y no se puede generar desde el repositorio); el PO los acepta
antes de fusionar. Imágenes **sintéticas**: nada de la biblioteca real.

| Fichero | Formato | Contenido (por este orden) |
|---|---|---|
| `minimo_rar4.cbr` | RAR 4 | `01.jpg` (JPEG 8×8 **rojo**), `02.jpg` (8×8 azul) |
| `minimo_rar5.cbr` | RAR 5 | `01.jpg` (8×8 **rojo**), `02.jpg` (8×8 azul) |
| `solido_rar4.cbr` | RAR 4 sólido | `01.jpg` (8×8 **rojo**), `02.jpg` (azul), `03.jpg` (verde) |
| `solido_rar5.cbr` | RAR 5 sólido | igual; **solo documenta una limitación de `unar`** (ver abajo), no se espera que se lea |

Cada uno < 5 KB. Las pruebas esperan que `01.jpg` sea rojo (R > 150, G y B < 100 en el centro).

## Cómo se crearon (2026-11-06)

Con el PO autorizando solo esto: contenedor desechable (`--rm`) de `debian:stable-slim` (digest
`sha256:fbfb4059d2127120aa05b6e6064523d2102552f0cf0026ddf0701c12f1f8f3e0`, creada el 2026-11-04, Debian 13.7), con el
paquete `rar` de non-free instalado por `apt` (**rar 2:7.11-1**, «RAR 7.11 … Trial version»), montando solo esta
carpeta. Las imágenes (JPEG 8×8, Pillow, calidad 95: `01` = (220, 20, 20), `02` = (20, 20, 220), `03` = (20, 200, 20))
se generaron antes y se borraron después.

```bash
rar a -ep -ma5 -m3    minimo_rar5.cbr 01.jpg 02.jpg
rar a -ep -ma5 -m3 -s solido_rar5.cbr 01.jpg 02.jpg 03.jpg
```

**`minimo_rar4.cbr`** (RAR 4) se creó el 2026-11-07 con **rar 6.24** (3 oct 2023), porque `rar` 7.x ya no crea RAR 4
(`ERROR: Unknown option: ma4`; ni el de `stable` ni el de `bookworm` sirven: 7.11 y 7.01). Origen: paquete oficial
`https://www.rarlab.com/rar/rarlinux-x64-624.tar.gz` (614 146 B), **SHA-256 `88e22a8e84125c947637bbf28c746e338a0a63279d80f9f9d7373603875db1eb`**.
> **Aviso: ese hash no es verificable contra un valor publicado** (RARLAB no publica sumas ni firmas); solo se anota lo
> descargado por HTTPS desde rarlab.com. El PO lo aceptó el 2026-11-07. El paquete se ejecutó únicamente dentro de un
> contenedor desechable de `debian:bookworm-slim` (digest
> `sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc`, Debian 12.15), con `--network none`, el
> paquete montado en solo lectura y montando solo esta carpeta.

```bash
rar a -ep -ma4 -m3 minimo_rar4.cbr 01.jpg 02.jpg      # rar 6.24; imágenes 8×8: 01 = (220, 20, 20), 02 = (20, 20, 220)
```

**`solido_rar4.cbr`** se creó el 2026-11-07 con el mismo `rar 6.24`, paquete, imagen y condiciones que `minimo_rar4.cbr`
(`rar a -ep -ma4 -m3 -s solido_rar4.cbr 01.jpg 02.jpg 03.jpg`).

## Limitación conocida: `unar` no lee un RAR 5 sólido

Medido el 2026-11-07 con `unar`/`lsar` **v1.10.1** (paquete `1.10.7+ds1+really1.10.1-2+b2` de Debian bookworm, imagen de
producción; digest de la imagen `sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc`) y con **v1.10.8**
(runner de CI): `lsar` lista `solido_rar5.cbr` bien, pero `unar` falla con «Attempted to read more data than was
available». `minimo_rar4`, `minimo_rar5` y el RAR 4 sólido sí se leen. En producción un RAR 5 sólido da `ilegible` → marca de
fallo → cascada de portada, sin error 500. La prueba `test_rar_real_un_rar5_solido_no_se_lee_limitacion_conocida_de_unar` es un
`xfail(strict)` que avisa si una versión futura de `unar` lo arregla.

## Huellas

| Fichero | Tamaño | SHA-256 |
|---|---|---|
| `minimo_rar4.cbr` | 982 B | `d6b611df379a9e8b503934641c7e72c0596ebf59e8fc47acb7f75607e0098fe4` |
| `minimo_rar5.cbr` | 995 B | `0e1e5aedab26374fa2008ee274d05e6d3b9da098bfd5de4c3368addfe02a8c9a` |
| `solido_rar4.cbr` | 641 B | `b211713ecd440a6b07bb0607bad507a167da9c22f063cf7e3f956fad1abf17af` |
| `solido_rar5.cbr` | 642 B | `fe68f32b540dedc928e04d8c09ec6f387c3f76e0b09f414953027e1068155dbe` |

Comprobado con `unrar lt` (UNRAR 7.20): `minimo_rar4` = firma `Rar!\x1a\x07\x00` (RAR 1.5–4.x; `unrar` lo llama «RAR 1.5») con `01.jpg`, `02.jpg`; `minimo_rar5` = «RAR 5» con `01.jpg`, `02.jpg`; `solido_rar5` = «RAR 5, solid» con
las tres. Con `unar`/`lsar` reales no se ha comprobado aún (no hay en la máquina de desarrollo): lo hará la CI.

## Lo que NO hay (NOT RUN real)

RAR cifrado y multivolumen: crearlos exige una muestra que no se puede fabricar aquí; solo se prueban con
el `lsar`/`unar` falso de `tests/_rar_falso.py`.
