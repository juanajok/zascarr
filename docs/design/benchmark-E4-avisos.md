# Ficha de benchmarking — aviso de importación (E4)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Breve: el
> riesgo está en la entrega y en no bloquear la importación, no en la UI.

**Historia / problema observado:**
E4 — avisar al móvil cuando se completa una importación, sin mirar el dashboard.

**Datos reales y medición de partida:**
Sin instalación todavía. El ciclo actual (`main.py::_import_loop`) hace
`scan_and_import()` → `session.commit()`, y `ImportReport.imported` ya es la
lista de archivos **nuevos** (los duplicados van a `duplicates`, la adopción
inicial ya no es automática desde B16).

**Referencias consultadas (URL, versión/commit):**
- Sonarr/Radarr: *Connect* (webhooks a Gotify/ntfy/Telegram/discord/URL), con
  reintento y reintento automático en backoff. Patrón de referencia, no
  implementación — versión/commit no fijado.
- Patrón local: `webhook_enabled`-style flags ya existen en D11.

**Cómo lo resuelve cada una:**
- Sonarr/Radarr *Connect*: cola de notificaciones con reintentos; una entrega
  fallida no revierte la importación (que ya está en la BD antes de notificar).

**Supuestos que NO valen en ZascArr:**
- *Connect* tiene una cola persistente y reintentos con backoff; ZascArr corre
  en una Pi compartida y E4 es tamaño S. Prometer entrega garantizada exige una
  cola persistente → otro alcance.

**Adoptar / adaptar / descartar:**
- **Adoptar:** disparar **después del commit**, solo con archivos nuevos.
- **Adaptar:** formato de webhook para Gotify/ntfy/Telegram/generic, apagado
  por defecto, con timeout corto.
- **Descartar (esta historia):** reintentos persistentes/cola — **entrega de
  mejor esfuerzo** documentada: un fallo se registra y no reintenta.

**Invariantes de ZascArr:**
- Un webhook caído/lento **no bloquea ni revierte** la importación.
- Un **4xx/5xx cuenta como fallo** (se registra con `send_failed`), no como
  envío correcto — por eso se comprueba el estado tras el POST.
- No exponer `webhook_token`/`webhook_url` en logs (pueden ser secretos).
- Gotify: token en cabecera `X-Gotify-Key`, **nunca** en la URL (la URL acaba
  en logs de acceso de Gotify o de un proxy aunque ZascArr no lo registre).
- Telegram **no usa `webhook_url`**: construye la ruta con el token del bot y
  exige token + chat_id.
- No notificar la adopción inicial ni duplicados de un segundo escaneo.

**Casos de prueba antes de implementar:**
- Un aviso tras el `commit`; ninguno si hay rollback.
- Ninguno si está desactivado.
- Ningún duplicado en el siguiente ciclo (el dedupe ya lo garantiza).
- Con un receptor HTTP falso: se envía un POST al destino correcto; un fallo
  no propaga; un 401/500 sí se registra como fallo; Telegram funciona sin URL.

**Decisión final / ADR:** no requiere ADR. **Decisión explícita: entrega de
mejor esfuerzo** (sin reintentos ni cola) para mantener E4 en tamaño S.
