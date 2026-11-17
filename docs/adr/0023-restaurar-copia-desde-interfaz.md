# ADR 0023 — Restaurar una copia desde la interfaz

- **Estado:** propuesto (BL-OPS2, #443). No desplegado.
- **Contexto:** BL-OPS1 ya permite pedir una copia. Restaurar es más peligroso: reemplaza datos y puede reactivar credenciales y sesiones antiguas.
- **Decisión:** la app no recibe Docker ni root. Envía una petición **v2 firmada** (`restaurar`) al auxiliar del host; el auxiliar:
  1. elige solo copias propias (`backup_*` + manifiesto) y verifica la contraseña actual con PBKDF2;
  2. aplica límites (una restauración cada 30 min, 3/24 h, 5 fallos/15 min);
  3. arranca `zascarr-restaurar@<TS>.service`, que ejecuta `scripts/restaurar_datos.sh --produccion --copia <TS>`.
- El script guarda una copia previa verificada, restaura en el mismo flujo con `ON_ERROR_STOP`, y **reaplica selectivamente** la configuración vigente: credenciales, `secret_key`, `base_url`, `auth_session_version+1`, `*_enabled`, webhook y `fuentes_heredadas`. Las claves de integración y el resto vienen de la copia. Después relee y compara antes de arrancar.
- Las copias son **secretos**: contienen hashes de contraseña, `secret_key` y claves de integración. Quien obtenga un `.sql.gz` puede falsificar cookies de esa versión; restaurar conserva la `secret_key` vigente.
- **Riesgo residual:** quien ya controla la app y su base puede pedir la restauración; la comprobación de contraseña frena a quien solo comparte el grupo del socket. root con systemd sigue siendo root.
- **Recuperación:** si falla el cambio o el arranque, se vuelve a la copia previa; el diario solo lleva el nombre `rollback-safety_<TS>.sql.gz`, no rutas. Si el auxiliar deja contadores ilegibles, se borran como root `/run/zascarr-ops/pruebas` o `restauradas`.
- **Pendiente:** prueba real en la Pi, systemd real, C-10 con PostgreSQL real y revisión de Seguridad.
