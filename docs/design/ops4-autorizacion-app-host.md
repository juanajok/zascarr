# OPS4 — autorización corta de la app al host

**Decisión del usuario (2026-11-20):** la app reautentica la contraseña actual
y emite una autorización corta de un solo uso; el host no vuelve a leer el hash
de la BD para esta comprobación. Sustituye el planteamiento de verificación
independiente del host como autoridad principal. La función sigue deshabilitada
y este contrato no está conectado a la web, el auxiliar ni systemd.

## Componentes

- [Emisor y composición en la app](../../src/zascarr/services/autorizacion_actualizacion.py):
  `crear_autorizacion` construye `cuerpo_json.firma_hex` con HMAC-SHA256 sobre
  `zascarr-ops4-autorizacion-v1`; `preparar_autorizacion` impone la puerta
  `habilitada`, confirmación, forma de contraseña, `auth_mode`, una única llamada
  a `comprobar_contrasena_actual` inyectable y emisión solo con `Reauth.OK`.
  No incluye contraseña, hash, usuario ni sesión. La clave debe ser de 32 bytes
  y **dedicada**; se recibe como argumento, no se lee ni se reutiliza `ops.key`.
- [Verificador en el host](../../deploy/ops/verificador_autorizacion_ops4.py):
  comprueba firma, esquema cerrado, acción `actualizar`, ID hexadecimal,
  ventana de 1–300 s, tolerancia de reloj de 120 s y un `id_esperado`
  **obligatorio**; después exige un callback de consumo único. Devuelve
  aceptada, inválida, caducada, repetida o no disponible. No lee hashes ni BD.
- [Consumo durable](../../deploy/ops/registro_repeticiones_ops4.py):
  `reclamar_autorizacion` usa `autorizacion-<id>`, separado de
  `solicitud-<id>` de v3, con `O_EXCL`, dos `fsync` y sin borrar marcas ante
  fallo. `crear_reclamador_durable(fd)` lo conecta al verificador.
  `abrir_directorio_autorizaciones` exige un `uid` explícito y modo `0700`, sin
  seguir enlaces, antes de usar el descriptor.
- [Lector de clave dedicada](../../src/zascarr/services/clave_autorizacion.py):
  exige `uid` y modo `0440`/`0400` exactos, fichero regular, 64 hex o 64+LF,
  sin seguir enlaces ni bloquear en FIFO. No la crea ni la instala.

El host no consulta `auth_mode`, hashes, DB ni readiness: confía en que la app
solo emite tras reautenticar. La composición no incluye todavía sesión/origen,
envío único ni transporte; por eso la integración completa sigue pendiente.

## Garantías y límites

Probado en aislamiento:

- Token válido aceptado una vez; segunda verificación repetida.
- Ventana, caducidad y tolerancia de reloj en los límites.
- Firma/clave/tipo/formas malformadas, campos extra, booleanos donde se exige
  entero, claves JSON duplicadas y token sobredimensionado: rechazo.
- Callback que lanza o no devuelve exactamente `True`: no se acepta.
- 32 hilos con callback serializado: un solo consumo.
- El token no contiene literalmente `prueba`, `password` ni `pbkdf2`.
- Emisor rechaza clave/ID/instante/vigencia inválidos.

**Probado en la composición:** orden puerta→confirmación→forma→`auth_mode`→
reautenticación→emisión; todos los resultados no `OK`, excepciones y valores
inesperados no emiten; ID CSPRNG generado solo tras OK; clave inválida no
emite; token oculto en `repr`; E2E composición→verificador→registro durable,
replay tras reapertura y procesos concurrentes.

**No probado todavía:** la reautenticación real contra el servicio completo, la
UI, el auxiliar, el protocolo de red, la provisión de la clave dedicada, el
propietario/modo real del directorio durable, el envío único ni la ejecución.
La prueba de hilos no sustituye la exclusión entre procesos: el callback debe
usar el [registro durable](ops4-registro-repeticiones.md) con un directorio
propio y acreditado. El ID del testigo se liga a la petición con `id_esperado`;
no debe reutilizarse para otra acción.

La autorización caduca en minutos y es de un uso, pero no demuestra por sí sola
que el host sea el correcto, que la app esté sana ni que el binario desplegado
sea el autorizado. Si la app o su clave están comprometidas, el modelo de
confianza cambia; el testigo no protege frente a ese escenario. El host debe
seguir validando instalación, rutas, cerrojo, estado y unidad como estaba
previsto.

**Clave: no reutilizar `ops.key`.** Esa clave de OPS1/OPS2 es legible por el
grupo del auxiliar y su HMAC acredita pertenencia al grupo, no que la app haya
reautenticado. Este contrato exige una clave dedicada de 32 bytes, con permisos
mínimos para la app y el host, rotación definida y separada de copia/restauración.
El prefijo de dominio evita reutilizar una firma de otro protocolo, pero no
convierte una clave compartida por grupo en prueba de reautenticación. Esa
provisión **no está implementada** y bloquea la integración.

## Pendiente para integrar

1. Provisionar la clave dedicada y el directorio durable (el lector y el
   comprobador existen, pero no hay instalador/ruta/rotación ni despliegue).
2. Definir el transporte (probablemente nueva versión) y eliminar la
   contraseña del mensaje al host en esa ruta; implementar envío único.
3. Acreditar propietario/modo/ruta del directorio durable y su retención.
4. Integrar sesión/origen y la puerta explícita de habilitación; no conectar la
   UI ni el auxiliar antes.
5. Revisión SecOps del SHA final antes de fusionar, conforme a la regla del
   proyecto para cambios que afectan a la contraseña actual.
6. No habilitar la UI ni instalar unidad/auxiliar hasta completar lo anterior.

**Estado de pruebas:** 49 casos de contrato, 59 de composición y 47 de registro
durable (incluidos aislamiento y UI) forman parte de las **791 pruebas OPS4/paridad** verdes y de la suite completa **8880 passed / 2431 skipped**; el detalle y las limitaciones están en los informes de
[SecOps](secops-ops4-autorizacion-2026-11-20.md),
[UI](ui-ops4-autorizacion-2026-11-20.md) y
[QA](qa-ops4-autorizacion-2026-11-20.md). El contrato permanece sin importar
desde web, API, main ni el auxiliar.


## Riesgo residual (ADR 0026)

El testigo y la firma comparten `actualizar.key`, y la app debe leerla para
emitir el testigo. Cualquier código del contenedor o proceso del grupo con
acceso a la clave puede fabricar una petición válida sin contraseña. La acción
fija, el socket restringido, el consumo único y el cerrojo acotan el daño; no
acreditan identidad humana en el host. La decisión está en
[ADR 0026](../../adr/0026-actualizacion-manual-confianza-main.md).
