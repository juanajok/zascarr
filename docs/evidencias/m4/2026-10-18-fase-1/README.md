# M4 — fase 1 del ensayo en Debian (2026-10-18): evidencia histórica

> **Estado de este paquete: INCOMPLETO.** Esta carpeta existe para fijar la ubicación, la procedencia y las reglas; **los ficheros
> del informe y de las evidencias todavía no se han incorporado**. Hasta que el inventario de abajo esté completo y con sus hashes,
> nadie debe citar este directorio como prueba. Los resultados que el backlog resume en «Estado de M4» proceden del informe de la
> fase 1 aportado por quien lo ejecutó, **no** de ficheros verificados aquí.

- **Candidato ensayado:** `0a591d6f91a6b54f8cecb1e675afc59dc0290873` (merge de #225).
- **Plan de referencia:** `docs/design/m4-plan-de-aceptacion-debian.md` (PR #226, merge `f2c45c4`). El plan decía «no se ha ejecutado
  nada» y era cierto en su fecha; **no se reescribe**.
- **Entorno:** máquina virtual Debian 12 aislada. **No acredita** Raspberry Pi/ARM, rendimiento real ni esfuerzo humano (#122).
- **Alcance ejecutado:** M4-01 (instalación limpia) y M4-02 (salud y esquema), más una inspección adicional del `.env` y la
  condición de fuentes. M4-03…M4-20: **sin ejecutar y sin autorización**.

## Resultados que se registran (según el informe; pendientes de verificar contra los ficheros)

| Caso / condición | Resultado | Nota |
|---|---|---|
| M4-01 instalación limpia, sin terminal | **FAIL** | RC=1: «DB_PASSWORD tiene el valor por defecto. Edita el .env» |
| M4-02 salud y esquema | **Parcial** | el arranque completó tras editar la contraseña a mano (intervención manual) |
| Condición: fuentes desactivadas | **FAIL** | las cuatro figuraban como habilitadas; no se acreditaron consultas efectivas (red cerrada) |
| Inspección del `.env` | **Hallazgo** | modo 644, abierto desde cuentas no administrativas |

## Inventario de ficheros (a completar; sin hashes verificados aquí no hay paquete)

**Lo que declara quien recuperó los originales (2026-10-18)** y que yo **no he podido verificar**, porque el paquete no ha llegado a este
repositorio ni a esta máquina:

- Un ZIP con **21 adjuntos**: los dos informes (HTML y Markdown), **diecinueve** ficheros de evidencia numerada (incluido `17b`) y un
  **manifiesto nuevo** con tamaño y SHA-256 de cada original, más una nota de recuperación que distingue los adjuntos originales de los
  documentos nuevos. Declara haber comprobado que los originales coinciden byte a byte con los archivos accesibles en su entorno y que el ZIP
  supera su comprobación de integridad.
- **Falta la evidencia `01`**, referenciada por el informe. **No incluye** discos de VM, imágenes Docker, bundles Git ni el archivo comprimido
  citado dentro del HTML.
- El manifiesto permite verificar la **transferencia**; **no demuestra por sí solo la procedencia histórica** de cada archivo.

| Fichero | Origen | SHA-256 | Estado |
|---|---|---|---|
| `INFORME.md` y su versión HTML | informe de la fase 1 | — | **pendiente de incorporar y verificar** |
| `evidencias/11-m4-01-bootstrap.log` | primer intento de instalación | — | **pendiente** |
| `evidencias/18-inspeccion-env.txt` | permisos del `.env` | — | **pendiente** |
| resto de `evidencias/` (19 numeradas, con `17b`) | — | — | **pendiente; falta el listado del manifiesto** |
| `evidencias/01-…` | referenciada por el informe | — | **ausente en el paquete recuperado** |
| `MANIFIESTO-SHA256` y nota de recuperación | documentos nuevos del recuperador (no son adjuntos originales) | — | **pendiente** |

**Ubicación real del paquete original:** *por registrar por quien lo transfiera a este entorno.*

## Reglas de publicación

- **Solo material saneado:** nada de `.env`, discos de VM, credenciales, contraseñas, tokens ni datos reales. Antes de incorporar un
  fichero se revisa su contenido entero.
- Los resultados históricos **no se reescriben**. Una aclaración posterior va como **nota o errata fechada y enlazada**, aparte.
- Las correcciones posteriores (#237, #238) **no son resultados del ensayo original**: se enlazan, no se mezclan.
- **Antes de publicar cada fichero:** revisarlo entero (credenciales, rutas, nombres de usuario, direcciones). El recuperador declara no haber hecho un
  análisis exhaustivo de secretos.
