# Checklist de despliegue — BL-R9 en la Pi

> Acompaña a la especificación `docs/design/especificacion-BL-R9-rescan-biblioteca.md`. La ejecuta el
> operador/PO; la aprobación del despliegue es una decisión aparte de la fusión.

## Antes de actualizar

1. **Backup** con `scripts/backup.sh` y verificar que el estado de copias en Estado queda al día.
2. **Nota de la primera pasada:** la migración 0021 es aditiva (`files.file_mtime_ns`, sin default).
   El PRIMER rescan re-tría una sola vez todos los archivos registrados (línea de base): lee cada
   CBZ/CBR. Con ~1.500 archivos reales en USB, espera **decenas de minutos** (medición sintética local:
   18,6 s por 1.200 archivos pequeños en SSD; la Pi y el USB no están medidos — NOT RUN).

## Actualizar

3. `scripts/update.sh --rama main` (como siempre: backup verificado, `--ff-only`, migraciones y
   healthcheck).
4. Comprobar en Estado que la app arranca y que la migración consta (`docker compose exec zascarr
   alembic current` → `0021`).

## Primer rescan (a mano, en un momento tranquilo)

5. Auditoría → «Reescanear la biblioteca». Se puede cerrar la página: sigue en segundo plano.
6. Revisar el resumen por categorías. **Esperado sin sorpresas:** aparecerán como «no disponibles»
   las filas que ya apuntaban a rutas inexistentes (p. ej. las 14 referencias obsoletas conocidas), y
   las copias idénticas sin fila se informarán como repetidas (contrato #326: siguen saliendo en cada
   pasada). Nada se mueve, renombra ni borra.
7. Si algo no cuadra: `scripts/rollback.sh` (la migración 0021 se quita con `alembic downgrade 0020`;
   los datos no se pierden porque la columna es nueva).

## Cadencia periódica

8. Confirmar en Auditoría que dice «Además, ZascArr lo hace solo una vez al día» y, al día siguiente,
   que el resumen aparece con disparador «automática».
9. Ajustar si hace falta: `RESCAN_INTERVAL_MINUTES` en el `.env` (1440 = diario; 0 apaga el periódico
   y queda solo el botón). Requiere `docker compose up -d` para releerlo.

## Verificaciones NOT RUN que conviene observar en la primera semana

- Tiempo real del rescan sobre el disco USB y memoria del proceso en la Pi.
- Que el rescan diario no coincida de forma molesta con el ciclo del importador (comparten turno: el
  perdedor se salta esa pasada y consta en el log — `rescan.auto_skipped`).
