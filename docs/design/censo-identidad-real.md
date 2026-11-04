# Censo de identidad editorial en la base real (#181)

> **Estado: ejecutado. Decisión: POSPONER el diseño de la migración de identidad editorial.**
> Solo lectura: no se creó, modificó ni borró nada. El informe no autoriza migración, cambios de esquema ni despliegue.

| | |
|---|---|
| **Fecha de ejecución** | 2026-11-04 |
| **Entorno** | Raspberry Pi del PO (producción), contenedor `zascarr-orquestador` |
| **Esquema** | `alembic_version = 0020` |
| **Checkout** | `8fc761f` (merge de #400 en `main`) |
| **Imagen desplegada** | `zascarr-zascarr:latest`, id `5aca677e9855`, `linux/arm64`, 613 MB |
| **Herramienta** | `scripts/medicion/censo_identidad.py` (sin cambios; último commit `a7fa840`) |
| **Parámetros** | modo compartible por defecto (sin `--local`); `DATABASE_URL` del propio contenedor |
| **Evidencia íntegra** | [`censo-identidad-2026-11-04.txt`](censo-identidad-2026-11-04.txt) |

**Garantía de solo lectura:** el script abre `BEGIN TRANSACTION READ ONLY`; Postgres rechaza cualquier escritura aunque el código se equivocara. La base no se volcó: la salida son agregados y una muestra de 20 filas con nombre y ruta **seudonimizados** (SHA-256 truncado, no anonimato fuerte).

## Qué se ejecutó

```bash
cd /opt/zascarr/zascarr
sudo docker compose exec -T zascarr python scripts/medicion/censo_identidad.py \
  2>&1 | tee "/tmp/censo-identidad-$(date +%F).txt"
```

**Incidencia de entorno (no del censo).** El primer intento falló con `open .env: permission denied` porque `docker compose` se ejecutaba como `pi` y el `.env` es de `root:600` (ADR 0012). Se resolvió con `sudo`. No produjo medición parcial ni dato contaminado: el censo se ejecutó una sola vez, completa.

## Métricas del censo (ADR 0003 y B22)

| Métrica | Valor | Lectura |
|---|---|---|
| **Filas por formato** | `single_issue` 443 · resto 0 | Los 443 `Issue` registrados son `single_issue`; ninguno tiene formato de recopilación. Entre los 897 archivos sin Issue no se ha comprobado si hay tomos o packs (NOT RUN 2). |
| **Colisiones de `number_key`** | `grupos_con_multiples` 0 · `colisiones_null` 0 · `issues_sin_numero` 0 | Ningún grupo `serie + número` tiene más de un issue; ningún número se repite con `volume` nulo. El índice único actual no tiene nada que desambiguar. |
| **Posibles ediciones** | `otras_ediciones_posibles` 0 | Ningún número aparece en dos volúmenes distintos: no hay reimpresión ni edición paralela en el catálogo. |
| **Recopilaciones** | `0` con archivo · `0` con evidencia almacenada | No hay recopilaciones que cubran grapas; los bloques de muestra de Omnigold/Integral, tomo y manga por tomos salen vacíos. |
| **Cobertura disponible** | `covered_issue_ids` 0 · `files_con_comicinfo` 0 | `covered_issue_ids = 0`: ninguna evidencia **almacenada en esa columna**. `files_con_comicinfo = 0`: ningún archivo declara `metadata_source='comicinfo_xml'`. El ComicInfo **dentro** del archivo no se inspecciona (NOT RUN 1). |
| **Registros sin contraste** | 272 de 443 sin fuente (61,4 %) · 171 `comic_vine` (38,6 %) | Casi dos tercios del catálogo no declaran fuente de metadatos. Es contexto de calidad de datos, no de identidad editorial. |

### Contexto del catálogo

- **20 series** (american 13, tebeo 4, franco-belga 2, manga 1) y **443 issues** (american 337 · tebeo 53 · manga 30 · franco-belga 23).
- **897 archivos sin Issue asignado** (`files.issue_id IS NULL`). El script los marca como *candidatos a pack* sin afirmarlo: **no abre archivos**, así que no puede decir si son packs, tomos o vinculaciones que no se completaron.
- El script **no imprime el total de archivos**, así que no se calcula porcentaje sobre ellos: sería un dato inventado.

## PASS / FAIL / NOT RUN

**PASS**
1. Censo ejecutado con el script existente, **sin modificarlo**, contra la base real.
2. Esquema, commit, imagen, fecha, entorno y parámetros conservados en la cabecera.
3. Las seis métricas del censo quedan cubiertas y con valor.
4. Solo lectura acreditada (`BEGIN TRANSACTION READ ONLY`) y muestra seudonimizada.
5. Salida íntegra conservada en el anexo, tal cual se produjo.

**FAIL**
- Ninguno del censo. La incidencia de permisos del primer intento es de entorno y está descrita arriba.

**NOT RUN**
1. **Cobertura verificable fuera de la base**: ComicInfo dentro de los archivos, catálogos editoriales y revisión manual. El script no los mide; `covered_issue_ids = 0` solo prueba que esa columna está vacía.
2. **Naturaleza de los 897 archivos sin Issue**: no se abrió ningún archivo; no se afirma que sean packs.
3. **Validación en una segunda instalación**: el censo describe esta biblioteca, no el parque de instalaciones.

## Lectura

En lo que el censo mide, no aparece el problema que la migración resolvería: una sola edición por número, cero colisiones, cero recopilaciones. Diseñar el modelo de ediciones (#184) con estos datos sería diseñar para un estado que no existe.

Ahora bien, **la ausencia no es neutra**: los 897 archivos sin Issue son justo el sitio donde vivirían los packs y tomos si existieran. El censo no puede distinguir «no hay recopilaciones» de «hay contenido que el modelo actual no puede expresar y por eso quedó sin vincular». Esa duda no la cierra este script: la cerraría un censo de contenido sobre esos 897 (leer nombres y ComicInfo), que es **otra historia**, no una modificación de #181.

## Decisión

**POSPONER** el diseño de la migración de identidad editorial: no hay evidencia, en el catálogo real, de que haga falta.

**Disparador para reabrir** (cualquiera de estos):
- aparece un `format` distinto de `single_issue` en el catálogo;
- `grupos_con_multiples` o `colisiones_null` dejan de ser 0;
- `covered_issue_ids` deja de ser 0;
- se censan los 897 archivos sin Issue y resultan ser packs o tomos (el `.txt` ya marca 9 de 20 candidatos con nombre que «parece rango»; es heurístico, no cobertura cierta).

**Propuesta al PO (fuera de #181):** una tarjeta para caracterizar esos 897 archivos sin abrir la biblioteca en modo escritura. Es la única pieza que falta para que «posponer» sea una decisión cerrada y no una decisión a la espera.

## Qué NO autoriza este informe

- No autoriza migración ni cambio de esquema.
- No autoriza tocar datos, archivos ni despliegue.
- No cierra #182, #183 ni #184: los deja sin materia prima hasta que se cumpla un disparador.

## Cómo reproducirlo

```bash
sudo docker compose exec -T postgres psql -U comics_admin -d zascarr -tAc "select version_num from alembic_version"
sudo docker compose exec -T zascarr python scripts/medicion/censo_identidad.py 2>&1 | tee censo.txt
```

Sin `--local`: esa variante imprime títulos y rutas reales y no se comparte.
