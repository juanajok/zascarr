# OPS4 — validación completa del worktree (2026-11-20)

Código validado: `b9f5a612`. Directorio de trabajo explícito:
`.worktrees/ops4-443`. No se atribuyen a este SHA los recuentos históricos de
8.045 pruebas superadas comunicados anteriormente.

## Ejecución completa

```sh
PYTHONPATH=.:src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python \
  -m pytest -q --basetemp=/var/tmp/zascarr-ops4-suite-r66
```

Se comprobaron los dispositivos: `/var/tmp` y `/` están en el mismo
filesystem; `/tmp` no. El primer intento dentro del sandbox no pudo crear el
directorio (`EROFS`): **8.655 errores de preparación y 2.427 omitidas**. No
acredita ejecución de los casos ni una regresión del código. Se repitió la
misma orden mediante la ampliación de permiso aprobada para escribir allí.

Resultado del segundo intento: **2 failed, 8651 passed, 2429 skipped,
7 warnings**, código de salida 1, 502,99 segundos. **La suite completa no está
verde.** Los avisos son de ZIP duplicado en un test y de AsyncMock no esperado
en pruebas del importador; no se han corregido en este incremento.

La ejecución pudo acceder al Docker local. La prueba de restauración usa su
propio proyecto Compose temporal y llama a `down -v --remove-orphans` en su
`finally`; esa rutina no comprueba el código de limpieza y aquí no se ha
verificado por separado el inventario final de Docker. No usa datos de
producción ni la Pi. El fallo de su opt-in descrito abajo debe corregirse antes
de repetir una suite que no solicite expresamente integración Docker.

## Fallos inspeccionados

### Ruta temporal confundida con una BD

[TestRestoreScript.test_restaura_y_comprueba_recuentos](../../tests/test_restore_script.py#L250-L271)
busca ausencia de la subcadena `zascarr` en el registro completo del Docker
falso, salvo el prefijo temporal `zascarr_restore_`. La ruta elegida para
`--basetemp` contiene `zascarr-ops4-suite-r66`, por lo que dispara la aserción
sin demostrar uso de la BD de producción.

La corrección debe distinguir rutas de archivos de argumentos de BD sin
suprimir la guardia que rechaza nombres de producción. Conviene conservar una
regresión con `zascarr` en el nombre de la carpeta. No se ha cambiado el script
de restauración ni se declara resuelto este fallo.

### PostgreSQL aún no disponible y opt-in sobrescrito

[test_la_seguridad_vigente_hostil_vuelve_byte_a_byte](../../tests/test_restaurar_produccion_pg.py#L274-L293)
falló al crear su esquema: el socket PostgreSQL no estaba disponible.
[esperar_postgres](../../tests/test_restaurar_produccion_pg.py#L115-L127)
usa `pg_isready` sobre el socket Unix, que puede dar listo durante el servidor
temporal de inicialización de la imagen oficial, antes del arranque final.
La causa es consistente con esa ventana; no se ha capturado un trazado completo
del contenedor que descarte toda otra causa. La espera debería acreditar el
servidor final (p. ej., TCP local dentro del contenedor y consulta real).

Además, el mismo módulo asigna `pytestmark` varias veces:
[marcas de selección](../../tests/test_restaurar_produccion_pg.py#L33-L46).
La última asignación sustituye la condición `TEST_DATABASE_URL`/`ZASCARR_PG_IT`
y la de plataforma por disponibilidad de Docker. Por ello el test puede
arrancar Compose aun sin opt-in. Se necesita combinar condiciones y evitar
incluso sondear Docker cuando no se solicite esa integración. No se ha cambiado
todavía el arnés.

## Evidencia complementaria

- **666 pruebas seleccionadas de OPS4/paridad** superadas en la pasada anterior
  sobre este mismo código; no se cambió código entre ambas ejecuciones.
- Ruff pasó sobre todos los módulos `deploy/ops`, tests OPS4, fixtures de VM y
  los cuatro servicios nuevos aislados de actualización.
- La [auditoría de concordancia de seguridad](ops4-concordancia-seguridad.md)
  deja M3 abierto: publicación antes del commit, rollback y diferencias entre
  SQL y proceso activo no quedan resueltas por leer correctamente un hash.
- No se ha fusionado, habilitado ni desplegado OPS4. La revisión final SecOps
  sigue pendiente y la suite completa debe repetirse tras corregir el arnés.
