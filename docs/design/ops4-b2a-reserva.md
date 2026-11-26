# OPS4 — B2a: primitivas de reserva y admisión (#443)

**Estado:** especificación de la primera mitad de B2; no cambia el
comportamiento del auxiliar ni habilita la función.
**Base:** `f9409155ea34dcadca11b449fb9c49843b1d0a40`.

B2 completo (`docs/design/especificacion-ops4-cierre.md`, §B2) exige el
cerrojo de admisión, la marca de intento, la verificación en dos fases, la
reserva durable antes del `start`, el wrapper con `flock` fd 9 y la
confirmación antes de consumir. Esta entrega añade las **primitivas** con
pruebas; el cableado del auxiliar y del trabajador es B2b.

## Contrato

### Verificación en dos fases

- `verificar_testigo_sin_consumo(token, *, clave, ahora, id_esperado)`:
  misma validación de formato, firma, campos, ligadura por `id`, ventana y
  reloj que `verificar_autorizacion`, pero **no llama** a ningún callback de
  consumo y no crea marcas. Devuelve `CodigoAutorizacion`.
- `verificar_autorizacion(...)`: conserva la firma pública y el
  comportamiento actual; internamente usa la función anterior y solo entonces
  llama a `reclamar_uso`. Un testigo no verificado nunca consume.

### Marca de intento

- `reclamar_intento(id_, *, directorio_fd, sincronizar=os.fsync)`: crea
  `<id>` en el directorio dedicado `ops4/intentos` con `O_EXCL`, `0600`,
  `O_NOFOLLOW`, `O_CLOEXEC`, y confirma con `fsync` del fichero y del
  directorio. Devuelve `True` solo entonces; `False` si ya existe.
- `abrir_directorio_intentos(ruta)`: exige directorio, `uid` 0 y modo `0700`;
  no lo crea ni lo repara.
- La marca no contiene secretos ni estado: su existencia acredita que la
  petición llegó a reserva. No sustituye al consumo de la autorización.

### Cerrojo de admisión

- `tomar_admision(ruta)` abre/crea el fichero `0600` sin seguir enlaces y
  toma `flock` exclusivo **no bloqueante**; devuelve el descriptor o `None`
  si está ocupado. `liberar_admision(fd)` lo cierra y libera.
- Solo serializa auxiliares; no es el cerrojo de operaciones y no se mantiene
  durante la actualización.

## Criterios y pruebas

- **AC-B2a-01.** `verificar_testigo_sin_consumo` acepta un testigo válido sin
  crear marcas ni invocar callbacks; rechaza firma, `id`, ventana y formato con
  los códigos actuales. Prueba: `test_ops4_autorizacion_b2.py`.
- **AC-B2a-02.** `verificar_autorizacion` sigue consumiendo una sola vez y no
  consume si la verificación falla. Prueba: mismo módulo.
- **AC-B2a-03.** `reclamar_intento` es exclusiva, `0600`, con `fsync`, y falla
  cerrada si el directorio no es seguro o la sincronización falla. Prueba:
  `test_ops4_intentos_b2.py`.
- **AC-B2a-04.** `tomar_admision` es exclusiva entre dos procesos reales,
  libera al cerrar y crea el fichero `0600`. Prueba:
  `test_ops4_admision_b2.py` con `fork`/tubería.
- **AC-B2a-05.** El instalador crea `ops4/intentos` en `0700` e instala el
  módulo de admisión; no activa nada. Prueba: `test_instalar_ops4.py`.

## Límites

No se conecta al auxiliar, no cambia el orden P3–P14, no añade el wrapper ni
toca `update.sh`. La ventana entre aceptación y `start` sigue abierta hasta
B2b. No se habilita ni despliega nada.
