# Tarjeta del tablero — BL-R9: Reescanear la biblioteca (a demanda y periódico)

> Propuesta lista para publicar en el tablero (formato `zascarr-kanban:v1`). La publica el PO.
> Feature padre: BL-R (Reconciliación de la biblioteca, #228). Ficha: `docs/design/benchmark-BL-R9-rescan-biblioteca.md`.
> Especificación: `docs/design/especificacion-BL-R9-rescan-biblioteca.md`.

```markdown
<!-- zascarr-kanban:v1:BL-R9 -->
# BL-R9: Reescanear la biblioteca (a demanda y periódico)

Como coleccionista, quiero que ZascArr reescanee mi tebeoteca — a demanda o periódicamente — y
actualice la biblioteca (archivos nuevos, movidos, sustituidos y desaparecidos) y añada a revisar lo
que no identifique, para que la biblioteca esté al día sin que yo tenga que acordarme de pulsar
botones.

## Origen y evidencia
- Hueco real: el ciclo del importador solo mira descargas y disponibilidad; registrar lo nuevo exigía
  Auditoría → «Buscar archivos nuevos» → confirmar (4 pasos a mano, #326). Un archivo sustituido en su
  misma ruta no se detectaba (límite documentado en `registro-incremental-326.md` §7).
- Ficha de benchmark (nivel 2): `docs/design/benchmark-BL-R9-rescan-biblioteca.md` (Sonarr, Komga,
  Kavita, Jellyfin, Plex, Kapowarr, Kodi; adoptar/adaptar/mejorar/construir/descartar por idea, con
  versión/commit).

## Decisión del PO (2026-11-06)
1. El periódico registra SIN confirmación: lo identificado con confianza va a su serie; lo dudoso, a
   «Por revisar». El manual conserva la garantía U21 junto a la acción.
2. Cadencia por defecto: DIARIA (`rescan_interval_minutes=1440`; 0 la apaga).
3. Sustituidos: sí, con stat guardado por ruta (`file_mtime_ns`, migración 0021) y re-triaje.
4. El botón vive en Auditoría.
5. Sin watchdog en esta entrega (mejora futura).

## Criterios de aceptación
1. Botón «Reescanear la biblioteca» en Auditoría: un paseo de la biblioteca que registra lo nuevo
   (serie o «Por revisar»), re-tría lo sustituido sobre la MISMA fila, reenlaza movidos y
   marca/revierte desaparecidos — sin mover, renombrar ni borrar nada y sin consultar fuentes.
2. Cadencia periódica configurable con default diario; el automático y el manual comparten el cerrojo
   de ciclo con el importador (nunca coinciden dos paseos de disco); un segundo disparo no duplica.
3. Informe honesto por categorías, persistido en `import_runs` con `kind="rescan"` (excluido de la
   lectura de «último ciclo» de #231).
4. Rutas sin cambios: solo `stat`, sin abrir el CBZ. El límite «mismo tamaño y fecha» queda declarado
   y testeado.
5. Pruebas: `tests/test_rescan_biblioteca_pg.py` (Postgres y ficheros reales) y
   `tests/test_rescan_biblioteca.py`; el test de #326 se ajusta por decisión explícita del PO
   (`registro_biblioteca.iniciar` sigue siendo solo de la pantalla).

## Dependencias y límites
BL-R3a (#232, hecho) y #326 (hecho) como base; sin dependencias nuevas, sin cola externa (ADR-0011).
No autoriza despliegue: fusión y despliegue se aprueban aparte.

## Estimación propuesta
8 pts, talla M, confianza Alta (no calibrada). Prioridad P1, MoSCoW Should.
```
