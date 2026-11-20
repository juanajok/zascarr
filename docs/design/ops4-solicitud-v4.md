# OPS4 — servicio app v4 aislado

Encadena en un único servicio la reautenticación, la autorización corta, la
petición v4 y el transporte. **No está conectado** a la web, al auxiliar, a
`main.py` ni a systemd; la puerta `habilitada` es `False` por defecto.

## Flujo

1. Comprobar `habilitada`, confirmación y forma de la contraseña.
2. Comprobar `auth_mode` y reautenticar con el servicio compartido.
3. Solo con `Reauth.OK`, generar ID CSPRNG y emitir el testigo con la clave
   recibida.
4. Construir la petición v4 (sin contraseña) y enviarla por el transporte
   inyectado.
5. Devolver un código cerrado; `INCIERTA` no se reintenta ni se presenta como
   éxito.

La clave y el transporte se inyectan: el servicio no lee ficheros, no abre
sockets por sí solo ni persiste. No registra contraseña, testigo ni petición.
Los resultados incluyen el ID solo cuando se llegó a emitir la petición.

## Pruebas

- [Servicio](../../src/zascarr/services/solicitud_actualizacion_v4.py) y
  [tests](../../tests/test_ops4_solicitud_v4.py): **13 casos**.
- No habilitada, confirmación, `auth_mode=none`, reauth incorrecta/bloqueada/
  excepción, éxito con petición v4 verificable, clave inválida, fallo de
  construcción, preparación inesperada, `ahora` inválido, transporte incierto
  sin reintento, `conversar` inyectado y ausencia de secretos en `repr`.
- **888 pruebas OPS4/paridad** verdes; suite completa pendiente de repetir.

## Límites

- No hay ruta web ni botón activo; no hay sesión/origen, CSRF/UI, envío único
  persistente ni reconciliación de `INCIERTA`.
- La clave no se provisiona ni se lee desde un canal instalado; el servicio
  recibe bytes. La identidad de instalación, el cerrojo, la unidad y la
  ejecución siguen fuera.
- El transporte inyectado puede ser real, pero el test usa dobles; no se ha
  probado el auxiliar productivo.
- Sin revisión SecOps del SHA final no se fusiona ni habilita.

La actualización sigue deshabilitada y sin despliegue.
