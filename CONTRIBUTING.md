# Contribuir a ZascArr

Gracias por querer mejorar ZascArr. Este documento resume el flujo de trabajo.
Las reglas de producto, diseño, arquitectura y seguridad están en
[`CLAUDE.md`](CLAUDE.md), que es la guía canónica del proyecto.

## Antes de empezar

- Lee [`README.md`](README.md), [`CLAUDE.md`](CLAUDE.md) y
  [`SECURITY.md`](SECURITY.md).
- Comprueba si la idea ya está en [`docs/BACKLOG.md`](docs/BACKLOG.md) o en un
  issue abierto. Una PR por historia; no mezcles refactors ajenos.
- Para problemas de seguridad, **no abras un issue público**: sigue
  [`SECURITY.md`](SECURITY.md).

## Entorno

Requisitos: [uv](https://docs.astral.sh/uv/) (gestiona también el Python 3.11)
y, para las pruebas de integración, PostgreSQL 15 y Docker.

```bash
uv sync --extra dev
uv run pre-commit install
```

Comandos habituales:

```bash
uv run make test          # suite completa
uv run make lint          # ruff check src/
uv run make format        # ruff format src/
uv run pytest -q tests/test_mi_cambio.py
```

Si cambias las dependencias en `pyproject.toml`, regenera `uv.lock` con
`uv lock` y commitéalo en la misma PR. La CI instala con `uv sync --frozen`:
un lock desincronizado hace fallar la suite.

Las pruebas que necesitan PostgreSQL real se saltan sin `TEST_DATABASE_URL`.
No las des por pasadas: si no se ejecutan, dilo en la PR como **NOT RUN**.

## Ramas y commits

- Parte de `main` actualizado: `git switch -c feat/mi-cambio origin/main`.
- Un tema por rama y una PR por historia.
- Mensajes en español, con prefijo convencional (`feat:`, `fix:`, `docs:`,
  `test:`, `chore:`), en imperativo y sin punto final.
- No reescribas el historial de una rama con PR abierta salvo que sea
  imprescindible; si lo haces, avisa en la PR.

## Qué debe llevar una PR

- Enlace al issue o a la historia (`Refs #123` o `Closes #123`).
- Una prueba de regresión por cada fallo corregido, nombrada con su mecanismo.
- `ruff check src/` sin errores y sin avisos nuevos.
- Si toca interfaz: comprobación en escritorio, 375 px y 320 px, tema claro y
  oscuro, teclado y foco visible.
- Lo que no se pudo comprobar, en **NOT RUN**, con el motivo.
- Nada de `.env`, credenciales, logs, capturas temporales ni artefactos locales.
- La plantilla de PR del repositorio, rellenada.

## Revisión, fusión y despliegue

- La CI debe estar en verde: suite, PostgreSQL real, ruff y las dos
  arquitecturas Docker.
- La fusión es por squash y requiere autorización expresa del mantenedor.
- El despliegue en la Pi es un paso separado y también requiere autorización.
  Una PR fusionada **no** está desplegada.
- No se hace commit directo a `main`.

## Código de conducta

Este proyecto sigue el [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Al
participar, aceptas cumplirlo.

## Licencia

Al contribuir aceptas que tu aportación se publique bajo la licencia
GPL-3.0-only del proyecto.
