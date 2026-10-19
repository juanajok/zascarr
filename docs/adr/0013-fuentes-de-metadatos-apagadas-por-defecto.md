# ADR 0013: Fuentes de metadatos apagadas por defecto

- Estado: **Aceptado por el PO** · 2026-10-19 (opción B de la ficha de decisión de #239, con condición). Implementación en esta PR; sin desplegar.
- Sustituye en lo que toca a los valores por defecto a la decisión B8 («activas por defecto», 2026-09-28). El interruptor por fuente, su override en caliente (D11) y GCD (E7) no cambian.
- Relacionado: [ADR 0012](0012-credenciales-del-env.md) (mismo principio: ningún estado de riesgo «por defecto»), CLAUDE.md §3.2 y §5, `docs/design/m4-plan-de-aceptacion-debian.md` §3.3, issue #239.

## Contexto

`comicvine_enabled`, `anilist_enabled`, `tebeosfera_enabled` y `gcd_enabled` valían `True` por defecto. Hechos verificados sobre `main` (`625a564`):

- El **enricher arranca con la aplicación** (primera pasada inmediata, luego cada 120 min) y, con las fuentes activas, consulta Comic Vine, AniList y Tebeosfera con los títulos de las series sin metadatos. **No espera a la aceptación legal** (sí lo hace el orquestador de descargas).
- Los flags **no se gobiernan desde el `.env`**: Compose solo transmite `FORUM_ENABLED` de las `*_ENABLED`. La vía efectiva es Ajustes (`runtime_settings`).
- Los textos decían otra cosa: el plan M4 §3.3 («permanecen apagadas, valor por defecto»), `LEGAL.md` («las fuentes que configure») y CLAUDE.md §3.2 («el usuario opta»).

No se midió tráfico real saliente: es una consecuencia del diseño, no una fuga demostrada.

## Decisión

1. **Los cuatro interruptores nacen apagados** (`default=False`). Ninguna fuente de metadatos consulta Internet hasta que el coleccionista la enciende en `/ui/ajustes`.
2. **Una actualización no apaga fuentes en silencio.** La migración de datos **0020** escribe las cuatro claves como `true` en `runtime_settings.values` en las instalaciones con **uso previo** (alguna fila en `series`, `files`, `wishlist`, `import_runs` o `legal_acknowledgments`, o algún ajuste ya guardado), **sin pisar** lo que el coleccionista ya hubiera guardado. Una instalación nueva (tablas vacías) no se toca y nace apagada.
3. **Aviso en Ajustes** (tarjeta «Fuentes de metadatos»): con alguna fuente activa, avisa de que consulta Internet con los títulos de la biblioteca y de cómo apagarla; con todas apagadas, lo dice. El contrato HTMX del formulario no cambia.
4. **`LEGAL.md` no se toca** (su `legal_version` es el hash del fichero y cambiarlo obligaría a reaceptar): con el nuevo valor por defecto, «las fuentes que configure» pasa a ser cierto.

## Consecuencias

- Las instalaciones nuevas no traen portadas ni metadatos externos hasta que el usuario enciende fuentes: es el coste elegido.
- El README ya decía «integraciones opcionales y desactivadas por defecto»; con esto es cierto también para metadatos.
- Límite: una instalación existente sin ningún dato ni ajuste se trata como nueva y queda apagada (no hay nada que conservar).
- `downgrade` de la 0020 **no hace nada**: no puede saber qué claves puso la migración y cuáles guardó el usuario. Con el código antiguo (default activo) las claves a `true` son inofensivas.
- **Fuera de esta decisión** (se abre aparte si se quiere): que el enricher espere a la aceptación legal, como el orquestador.

## Pruebas

`tests/test_fuentes_apagadas_por_defecto.py` (defaults y aviso, sin Postgres) y `tests/test_migracion_fuentes_pg.py` (con Postgres real: instalación nueva no escribe; cada señal de uso previo conserva; no pisa lo guardado; recrea la fila ausente; idempotente; la bajada no toca los ajustes).
