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

## fonts/

Tipografías de la UI, servidas en local por la misma razón que htmx: la app corre
en la red de casa, a menudo sin internet, y no manda la IP del coleccionista a
un tercero. Solo el subconjunto latino (U+0000-00FF: tildes, Ñ, ¡, ¿, º, ª).
Se declaran en `web.css` (sección 0, «Fuentes») y van en el paquete por
`[tool.setuptools.package-data]` de `pyproject.toml`.

| Fichero | Familia | Versión | Origen | Licencia |
|---|---|---|---|---|
| `anton-latin-400-normal.woff2` | Anton (titulares) | Fontsource `@fontsource/anton` 5.3.0 | https://www.npmjs.com/package/@fontsource/anton · `files/anton-latin-400-normal.woff2` | SIL OFL 1.1 (`OFL-Anton.txt`) |
| `archivo-latin-wght-normal.woff2` | Archivo variable, peso 100–900 (texto) | Fontsource `@fontsource-variable/archivo` 5.3.0 | https://www.npmjs.com/package/@fontsource-variable/archivo · `files/archivo-latin-wght-normal.woff2` | SIL OFL 1.1 (`OFL-Archivo.txt`) |
| `archivo-latin-wght-italic.woff2` | Archivo variable, cursiva | ídem | ídem · `files/archivo-latin-wght-italic.woff2` | SIL OFL 1.1 (`OFL-Archivo.txt`) |

Actualizar: `npm pack @fontsource/anton @fontsource-variable/archivo` en una carpeta
temporal, copiar los mismos ficheros y su `LICENSE`, y anotar aquí la versión.
Nada de fuentes comerciales (Blambot, Comicraft…): el repositorio es GPL-3.0 y
cada instalación las redistribuiría.
