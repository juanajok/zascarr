# Medición OCTA-D4 — coste del `commit` de `get_db` en GET

- **Historia:** [#934](https://github.com/juanajok/zascarr/issues/934), épica OCTA-D
  [#917](https://github.com/juanajok/zascarr/issues/917).
- **Fecha:** 2026-11-17, 22:13 (Europe/Madrid).
- **Pi:** `main` `edf2fa61`, esquema **0050**, carga `0.14 / 0.22 / 0.15`; contenedor
  `zascarr-orquestador` contra PostgreSQL real.
- **Cambio de código:** ninguno. Esta ficha decide si hace falta.

## Qué se mide

`get_db` hace `await session.commit()` al final de **todas** las peticiones, también GET. En un
GET de solo lectura la transacción no tiene cambios; la pregunta es cuánto cuesta ese commit.

Se midió el ciclo completo de una sesión nueva por iteración, con 30 de calentamiento y **500
mediciones** por caso:

```python
async with async_session_factory() as s:
    await s.execute(text(sql))
    if commit:
        await s.commit()
```

Dos consultas: `SELECT 1` (coste mínimo) y `SELECT count(*) FROM series` (lectura típica).

## Resultados (ms)

| Caso | Media | p50 | p95 | Máx |
|---|---:|---:|---:|---:|
| `SELECT 1`, sin commit | 0,804 | 0,797 | 0,863 | 1,200 |
| `SELECT 1`, con commit | 0,865 | 0,840 | 0,900 | 7,570 |
| `count(*) series`, sin commit | 0,928 | 0,912 | 1,035 | 1,352 |
| `count(*) series`, con commit | 0,962 | 0,956 | 1,032 | 1,233 |

**Diferencia del commit:** +0,061 ms de media en el caso mínimo y +0,034 ms en la lectura típica;
p95 prácticamente igual (+0,037 ms y −0,003 ms). El único pico de 7,57 ms es un valor atípico
aislado, no repetido en la mediana ni en p95.

## Decisión

**Se mantiene `get_db` tal como está.** El commit de una transacción de solo lectura cuesta
fracciones de milisegundo (≈0,03–0,06 ms), por debajo del ruido de una petición real y de la
latencia de red/plantilla. Introducir una sesión de lectura separada añadiría un segundo camino
de sesión y riesgo de inconsistencias para no mejorar nada medible.

**Revisar solo si** en el futuro:
- una GET empieza a escribir en la sesión y el commit pasa a ser real;
- la latencia HTTP p95 sube y el perfilado señala la sesión;
- cambia el número de workers o el pool de conexiones de forma significativa.

## Límites de la medición

- Es un microbanco dentro del contenedor, no una traza HTTP completa; mide el coste del commit,
  que es la pregunta de D4.
- La Pi estaba en carga baja; no mide contención extrema del pool.
- No se cambió ni se reinició nada para medir.
