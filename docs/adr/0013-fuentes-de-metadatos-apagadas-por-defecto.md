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
2. **Una actualización no apaga fuentes en silencio, y el estado heredado queda REGISTRADO** (no se deduce en cada arranque, no es una excepción difusa en el enricher). Tres estados persistidos en `runtime_settings.values`:

   | Situación de la instalación | Tras actualizar |
   |---|---|
   | Nunca guardó las fuentes en Ajustes y **ya usaba la aplicación** | Las cuatro **activas** y `fuentes_heredadas = true` («por compatibilidad»); Ajustes muestra el aviso |
   | Guardó las fuentes **activas** | Sin cambio; sin aviso |
   | Guardó las fuentes **desactivadas** | Sin cambio; sin aviso |
   | Instalación nueva | **Apagadas**, sin marcador, sin aviso |

   La migración de datos **0020** hace lo de la primera fila: «uso previo» = alguna fila en `series`, `files`, `wishlist`, `import_runs` o `legal_acknowledgments`, o algún ajuste ya guardado; escribe las cuatro claves a `true` **sin pisar** las que existieran y añade `fuentes_heredadas = true` solo si **ninguna** de las cuatro estaba guardada.
3. **Aviso en Ajustes** (tarjeta «Fuentes de metadatos»), **solo en estado heredado**: «Las fuentes de metadatos externas están activadas por compatibilidad con tu instalación anterior…». Guardar esa tarjeta —aunque no se cambie nada— pone `fuentes_heredadas = false` y el aviso desaparece. Guardar otra tarjeta no lo quita. El contrato HTMX del formulario no cambia.
4. **`LEGAL.md` se actualiza** (§3, fila del enricher de §4 y punto 2 de la aceptación) para reflejar que las fuentes son opcionales y desactivadas por defecto. Su `legal_version` es el hash del fichero, así que este cambio modifica la política de fuentes de metadatos y **requiere que el usuario vuelva a aceptar el aviso legal antes de que el orquestador reanude su funcionamiento**; no revoca un consentimiento previo: la política cambia y la aplicación pide una confirmación nueva. Decisión del PO tras la ficha de #239.

## Consecuencias

- Las instalaciones nuevas no traen portadas ni metadatos externos hasta que el usuario enciende fuentes: es el coste elegido.
- El README ya decía «integraciones opcionales y desactivadas por defecto»; con esto es cierto también para metadatos.
- Límite: una instalación existente sin ningún dato ni ajuste se trata como nueva y queda apagada (no hay nada que conservar).
- `downgrade` de la 0020 **no hace nada**: no puede saber qué claves puso la migración y cuáles guardó el usuario. Con el código antiguo (default activo) las claves a `true` son inofensivas.
- **Fuera de esta decisión** (se abre aparte si se quiere): que el enricher espere a la aceptación legal, como el orquestador.

## Pruebas

`tests/test_fuentes_apagadas_por_defecto.py` (defaults y aviso, sin Postgres) y `tests/test_migracion_fuentes_pg.py` (con Postgres real: los cuatro casos de la tabla; cada señal de uso previo; decisión parcial respetada; recrea la fila ausente; idempotente; la bajada no toca los ajustes) y la persistencia del marcador (`apply_overrides` al arrancar, limpieza al guardar).
