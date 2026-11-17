# Especificación — BL-DUP2: unir copias idénticas con enlace duro (#265)

**Estado:** implementada; pendiente de verificación manual en navegador sobre la biblioteca real. Depende de BL-DUP0 (benchmark y ADR 0017) y BL-DUP1
(cuarentena, comprobantes y deshacer).

## Contrato

Dentro de un grupo de **contenido idéntico** (mismo SHA-256 verificado en el momento), la
persona elige una copia que se queda. Las demás:

1. se mueven a la cuarentena de BL-DUP1 (no se borran);
2. en su ruta original se publica un **enlace duro** a la copia que se queda.

Las dos rutas siguen existiendo y, una vez vaciada la cuarentena, ocupan un solo bloque de
datos. Mientras la cuarentena contenga la copia original, el espacio **no** está liberado: la
pantalla no debe prometerlo.

## Invariantes

- Solo contenido idéntico; hash y tamaño revalidados justo antes de actuar.
- Misma montura (`st_dev`) y `os.link`; si falla por `EXDEV` u otro error, el grupo se rechaza
  sin copiar ni dejar la cuarentena a medias.
- Temporal junto a la copia sustituida; `os.replace` atómico. Un fallo compensa los enlaces ya
  hechos y deja las rutas como estaban.
- La operación se escribe (`en_curso` + grupos) antes de tocar el disco; es idempotente.
- El catálogo no crea filas nuevas. Si ya había una `File`, sigue apuntando a una ruta que
  existe; si hay más de una fila para el grupo, se rechaza (`catalogo_ambiguo`).
- Deshacer exige que la copia original siga siendo enlace de la que se queda; si alguien la
  cambió o la sustituyó, no se pisa: se rechaza.
- No hay borrado, ni purga automática, ni reflinks, ni enlaces simbólicos.

## UI

En «Duplicados», además de «Ver vista previa» (apartar), existe **«Unir con enlace duro»**.
La vista previa de enlace muestra:

- qué copia se queda y cuáles se enlazan;
- que las dos rutas seguirán existiendo;
- que Kavita y otros lectores pueden mostrarlas por separado;
- que una copia de seguridad sin enlaces duros volverá a ocupar el doble;
- que cambiar el contenido de una cambia la otra;
- que el espacio no se libera hasta vaciar la cuarentena.

La confirmación exige token firmado y la operación se puede deshacer desde la lista de
operaciones mientras la cuarentena siga existiendo.

## Pruebas

- `tests/test_enlace_duplicados_pg.py`: preview sin escritura, enlace de dos/tres copias,
  inodo compartido, cuarentena, catálogo sin duplicados, `EXDEV`, contenido cambiado,
  compensación, idempotencia y deshacer; además, permisos de carpeta y monturas distintas
  reales (`/dev/shm` frente a `/tmp`, con `skip` si no aplica).
- `tests/test_web_duplicados_264.py`: vista previa y confirmación de enlace.
- `tests/test_migracion_apartado_pg.py`: columna `modo` en la migración.

## Límites

- No se ha ejecutado sobre la biblioteca real del PO; las pruebas usan directorios temporales
  y Postgres de prueba.
- No se prueba un corte eléctrico real ni un cambio de contenido concurrente entre el hash y
  el `os.link`; la ventana es pequeña y la operación queda recuperable, pero no está acreditada
  en hardware real.
- No se implementa vaciar la cuarentena (D2 de ADR 0017): el espacio se libera cuando esa
  acción exista.
