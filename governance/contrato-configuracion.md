# Contrato de configuración, estado y exposición

**Estado: migración en curso.** Reglas trasladadas desde la guía vigente. La copia de `CLAUDE.md` se conserva; trasladar no retira la norma.

## PRE-07 — Integraciones y fuentes apagadas por defecto

- Las integraciones P2P están desactivadas por defecto (`FORUM_ENABLED=false` y análogas): el usuario opta, la aplicación no facilita nada por defecto. El patrón está explicado en `LEGAL.md`.
- Las fuentes de metadatos (Comic Vine, AniList, Tebeosfera, GCD) están apagadas por defecto por decisión de producto (ADR 0013): se encienden en Ajustes y el `.env` no las gobierna.
- Una actualización **no apaga en silencio** las fuentes de una instalación que ya las usaba: la migración 0020 las conserva y Ajustes avisa.

## PRE-08 — Estado observacional y aviso de versión de solo lectura

- El healthcheck es observacional, **no bloqueante**: una VPN caída es WARNING, no ERROR, y no congela ni el arranque ni el ciclo de descargas.
- El aviso de versión de `/estado` (ADR 0025) es solo lectura: SHA completo de la imagen y comparación de ascendencia con `main` en caché. Sin identidad o sin verificación dice «No se puede comprobar». Nunca actualiza, no ejecuta Git en la aplicación y no bloquea la página por la red.

## PRE-09 — La actualización manual no está habilitada por la decisión

El PO decidió confiar en `main` y permitir migraciones, sin aprobación por consola de cada SHA (ADR 0026). Esa decisión **cambia la política propuesta pero no habilita la función**: hacen falta un auxiliar de acción fija, autenticación, revisión de privilegios, estado fiable y pruebas aisladas.

Estado actual: UI conectada solo detrás de `OPS4_ACTUALIZACION_HABILITADA=false`, auxiliar y unidad separados, instalador sin activación por defecto. No está habilitada ni desplegada. No se conecta `update.sh` directamente a la aplicación.

## PRE-13 — Exposición de red (ADR 0004)

La interfaz escucha en localhost por defecto (`127.0.0.1`) y Postgres no se publica a la red en ningún caso. Abrir a la LAN es una decisión **explícita** del operador y exige contraseña; exponer al exterior exige proxy inverso con TLS y `BASE_URL`/`ALLOWED_HOSTS`.

El instalador (A11) fija la contraseña **antes** de publicar el puerto en las dos opciones que abren la interfaz.

## Límites

Este contrato no habilita ninguna función de actualización ni cambia la exposición por defecto. Cualquier cambio en estos ámbitos es de riesgo alto según [la clasificación](risk-classification.md).
