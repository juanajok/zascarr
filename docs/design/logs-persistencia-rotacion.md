# Logs persistidos: rotación, consulta y descarga

> **Estado:** implementado en `main`; no cambia datos de usuario ni la política de saneo #369.
> Complementa `benchmark-logs-zascarr.md`.

## Por qué

Hasta ahora los logs solo estaban en stdout (Docker, `10 MB × 3`) y en un búfer de
memoria de 500 eventos. Al reiniciar, el búfer se perdía y desde el contenedor no se podían
leer los ficheros de Docker. El coleccionista no podía consultar una incidencia de ayer ni
filtrar por hora/evento.

## Política de rotación

- Directorio: **`LOG_DIR=/config/logs`**, montado desde
  `${ZASCARR_DATA_DIR}/logs` en Compose. Si no existe o no es escribible, la app sigue
  arrancando: stdout y el búfer actual son el respaldo.
- Un fichero **por día UTC**: `zascarr-AAAA-MM-DD.jsonl`.
- Al superar **`LOG_MAX_BYTES` (5 MiB)**, el fichero del día se desplaza a `.1`, `.2`…
  y se conservan **`LOG_BACKUPS` (3)**; el siguiente fichero empieza de cero.
- Se eliminan los días anteriores a **`LOG_RETENTION_DAYS` (30)**.
- Permisos: directorio `0700`, fichero `0600`.
- Una línea JSON por evento, escrito ya saneado por #369 (`sanear_evento` va antes del
  sumidero).
- El sumidero es **best-effort**: un fallo de disco no tumba la petición; el evento sigue en
  stdout.

Variables nuevas (opcionales): `LOG_DIR`, `LOG_MAX_BYTES`, `LOG_BACKUPS`,
`LOG_RETENTION_DAYS`. Se pasan en `.env.example` y Compose.

## Consulta

- `GET /ui/logs/visor`: selector de **fecha** (días con fichero), **hora** (`HH` o `HH:MM`) y
  **evento**; muestra hasta 300 eventos y enlaza a la descarga con los mismos filtros.
- `GET /ui/logs?fecha=&hora=&evento=&limite=`: descarga **JSONL** filtrado; `limite` máximo
  1.000. Sin filtros y sin ficheros, conserva el contrato BL-E5 del búfer en memoria.
- La descarga no expone rutas ni nombres: los eventos llegan saneados por la cadena #369.

## Límites

- **Antes de esta versión** los logs siguen en Docker (stdout); el visor no puede
  recuperarlos sin acceso al socket/host. A partir del despliegue, los nuevos eventos sí se
  consultan y descargan.
- La app no crea el volumen del host: el despliegue debe crear
  `${ZASCARR_DATA_DIR}/logs` con el UID/GID del servicio (o dejar que Docker lo cree y
  corregir permisos una vez).
- No hay índice de eventos: el visor lee los ficheros del día seleccionado, acotado a 1.000.
- No se midió el coste en la Pi; el volumen es pequeño y las escrituras son O_APPEND.
