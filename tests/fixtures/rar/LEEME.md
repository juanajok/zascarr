# Fixtures de RAR (#418, BL-PORT3)

Tres RAR mínimos para las pruebas con `unar` real (`tests/test_lector_rar_real.py`). **Se crean a mano**
con el `rar` oficial (no es software libre y no se puede generar desde el repositorio); el PO los acepta
antes de fusionar. Imágenes **sintéticas**: nada de la biblioteca real.

| Fichero | Formato | Contenido (por este orden) |
|---|---|---|
| `minimo_rar4.cbr` | RAR 4 | `01.jpg` (JPEG 8×8 **rojo**), `02.jpg` (8×8 azul) |
| `minimo_rar5.cbr` | RAR 5 | `01.jpg` (8×8 **rojo**), `02.jpg` (8×8 azul) |
| `solido_rar5.cbr` | RAR 5 sólido | `01.jpg` (8×8 **rojo**), `02.jpg` (azul), `03.jpg` (verde) |

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

**`minimo_rar4.cbr` NO está creado:** `rar` 7.x ya no crea RAR 4 (`ERROR: Unknown option: ma4`). Hace falta un `rar`
≤ 6.x (`rar a -ma4 -m3 minimo_rar4.cbr 01.jpg 02.jpg`); sin él, esa prueba se salta y el paso de CI que exige las
pruebas de RAR real sigue en rojo.

## Huellas

| Fichero | Tamaño | SHA-256 |
|---|---|---|
| `minimo_rar4.cbr` | — | _pendiente (ver arriba)_ |
| `minimo_rar5.cbr` | 995 B | `0e1e5aedab26374fa2008ee274d05e6d3b9da098bfd5de4c3368addfe02a8c9a` |
| `solido_rar5.cbr` | 642 B | `fe68f32b540dedc928e04d8c09ec6f387c3f76e0b09f414953027e1068155dbe` |

Comprobado con `unrar lt` (UNRAR 7.20): `minimo_rar5` = «RAR 5» con `01.jpg`, `02.jpg`; `solido_rar5` = «RAR 5, solid» con
las tres. Con `unar`/`lsar` reales no se ha comprobado aún (no hay en la máquina de desarrollo): lo hará la CI.

## Lo que NO hay (NOT RUN real)

RAR cifrado y multivolumen: crearlos exige una muestra que no se puede fabricar aquí; solo se prueban con
el `lsar`/`unar` falso de `tests/_rar_falso.py`.
