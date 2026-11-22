# OPS4 — protocolo v4 aislado (autorización sin contraseña)

Sustituye la contraseña de v3 por el testigo corto app→host. En la rama hay
transporte y servicio app, y la UI/auxiliar están conectados **solo detrás de
la bandera apagada**; no se ha habilitado ni desplegado. v3 sigue siendo el
protocolo histórico aislado.

## Formato

Una línea JSON UTF-8 + LF, máximo 4096 bytes, con exactamente:

```text
v=4, id (32 hex), accion="actualizar", creada (entero 63 bits),
autorizacion (base64url sin relleno del testigo), firma (64 hex)
```

Se rechazan CRLF, segunda línea, claves duplicadas, campos extra, `prueba`,
booleanos donde se exige entero, base64 no canónico y tamaños fuera de límite.
La firma HMAC-SHA256 cubre los cinco campos en orden fijo y dominio
`zascarr-ops/actualizar/v4\x00`. El testigo lleva su propio dominio y `id`; el
host exige que coincida con el `id` de la petición.

## Admisión

[`admitir_v4`](../../deploy/ops/admision_v4_actualizar_ops4.py) ordena:
esquema → firma de petición → frescura (120 s) → decodificación del testigo →
verificación del testigo → consumo único. El callback de consumo debe ser
durable y separado de `solicitud-<id>` de v3; se prueba con
`abrir_directorio_autorizaciones` y `crear_reclamador_durable`. Un testigo
inválido, caducado o con otro ID **no llama** al callback. Una aceptación no
autoriza efectos: faltan instalación, cerrojo, estado, unidad y SHA.

## Evidencia

- [Protocolo host](../../deploy/ops/protocolo_actualizar_v4_ops4.py),
  [constructor app](../../src/zascarr/services/ops_actualizacion_v4.py) y
  [tests](../../tests/test_ops4_protocolo_v4.py): **21 casos**.
- Paridad app/host, petición sin `prueba`/`password`/`pbkdf2`, replay,
  testigo de otro ID, caducidad, firma/clave/reloj inválidos, CRLF, campos
  extra, base64 canónico, límites y E2E con directorio durable real.
- **389 pruebas OPS4/instalador** verdes; falta repetir la suite completa en este
  árbol. No hay socket, ruta web, auxiliar ni unidad de actualización.

## Límites y pendientes

- No hay transporte por socket ni envío único; no se ha probado una respuesta
  perdida, un timeout ni el estado incierto.
- La app aún no compone `preparar_autorizacion` con este constructor ni obtiene
  la clave dedicada por un canal instalado; no se conecta a la web.
- El consumo durable no acredita el directorio en producción (el test usa un
  tmp acreditado), ni retención/cuota, ni supervivencia a pérdida eléctrica.
- La autorización no demuestra que el host sea correcto ni que el binario esté
  autorizado; la posesión de la clave dedicada sigue siendo el límite de
  confianza. La app o la clave comprometidas pueden forjar peticiones.
- Revisión SecOps del SHA final y pruebas de cortes/transporte antes de
  integrar. La actualización permanece deshabilitada.
