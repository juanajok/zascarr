# A6 · Recuperación (parcial automatizada)

**Fecha:** 2026-11-21  
**SHA de producto:** `09a067fe` (rama `feat/uatp0607-recuperacion`).  
**Entorno:** Linux, suites automatizadas con Docker falso y PostgreSQL no real; **no** se ejecutó una candidata, una Pi, systemd ni una copia real de biblioteca.  
**Estado:** **A6 PARCIAL — no acredita UATP-06/07.** Sin candidata y sin copia de archivos real no se declara PASS.

## Resultados automatizados

| Check | Resultado | Evidencia |
|---|---|---|
| N-01 SHA de copia incorrecto: rc≠0, cero eventos Docker, base y copia intactas | PASS | `test_restaurar_produccion.py` |
| N-02 gzip truncado: rechazo antes de Docker | PASS | `test_restaurar_produccion.py` |
| N-03a falta `series`; N-03b falta `issues` | PASS | `test_restaurar_produccion.py`, `test_restaurar_datos.py` |
| Estado `copia_no_valida`, `comprobacion`, `base_en_su_sitio=true`; intentos conservados | PASS | `test_restaurar_produccion.py` |
| `version_de_la_copia` (head/build_sha/app_version/alembic; null si falta) | PASS | `test_version_copia.py`, `test_backup_script.py` |
| Lector reabre en la página guardada | PASS | `test_lector.py` |

Salida completa: [`evidencia/resultado.txt`](evidencia/resultado.txt) — **141 passed**.

## NOT RUN (imprescindible para cerrar A6)

- Restauración real en candidata aislada con PostgreSQL real y proyecto Compose.
- Copia de archivos manual a destino vacío, mtime/sha256 testigo y reapertura del CBZ restaurado.
- Ficha «Continuar (pág. N)» y lector en navegador real.
- Versión de la imagen candidata y tag anterior T0/T1.
- Diagnóstico con la app caída/systemd y evidencia sin secretos.

**No se convierte ningún NOT RUN en PASS.**
