# Validación final de la épica #1021 (Biblioteca UX)

Fecha de preparación: 2026-11-18. No se ha desplegado nada desde este documento.

## Estado observado en la Pi

- Host `192.168.1.176`, proyecto `/opt/zascarr/zascarr`.
- HEAD desplegado: `66b980f4` (incluye UX-BIB-1 `d17e09e4`/`f96c5fae`, UX-BIB-2/4/5 y los ficheros de UX-BIB-3/6).
- Contenedores `postgres` y `zascarr` **healthy**; `/api/health` HTTP 200.
- Alembic: **0052 (head)**; enum `comic_tradition` incluye `hispanoamericano` y `series_kind` incluye `one_shot`.
- Disco raíz: 78 GiB libres (66 % usado).
- Datos: **254 series, 4.305 números, 5.106 archivos, 13 progresos, 5 visitas**. Cumple el mínimo del DoD (≥230/4.200/5.000).
- La UI exige sesión: `/ui/biblioteca` responde 303 a `/login`; la medición HTTP necesita una sesión temporal.

## EXPLAIN ya ejecutado (solo lectura, Pi real)

| Consulta | Plan | Tiempo |
|---|---|---|
| Series con `EXISTS` de `Issue.format='hardcover'` | Seq Scan de `issues` (4.305 filas), sin índice de formato | **0,873 ms** |
| Series por `kind='one_shot'` | Seq Scan de `series` (245 filas descartadas) | **0,182 ms** |

Conclusión: a este tamaño no hay problema de latencia, pero **no existe índice sobre `issues.format`**. Si se quiere cumplir literalmente «EXISTS indexado», añadir en una migración posterior `CREATE INDEX ix_issues_series_id_format ON issues (series_id, format)` y repetir el plan. No se ha añadido en esta preparación.

## Pasos para la pasada final

1. **Copia de seguridad** antes de desplegar: `sudo ./scripts/backup.sh` (o «Hacer una copia ahora»). Verificar `status.json`.
2. **Despliegue** del main validado (cuando el PO lo autorice): `git fetch && git checkout <sha> && sudo docker compose up -d --build`; esperar `healthy`.
3. **Migraciones**: `sudo docker compose exec -T zascarr alembic upgrade head`; comprobar `alembic current` = `0053` si se añade el índice, o `0052` si no.
4. **Login temporal** para las pruebas:
   ```bash
   export ZASCARR_TEST_PASSWORD='...'   # no se guarda en el repo
   python scripts/medicion/medir_biblioteca_1021.py \
     --base-url http://192.168.1.176:8000 --runs 30
   ```
5. **Smoke visual** con la app real: `/ui/biblioteca`, `?modo=escaparate`, `?densidad=compacta`, una ficha, favoritos, visor HD, filtros naturaleza/formato y 320/375/390/1280.
6. **Criterio DoD**: p95 de `/ui/biblioteca` y `/ui/biblioteca?modo=escaparate` **< 150 ms** con cachés calientes y concurrencia 1–2; sin errores 5xx; sin desbordes horizontales.
7. **Rollback**: volver al SHA anterior y `docker compose up -d`; las migraciones 0050–0052 son aditivas (0052 no se puede revertir por el enum, documentado).

## Qué queda bloqueado

- La medición HTTP real y la pasada visual necesitan **contraseña de la instalación** (no está en el repo ni se debe imprimir).
- El índice de `issues.format` es una decisión de rendimiento aparte; no bloquea funcionalmente #1021.
- El cierre de #1021 se hará cuando esos dos puntos estén medidos y el `ruff` global de CI deje de fallar por `src/zascarr/web/lector.py` (ajeno a la épica).
