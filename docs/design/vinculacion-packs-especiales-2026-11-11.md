# Vinculación: packs, especiales y D2 revisada (2026-11-11)

## Decisiones

1. **D2 revisada**: «Marcar todos los que se pueden vincular» ya no incluye
   archivos que contradicen la carpeta/serie elegida. Siguen visibles y se
   pueden marcar a mano. Si la persona escribe el número, su decisión manda.
2. **Prefijo de orden de lectura**: si un archivo sin número empieza por
   `047.- `, la revisión avisa de que ese `047` es orden de lectura, no el
   número del cómic.
3. **Packs y especiales**: no se tratan como grapas.
   - Un pack (rango o `#N - Anual`) no es una publicación única.
   - Un especial (`Especial`) se deja para Pendientes/el flujo de
     «Vincular como especial sin número».
   - Ambos quedan bloqueados en el masivo y no generan números falsos.

## Implementación

- `ParsedComicName.is_pack`.
- `VistaPreviaDeVinculacion` bloquea `es_pack` y `es_especial` y añade el
  aviso del prefijo de orden.
- `elegir_para_marcar_todos` excluye conflictos de carpeta salvo número
  escrito por la persona.
- Test de aceptación D2 actualizado; nuevos tests de pack, especial y aviso.

## Verificación

- 128 tests de asistente/vinculación en verde.
- Test del parser para `is_pack`/`is_special`.
- Sin cambios de datos ni migraciones.
