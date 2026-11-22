# Fixture A6 — datos sintéticos reproducibles

Semilla mínima para reproducir A6 (UATP-06/07) en un entorno aislado. **Nunca** se
ejecuta contra una instalación real ni contra la Pi.

- [`crear_cbz.py`](crear_cbz.py) — genera `ARCHIVO-A.cbz` (6 páginas) y `ARCHIVO-B.cbz`
  (3 páginas) deterministas con la stdlib (`zipfile` + PNG mínimo hecho a mano).
- [`sembrar.py`](sembrar.py) — copia los CBZ a la raíz de biblioteca del host y siembra
  el catálogo con UUID fijos (2 series, 2 números, 2 archivos). No siembra el progreso:
  lo escribe el lector real con `POST /ui/leer/<file_id>/progreso --data pagina=3`.

Uso (con el entorno E-A6 ya arrancado y migrado; variables del runbook):

```bash
export COMPOSE_FILE=<compose aislado> ENV_FILE=<.env del entorno> DB_NAME=zascarr DB_USER=comics_admin
export HOST_LIBRARY_DIR=<raíz de biblioteca del host> LIBRARY_PATH=/biblioteca
python3 docs/uat/A6/fixture/sembrar.py
```

Después, para dejar la página guardada como la escribió el lector:

```bash
curl -s -o /dev/null -c "$COOKIE" -X POST "$APP_URL/login" --data-urlencode "password=<secreto>"
curl -s -o /dev/null -w '%{http_code}\n' -b "$COOKIE" -H "Origin: $APP_URL" \
  -X POST "$APP_URL/ui/leer/a6000000-0000-4000-8000-000000000021/progreso" --data-urlencode "pagina=3"
```

El entorno necesita `auth_mode=password` (el flujo `restaurar_datos.sh --produccion` lo exige);
la contraseña y su hash no se versionan.
