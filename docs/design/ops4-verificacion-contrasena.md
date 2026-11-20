# OPS4 — límites del verificador de contraseña del host

El [verificador aislado](../../deploy/ops/prueba_viva_ops4.py) interpreta hashes
`pbkdf2_sha256$iteraciones$sal_hex$digest_hex` obtenidos por el lector del host.
No está conectado al auxiliar ni cambia el login o la reautenticación de la
aplicación.

## Límites y coste

- Contraseña: 1–512 bytes UTF-8. Se rechaza longitud en caracteres superior a
  512 antes de codificar, y se comprueba después el límite en bytes.
- Hash almacenado: hasta 256 caracteres antes de dividir/decodificar.
- Iteraciones: **10.000–2.000.000**, ambos extremos incluidos. Este techo ya
  existía; ahora queda nombrado y probado explícitamente. No es la política
  de generación de hashes nuevos ni una recomendación de usar 10.000.
- Sal: 1–64 bytes decodificados. El límite superior acota entradas corruptas;
  no exige 16 para conservar compatibilidad con sales históricas más cortas.
- Digest esperado: exactamente 32 bytes (salida SHA-256 por defecto).

Un algoritmo, número, sal, digest o tamaño imposible se rechaza **antes** de
calcular PBKDF2. La comparación final sigue usando `hmac.compare_digest`.
Los mensajes no incluyen contraseña, hash ni errores de la BD.

## Compatibilidad comprobada, no aprobación de integración

La [app](../../src/zascarr/services/auth.py) genera actualmente **600.000**
iteraciones, sal aleatoria de **16 bytes** y digest de **32 bytes**. La
[regresión](../../tests/test_ops4_prueba_viva.py) llama a su `hash_password`
real y comprueba que el verificador OPS4 acepta la contraseña correcta y
rechaza otra. Una actualización de esa política debe repetir esta prueba y
revisar el techo del host **antes de habilitar OPS4**: no asumir que cualquier
hash aceptado por la app lo acepta el host.

Las pruebas de fronteras de 10.000/600.000/2.000.000 usan un cálculo inyectado
para no gastar el coste máximo en cada test. La prueba de compatibilidad con
la app y la de sal máxima sí calculan PBKDF2 real. Los casos malformados
prohíben explícitamente invocarlo.

## Pendiente de resolver

- Esto acota el coste **por intento**, no la concurrencia global ni los
  intentos entre procesos. El límite en memoria existente no es persistente
  ni compartido por instancias del auxiliar.
- El host lee `runtime_settings`; la app aplica overrides sobre los valores
  de configuración base y mantiene una instancia de Settings. La
  concordancia entre sus fuentes efectivas, los cambios/rollback de ajustes
  y la identidad de la instalación **sigue sin acreditarse**. Una coincidencia
  con un hash leído no demuestra por sí sola que sea la contraseña efectiva
  de esa app en ese instante. La [auditoría de concordancia](ops4-concordancia-seguridad.md)
  detalla publicación anterior al commit, rollback, recuperación CLI e
  identidad/readiness pendientes; M3 sigue abierto.
- Los límites del host pueden denegar un hash fuera de rango que otra ruta
  histórica acepte. Fallar cerrado es preferible a intentar un coste sin
  límite; la compatibilidad de instalaciones reales necesita revisión.
- Siguen pendientes reserva durable de operación, cerrojo, unidad,
  reconciliación de cortes y revisión SecOps del SHA final.

No se ha cambiado la autenticación en servicio ni se ha ejecutado una
actualización. OPS4 permanece deshabilitado.
