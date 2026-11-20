# OPS4 — autorización corta de la app al host

**Decisión del usuario (2026-11-20):** la app reautentica la contraseña actual
y emite una autorización corta de un solo uso; el host no vuelve a leer el hash
de la BD para esta comprobación. Sustituye el planteamiento de verificación
independiente del host como autoridad principal. La función sigue deshabilitada
y este contrato no está conectado a la web, el auxiliar ni systemd.

## Componentes

- [Emisor en la app](../../src/zascarr/services/autorizacion_actualizacion.py):
  construye `cuerpo_json.firma_hex` con HMAC-SHA256 sobre el prefijo de dominio
  `zascarr-ops4-autorizacion-v1`. No incluye contraseña, hash, usuario ni sesión.
  La clave debe ser de 32 bytes y **dedicada** a esta autorización.
- [Verificador en el host](../../deploy/ops/verificador_autorizacion_ops4.py):
  comprueba firma, esquema cerrado, acción `actualizar`, ID hexadecimal,
  ventana de 1–300 s y tolerancia de reloj de 120 s; acepta opcionalmente un
  `id_esperado` para ligar el testigo a la petición, y después exige un callback
  de consumo único. Devuelve aceptada, inválida, caducada, repetida o no
  disponible. No ejecuta nada.

El llamador de la app debe ejecutar **antes**
`services.reautenticacion.comprobar_contrasena_actual` y no emitir si el
resultado no es `Reauth.OK`. El emisor puro no puede comprobarlo por sí mismo;
la futura integración debe imponer ese orden y cubrirlo con una prueba de
composición. El host no consulta `auth_mode`, hashes, DB ni readiness: confía
en que la app solo emite tras reautenticar.

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

**No probado todavía:** la composición real con reautenticación, la UI, el
auxiliar, el protocolo de red, la clave compartida, la persistencia durable del
consumo ni la ejecución. La prueba de hilos no sustituye exclusión entre
procesos: el callback debe usar el [registro durable](ops4-registro-repeticiones.md)
o un mecanismo equivalente. El ID del testigo debe ligarse a la petición y a la
operación, no reutilizarse como identificador de otra acción.

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

1. Adquirir la clave de 32 bytes en la app por el canal ya previsto, sin
   exponerla a la web ni registrarla.
2. Llamar a reautenticación y emitir solo con `OK`; probar composición y fallos.
3. Definir el transporte (probablemente nueva versión de protocolo) y eliminar
   la contraseña del mensaje al host en esa ruta.
4. Consumo durable y exclusión entre procesos; ligar testigo, petición y
   operación.
5. Revisión SecOps del SHA final antes de fusionar, conforme a la regla del
   proyecto para cambios que afectan a la contraseña actual.
6. No habilitar la UI ni instalar unidad/auxiliar hasta completar lo anterior.

Los 38 tests de [test_ops4_autorizacion.py](../../tests/test_ops4_autorizacion.py)
y la barrera de [aislamiento](../../tests/test_ops4_aislamiento.py) pasan; el
contrato permanece sin importar desde web, API, main ni el auxiliar.
