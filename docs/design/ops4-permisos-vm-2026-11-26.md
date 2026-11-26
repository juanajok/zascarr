# OPS4 — Evidencia de la VM de permisos (2026-11-26, #443)

**Candidato:** `de4f8c3df303c923d8607dfab9f309604196761f` (rama
`fix-ops4-estado-permisos`, base `c4a34203`).
**Máquina:** Debian 13 *genericcloud* sobre un overlay nuevo, sin NIC y con el
material de prueba en un CD de solo lectura. Imagen base intacta.

## Qué se ejecutó

- Instalación manual del auxiliar y sus módulos en `/usr/local/lib/zascarr`, y
  de `zascarr-actualizar.socket` y `zascarr-actualizar@.service` con
  `@ZASCARR_DATA_DIR@=/var/lib/ops4test` y `@GRUPO@=pruebaops4` (GID 989).
- Clave **sintética** de 32 bytes (todo ceros) en
  `/var/lib/ops4test/ops/actualizar.key`, `root:pruebaops4` y `0440`.
- `ops4/consumidos` en `0700`; directorio `ops` en `0750 root:pruebaops4`.
- `zascarr-actualizar.socket` real, `Accept=yes`, `0660 root:pruebaops4`.
- Unidad de destino **fixture** `zascarr-actualizar.service` que solo escribe
  una línea en `/var/lib/ops4test/inicios`; **no** se instaló ni ejecutó
  `update.sh`, Docker, PostgreSQL ni la unidad real de actualización.
- Petición v4 construida con las funciones reales de autorización y protocolo;
  enviada por el socket Unix; repetida sin cambios para probar el consumo.

## Resultados

| Comprobación | Resultado |
|---|---|
| Petición válida | `aceptada` |
| Replay de la misma petición | `repetida`; una sola ejecución del fixture |
| Estado | `root:pruebaops4`, modo `0640` |
| Lectura como identidad de app (`pruebaapp4`, grupo `pruebaops4`) | correcta |
| Auxiliar | UID 0, GID 989, `CapEff=0000000000000000` |
| Grupo divergente (drop-in `Group=otroops4`) | `no_disponible`, sin segunda ejecución |
| Publicación inicial | `escribir_estado` devuelve `ok` |

La guarda de GID efectivo se ejecuta antes de procesar la petición; por eso el
caso divergente responde `no_disponible` con `id: null` y no crea consumo ni
estado.

## Límites

- La unidad de destino es un fixture: no se probó el recorrido real de
  `update.sh`, las migraciones, el arranque de contenedores ni `ExecStopPost`.
- No se probó la Raspberry Pi, la UI, la rotación de clave ni un corte de
  energía.
- No se usó ninguna credencial ni dato real. El overlay y la clave sintética no
  se conservan como material reutilizable.
- Esta evidencia no autoriza habilitar ni desplegar OPS4.
