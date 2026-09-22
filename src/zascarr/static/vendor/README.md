# Vendor

Librerías JS de terceros servidas por el propio FastAPI, no desde un CDN
(ver `docs/adr/0001-ui-stack.md`). Sin gestor de paquetes de por medio:
actualizar aquí significa volver a descargar el fichero a mano.

## htmx.min.js

- Versión: 4.0.0
- Origen: https://github.com/bigskysoftware/htmx/releases/tag/v4.0.0
- Descargado de: `https://raw.githubusercontent.com/bigskysoftware/htmx/v4.0.0/dist/htmx.min.js`
- Licencia: BSD 2-Clause
- Verificado cargándolo en un navegador real contra un servidor HTTP
  local: `htmx.version === "4.0.0"`, sin errores de consola.
