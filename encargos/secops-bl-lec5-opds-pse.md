# Encargo a SecOps: pasada de seguridad de BL-LEC5 (#828, PR #1153)

**SHA a dictaminar:** `59e64684fb31e6e3123eb458eceae29ba6310dd9` (rama `feat/bl-lec5-opds-pse`). Cualquier commit posterior exige nueva pasada.
**Pedido por:** el PO (2026-11-19). **Acuse de recibo: por favor, confirma que lo has recibido.**

## Qué cambia
- `GET /opds/paginas/{file_id}/{n}`: sirve páginas de un tebeo con la Basic de `/opds`.
- Enlace OPDS-PSE por número en `/opds/series/{id}`.
- Ficheros: `api/opds.py`, `services/lector.py`. No toca `services/seguridad.py`, `web/ajustes.py` ni `services/reautenticacion.py`.

## Qué mirar
1. **Autenticación:** el middleware cubre `/opds/*`; sin credenciales, 401 con `WWW-Authenticate` y sin redirección (prueba incluida).
2. **Validación de `file_id`:** `pagina()` → `_abrir`: archivo vinculado a un número, no perdido, no enlace simbólico, legible. Cualquier fallo, 404 sin detalle.
3. **`n`:** entero 0-basado; no numérico, negativo o fuera de rango dan 404.
4. **Fugas:** el XML no lleva rutas, nombres de archivo ni hashes; la URL lleva el UUID del archivo (igual que `/ui/leer`).
5. **Sin recodificar:** solo JPEG, PNG y GIF; otro tipo, 404.
6. **Caché:** `Cache-Control: private`, `Vary: Authorization`, `nosniff`.
7. **Recursos:** el feed mide cada archivo elegido (abre el ZIP o lista la caché de RAR) en un hilo; un RAR sin preparar no se prepara desde el OPDS. Evaluar el coste en una serie con muchos números en la Pi.
8. **Basic sobre HTTP:** en LAN sin TLS viaja en claro; el exterior exige proxy con TLS (ADR 0004). Dicho en `docs/design/especificacion-BL-C5-opds.md` §12.

## Resultados ya obtenidos
PASS: `tests/test_opds_pse.py` (14), suite completa 8023 passed. NOT RUN: app real y Pi.
