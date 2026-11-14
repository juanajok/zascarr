# BL-E5 (#164) — Descargar logs recientes desde el dashboard

## Problema

El coleccionista que reporta un fallo no puede abrir una terminal. La app escribe con
structlog a **stdout**; Docker lo rota en el host (`json-file`, 10 MB × 3) y desde el
contenedor no hay acceso a esos ficheros. Se necesita un botón en Inicio que entregue un
fichero con lo ocurrido, sin montar rutas del host ni añadir dependencias.

## Decisión

**Búfer en memoria de eventos structlog** (`deque(maxlen=500)`), capturado por un procesador
insertado antes del renderizador final. La captura **no cambia** el formato de stdout.
`GET /ui/logs` devuelve el texto como adjunto `text/plain`, con `no-store` y `nosniff`.

- No se leen ficheros de Docker ni se monta el socket.
- No hay migración, ni tabla, ni dependencia nueva.
- El búfer vive en el proceso (`uvicorn --workers 1`), igual que el orquestador.
- Reiniciar la app vacía el búfer; el límite es 500 eventos / 256 KiB.

## Privacidad

El fichero puede contener rutas y nombres de la biblioteca (necesarios para diagnosticar); se
avisa **antes** de descargarlo. Se redactan:

- campos con nombre de contraseña, token, secreto, `api_key`, `authorization`, `cookie` o
  `bearer`;
- `usuario:clave@host` en URLs;
- parámetros de URL con pinta de secreto;
- `token=...`, `authorization: ...` y `Bearer ...` dentro de mensajes y trazas.

Los logs de acceso de uvicorn ya pasan por `SinQueryEnAcceso` (#361); este búfer añade los
eventos de aplicación, no una copia de cada petición.

## Criterios de aceptación

- En Inicio hay un enlace **«Descargar logs»** visible.
- `GET /ui/logs` responde 200, `text/plain`, `Content-Disposition: attachment`,
  `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`.
- Sin eventos, el fichero lo explica («No hay registros recientes…»).
- Un token/contraseña de prueba no aparece en el texto; el nombre del evento y una ruta
  normal sí.
- El búfer no altera la salida normal ni el formato de structlog.
- No hay dependencias nuevas ni cambios de compose.

## PASS / FAIL / NOT RUN

- **PASS (pruebas):** captura, redacción, descarga, fichero vacío, botón en Inicio.
- **PASS (compatibilidad):** las suites que usan `structlog.testing.capture_logs` siguen pasando.
- **NOT RUN:** descarga real desde un navegador/Pi (lo valida el despliegue), lectura del
  fichero por una persona externa y revisión de privacidad con el PO. El aviso de rutas está
  en la UI, pero la decisión de compartir es del coleccionista.
