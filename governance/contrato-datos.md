# Contrato de datos y servicios

**Estado: migración en curso.** Recoge reglas trasladadas desde la guía vigente. La copia de `CLAUDE.md` se conserva: trasladar **no** retira la norma hasta que exista aprobación expresa de la retirada. Si este contrato y la guía discrepan, manda la guía y hay que corregir este fichero.

## PRE-01 — La capa de servicios es la única fuente de verdad del negocio

Los routers de API y web son finos y comparten la lógica; el negocio vive en servicios. Duplicar lógica entre routers produce bugs divergentes por diseño: hay un único camino por comportamiento.

## PRE-02 — El ORM nunca cruza un movimiento de ficheros con la sesión viva

Regla aprendida del tracker de Kapowarr: mover primero, hacer un `commit` corto después. Estado real auditado ([auditoría mover y sesión](../docs/design/auditoria-mover-y-sesion.md), V6a, 2026-10-03):

- `ReviewService.assign_to_series` **hoy no cumple** la regla: el `commit` de `get_db` ocurre tras la respuesta. Queda como código heredado, sin rutas.
- `services/asignacion.py` (ADR 0006) la cumple y es el **único camino** de `POST /ui/pendientes/{id}/asignar`.
- El importer sigue pendiente de un solo `commit` por ciclo.

No se presenta esta deuda como cumplimiento: es deuda declarada, y este texto no la cierra.

## PRE-38 — Migraciones aplicadas inmutables y tipos Postgres explícitos

- Migraciones Alembic **one-shot**: `versions/` no se reescribe una vez aplicado (aplicado = IDs 0001-0008). Saltarse esto rompe instalaciones reales.
- Enum Postgres con `postgresql.ENUM` explícito; el `create_table` vuelve a crear tipos si no se le dice lo contrario (bug documentado del 0001).
- La tradición se guarda como `String` con `values_callable` sobre `.value` en minúsculas, nunca `.name` en mayúscula (bug real del 0001).
- Las migraciones que tocan `CREATE EXTENSION` o `CREATE FUNCTION` usan `IF EXISTS`/`IF NOT EXISTS` y un downgrade coherente; `0006 f_title_norm` es la referencia de estilo.

## Límites

Este contrato describe decisiones vigentes de datos y servicios; no sustituye a los ADR que las originaron ni a las pruebas que las comprueban. No autoriza cambios de esquema: eso exige su propio contrato y su nivel de riesgo.
